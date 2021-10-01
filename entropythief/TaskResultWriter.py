import os
import io
import asyncio
import concurrent.futures
import functools

from . import pipe_writer
import sys # for output to sys.stderr

from abc import ABC, abstractmethod



  ###################################
 # TaskResultWriter{}              #
###################################
class TaskResultWriter(ABC):
    """interfaces with pipe_writer module or derivative to communicate the results of a finished task externally"""
    _bytesSeen = 0
    _writerPipe = None
    to_ctl_q = None

    def __init__(self, to_ctl_q, POOL_LIMIT, writer=pipe_writer.PipeWriter):
        """initialize TaskResultWriter with a message queue to the controller and a pipe writer"""
        self.to_ctl_q = to_ctl_q
        self._writerPipe = writer(POOL_LIMIT)


    async def _write_to_pipe(self, data):
        """writes data to the pipe"""
        written = await self._writerPipe.write(data)
        return written


    def update_capacity(self, new_capacity):
        """informs on the most number of bytes the writer can hold at a given time"""
        self._writerPipe._set_max_capacity(new_capacity)


    def query_len(self) -> int:
        """queries the number of bytes in the pipe writer"""
        return self._writerPipe.len()


    def count_bytes_requesting(self) -> int:
        """queries the most number of bytes the pipe writer will accept without discarding"""
        return self._writerPipe.countAvailable()

    # the inheritor may wish to write processed data first then calling this as a super
    async def refresh(self):
        """flushes the pipe writer in an asynchronous loop"""
        # since the PipeWriter object must be manually refreshed regularly
        while True:
            await self._writerPipe.refresh()
            # await self._flush_pipe()
            print("refresh", file=sys.stderr)
            await asyncio.sleep(0.01)

    # number of result files added so far
    @abstractmethod
    def count_uncommitted(self):
        """indicates the number of partial result files receieved"""
        pass

    @abstractmethod
    def add_result_file(self, filepathstring):
        """receives one new result file """
        pass

    @abstractmethod
    def commit_added_result_files(self):
        """receives the signal indicating there are no more results incoming"""
        pass

    def __del__(self):
        """invokes the delete method on the pipe writer it has been initialized with"""
        if self._writerPipe:
            self._writerPipe.__del__()







######################{}########################
class Interleaver__Source():
    """wraps a task result file for reading"""
    # required by Interleaver
    _file = None
    _filePath = None
    _file_len = None

    def __init__(self, filePath):
        """initializes with the file to wrap"""
        self._file_len = os.path.getsize(filePath)
        self._file = open(filePath, 'rb', opener=lambda path, flags: os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        self._filePath = filePath


    def hasPageAvailable(self, page_size):
        """determines if a length of page size is able to be read"""
        def ___remaining():
            told = self._file.tell()
            remaining = self._file_len - told
            return remaining
        return ___remaining() >= page_size


    def read(self, page_size):
        """reads a page_size length of bytes from the file and returns the bytearray"""
        return self._file.read(page_size)


    def __del__(self):
        """unlinks the wrapped file"""
        self._file.close()
        os.unlink(self._filePath)

    







######################{}########################
class Interleaver(TaskResultWriter):
    """implements TaskResultWriter to aggregate then interleave task results writing out as a random byte stream"""
    # a reference implementation of TaskResultWriter
    _source_groups = [] # sublists of task result groups
    _source_next_group = [] # next sublist of tasks results before being committed

    # ----------------Interleaver-------------------
    @property
    def _page_size(self):
        """compute the shortest length of all files in the current group, so that all can be read from alternately"""
    # ----------------------------------------------
        if len(self._source_groups) == 0:
            return 0 # no pages no length

        if len(self._source_groups[0]) > 0: 
            minimum_from_first_group = min(self._source_groups[0], key=lambda source: source._file_len)._file_len

        minimum_length = minimum_from_first_group
        return minimum_length 
            
    """
    @_page_size.setter
    def _page_size(self, size):
        self.__page_size = size
    """



    # -----------------Interleaver--------------------------
    def __init__(self, to_ctl_q, POOL_LIMIT):
    # ------------------------------------------------------
        super().__init__(to_ctl_q, POOL_LIMIT)




    # ------------Interleaver-----------
    def add_result_file(self, filepathstring): # implement
    # ----------------------------------
        source = Interleaver__Source(filepathstring)
        self._source_next_group.append(source)




    # ----------Interleaver-------------
    def count_uncommitted(self): # implement
    # ----------------------------------
        return len(self._source_next_group)


    # ---------------Interleaver----------------------------
    def commit_added_result_files(self): # implement
    # soft prereq: at least 2 files have been added
    # tip: a developer could subclass and modify commit_added_result_files to add a locally
    # generated stream to the group before adding the group
    # ------------------------------------------------------
        accum = 0
        for source in self._source_next_group:
            accum += source._file_len
        self._bytesSeen+=accum
        self._source_groups.append(self._source_next_group)
        self._source_next_group = []




    # post: if a group is available and readable, the `_writerPipe` is given a "book" of interleaved bytes
    # ------------Interleaver----------------
    async def refresh(self): # override
        """alternate across bytes from each task result, write alternated sequence to pipe and controller-view"""



        # ........................................
        # post: _source_groups either has a list of 2 or more results in the front of the queue
        #       or groups are removed until this condition has been satisfied or until empty
        def ___refresh_source_groups():
            if len(self._source_groups) > 0:
                sources = self._source_groups[0] # just treat head
                shortlist = [ source for source in sources if not source.hasPageAvailable(self._page_size) ]
                # prune from head source group
                for source_list_item in shortlist:
                    self._source_groups[0].remove(source_list_item)
                    del source_list_item # deletes the underlying file

            # after pruning, it is possible there are less than 2 items
            # in which case the group is popped
            if len(self._source_groups) > 0:
                current_group = self._source_groups[0]

                if len(current_group) == 0:
                    self._source_groups.pop(0) # empty pop
                elif len(current_group) < 2: # dangling group has only one member
                    popped_dangling_source_group = self._source_groups.pop(0)
                    popped_dangling_source_group.clear() # deletes underlying files

        # ........................................

        while True:
            ___refresh_source_groups()  # ensure there are at least two results with at least length _page_size
                                        # at the head of _source_groups

            # [ viable source list (2+ members with all having at least a page of bytes) now at head ]
            if len(self._source_groups) > 0: 
                pages = []

                # read the calculated page size from each file and add to a "pages" list
                for source in self._source_groups[0]:
                    pages.append(io.BytesIO(source.read(self._page_size)))
                    await asyncio.sleep(0) # ------- yield ---------

                # write the pages into a single book, alternating each byte across all pages
                book=io.BytesIO()
                k_yield_byte_count=4096 # number of bytes to read before asynchronously yielding
                intervalcount=0 # the number of times yield_byte_count as been read since the last pipe write
                k_interval_reset_count=10
                bytes_read=0
                debug_count=0
                for _ in range(self._page_size): # up to the shortest length of all results (now stored in pages)
                    for page in pages: # read next byte from each page/result writing them alternately into the book
                        book.write(page.read(1)) # read,write
                        bytes_read+=1

                    if bytes_read >= k_yield_byte_count:
                        bytes_read=0
                        intervalcount+=1
                        await asyncio.sleep(0) # --------- yield -----------
                        # upon every intervalcount intervals write whatever was written in the book (intervalcount * k_yield_byte_count)
                        if intervalcount == k_interval_reset_count:
                            intervalcount = 0
                            # write to pipe

                            # print(f"WRITING TO PIPE count: {debug_count}", file=sys.stderr)
                            # debug_count+=1

                            written = await self._write_to_pipe(book.getbuffer())
                            # send hex serialized version to controller
                            randomBytesView = book.getvalue() # optimize?
                            to_ctl_cmd = {'cmd': 'add_bytes', 'hex': randomBytesView[:written]}; self.to_ctl_q.put_nowait(to_ctl_cmd)

                            # clear book from memory and start a new one
                            book.close()
                            book=io.BytesIO()

                            # directly inform controller of any change in pipe, which is next to guaranteed
                            msg = {'bytesInPipe': self.query_len()}; self.to_ctl_q.put_nowait(msg)
                    await asyncio.sleep(0)
                # write remaining that is less than yield_byte_count
                written = await self._write_to_pipe(book.getbuffer())

                # share with controller a view of the bytes written
                randomBytesView = book.getvalue()
                msg = randomBytesView[:written].hex()
                # to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}; self.to_ctl_q.put_nowait(to_ctl_cmd)
                # msg = {'bytesInPipe': self.query_len()}; self.to_ctl_q.put_nowait(msg)
                # TODO for later messages can be tx faster of they are smaller in size (e.g. binary vs hex)
                to_ctl_cmd = {'cmd': 'add_bytes', 'hex': randomBytesView[:written]}; self.to_ctl_q.put_nowait(to_ctl_cmd)

                for page in pages:
                    page.close() # garbage collect pages (not really necessary in this case)
            await asyncio.sleep(0.01)
        # await self._flush_pipe()




    # ---------Interleaver-----------------
    def __del__(self): # override
        """deletes Interleaver__source objects added to it"""
    # -------------------------------------
    # the deconstructor is called on every member of every subgroup
        for source_group in self._source_groups:
            source_group.clear() # deletes underlying files
        super().__del__()
