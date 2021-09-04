import os
import io
import asyncio
import concurrent.futures
import functools

import pipe_writer
import sys # for output to sys.stderr

from abc import ABC, abstractmethod

"""
    classes:
        TaskResultWriter
        Interleaver(TaskResultWriter)
            Interleaver__Source
"""

"""
notes: 
 TaskResultWriter
    implements
    ---------
    _flush_pipe
    _write_to_pipe
    update_capacity()
    query_len()
    count_bytes_requesting()
    refresh()

    inheritor must implement:
    -------------------------
    add_result_file()
    commit_added_result_files()
    count_uncommitted()

    inheritor may override:
    --------------------------
    refresh()

    about:
    The TaskResultWriter is an abstract class which permits the developer to customize how the model will process
    the task results. Its primary function is to be an intermediate point of transfer to the underlying
    `_writerPipe`, which by default is a named pipe writer. (Future versions will abstract _writerPipe.)

    The writer is initialized with a message queue to the controller and optionally a writer override, which
    defaults to PipeWriter (pipe_writer.py). The number of bytes currently in the writer is queried via
    query_len() and is always less than or equal to the current maximum capacity. The number of bytes that
    the writer can accept is given by count_bytes_requesting(). The writer is manually flushed via its
    refresh() method (which should be called from an overidden refresh method).

    The implementation must define add_result_file(...) and commit_added_result_files. The super __del__ should also be
    called from an overidden __del__. The typical implementation would define the logic for adding files
    and for signifying when all files (results) from a task have been provided (commit_added_result_files).

"""





  ###################################
 # TaskResultWriter{}              #
###################################
# a callable wrapper around the pipe_writer module utilized by ctx.download_bytes in steps (a copy of which is stored in the task data)
# provides an interface for inspection of the buffer from elsewhere in the app
class TaskResultWriter(ABC):
    _bytesSeen = 0
    _writerPipe = None
    to_ctl_q = None

    def __init__(self, to_ctl_q, POOL_LIMIT, writer=pipe_writer.PipeWriter):
        self.to_ctl_q = to_ctl_q
        self._writerPipe = writer(POOL_LIMIT)
        # self._writerPipe = pipe_writer.PipeWriter(POOL_LIMIT)


    async def _flush_pipe(self):
        await self._writerPipe.refresh()


    async def _write_to_pipe(self, data):
        written = await self._writerPipe.write(data)
        # self._flush_pipe()
        return written


    def update_capacity(self, new_capacity):
        self._writerPipe._set_max_capacity(new_capacity)


    def query_len(self) -> int:
        return self._writerPipe.len()


    def count_bytes_requesting(self) -> int:
        # return how many bytes the buffer can accept
        # check if the POOL_LIMIT has not been reached
        return self._writerPipe.countAvailable()

    # the inheritor may wish to write processed data first then calling this as a super
    async def refresh(self):
        # since the PipeWriter object must be manually refreshed regularly
        await self._flush_pipe()

    # number of result files added so far
    @abstractmethod
    def count_uncommitted(self):
        pass

    @abstractmethod
    def add_result_file(self, filepathstring):
        pass

    @abstractmethod
    def commit_added_result_files(self):
        pass

    def __del__(self):
        if self._writerPipe:
            self._writerPipe.__del__()







######################{}########################
class Interleaver__Source():
# wraps a task result file
# required by Interleaver
################################################
    _file = None
    _filePath = None
    _file_len = None

    def __init__(self, filePath):
        self._file_len = os.path.getsize(filePath)
        self._file = open(filePath, 'rb', opener=lambda path, flags: os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        self._filePath = filePath


    def hasPageAvailable(self, page_size):

        def ___remaining():
            told = self._file.tell()
            remaining = self._file_len - told
            return remaining
        return ___remaining() >= page_size


    def read(self, page_size):
        return self._file.read(page_size)


    def __del__(self):
        self._file.close()
        os.unlink(self._filePath)

    







######################{}########################
class Interleaver(TaskResultWriter):
# reference implementation of TaskResultWriter
################################################
    """
    definitions:
    
    result := Interleaver__Source object, which wraps the result_file for reading...

    attributes/methods:

    / _page_size                    { computed property }
     - shortest length of all results next in queue

    _source_groups
     - [ [result, result, ...], [ result, result, ...] ] # results (as wrapped file streams ie Interleaver__Source) are added in groups and queued

    _source_next_group
     - [ result, result ...] # which add_result_file augments until full then added to _source_Groups

    add_result_file(...)            { implement }
     - augment _source_next_group by opening/wrapping in Interleaver__Source and appending _source_next_group

    count_uncommitted(...)          { implement }
     - length of _source_next_group

    commit_added_result_files(...)  { implement }
     - move append _source_next_group to _source_groups and clear

    refresh(...)                    { override }
    """

    """
    Extended Description:
        The Interleaver class subclasses TaskResultWriter to prepare the bytes that are written to the
        writer object setup by the superclass.

        The Interleaver class initially waits for the results of a Golem executor (tasks) by collecting
        them into a temporary variable `_source_next_group`, which are added to the `_source_groups`
        as a sublist upon invocation of commit_added_result_files().

        When manually refreshed via refresh():
            Interleaver checks to see whether there are at least two files in
            the head, or first element of, `_sources_groups` and interleaves the bytes from all the souces.
            The interleaving process reads a byte from each source_file streams to consecutively place them
            into the underlying pipe writer (see super).

            Given two bytes streams
                b'deadbeef
                b'defgaf     <- shortest length is a the cutoff (returned by `_page_size()`)
            the result according to the algorithm would be written to the underlying writer as
                ddeeafdgbaef 
            (notice that terminating ef was not including because there is no more to alternate)

            the group is popped from `_source_groups` and burned if a there is only one stream that has not been
            completely read and the next group in the to the head of the list.

            when the result is written to the underlying writer, it is also sent over the message queue
            back to the controller (which can display it to the UI).
        comments: the _page_size will result in a loss of bytes if the lengths of the results are disparate

    """
    _source_groups = [] # sublists of task result groups
    _source_next_group = [] # next sublist of tasks results before being committed

    # ----------------------------------------------
    @property
    def _page_size(self):
    # ----------------------------------------------
    # computes the shortest length of all files in a group so that all can be read from equally
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



    # ------------------------------------------------------
    def __init__(self, to_ctl_q, POOL_LIMIT):
    # ------------------------------------------------------
        super().__init__(to_ctl_q, POOL_LIMIT)




    # ----------------------------------
    def add_result_file(self, filepathstring):
    # ----------------------------------
        source = Interleaver__Source(filepathstring)
        self._source_next_group.append(source)

    # ----------------------------------
    def count_uncommitted(self):
    # ----------------------------------
        return len(self._source_next_group)


    # commit_added_result_files is called when a new group of files have been added
    # soft prereq: at least 2 files have been added
    # tip: a developer could subclass and modify commit_added_result_files to add a locally
    # generated stream to the group before adding the group
    # ------------------------------------------------------
    def commit_added_result_files(self):
    # ------------------------------------------------------
        accum = 0
        for source in self._source_next_group:
            accum += source._file_len
        self._bytesSeen+=accum
        self._source_groups.append(self._source_next_group)
        self._source_next_group = []




    # post: if a group is available and readable, the `_writerPipe` is given a "book" of interleaved bytes
    # ---------------------------------------
    async def refresh(self):
    # ---------------------------------------
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


        ___refresh_source_groups()  # ensure there are at least two results with at least length _page_size
                                    # at the head of _source_groups

        # [ viable source list (2+ members with all having at least a page of bytes) now at head ]
        if len(self._source_groups) > 0: 
            pages = []

            # read the calculated page size from each file and add to a "pages" list
            for source in self._source_groups[0]:
                pages.append(io.BytesIO(source.read(self._page_size)))
                await asyncio.sleep(0) # ------- yield ---------
                # await asyncio.sleep(0.01) # ------- yield ---------

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
                    # await asyncio.sleep(0.001) # --------- yield -----------
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

        await self._flush_pipe()




    # -------------------------------------
    def __del__(self):
    # -------------------------------------
    # the deconstructor is called on every member of every subgroup
        for source_group in self._source_groups:
            source_group.clear() # deletes underlying files
        super().__del__()
