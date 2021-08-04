import os
import io
import asyncio
import concurrent.futures
import functools

import pipe_writer
import sys # for output to sys.stderr

  ###################################
 # TaskResultWriter{}              #
###################################
# a callable wrapper around the pipe_writer module utilized by ctx.download_bytes in steps (a copy of which is stored in the task data)
# provides an interface for inspection of the buffer from elsewhere in the app
class TaskResultWriter:
    _bytesSeen = 0
    _writerPipe = None
    to_ctl_q = None
    def __init__(self, to_ctl_q, POOL_LIMIT):
        self.to_ctl_q = to_ctl_q
        self._writerPipe = pipe_writer.PipeWriter(POOL_LIMIT)

    def query_len(self) -> int:
        return self._writerPipe.len()



    def count_bytes_requesting(self) -> int:
        # return how many bytes the buffer can accept
        # check if the POOL_LIMIT has not been reached
        return self._writerPipe.countAvailable()



    async def refresh(self, pool_limit=None):
        # since the PipeWriter object must be manually refreshed regularly
        if pool_limit:
            self._writerPipe._set_max_capacity(pool_limit)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(), self._writerPipe.refresh)



    async def __call__(self, randomBytes):
        self._bytesSeen += len(randomBytes)
        written = self._writerPipe.write(randomBytes)
        await asyncio.sleep(0.001) # may help yield cpu time (but steps async generator may be sufficient) REVIEW

        # inform controller
        msg = randomBytes[:written].hex()
        to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
        self.to_ctl_q.put_nowait(to_ctl_cmd)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(), self._writerPipe.refresh)

        bytesInPipe = self.query_len()
        msg = {'bytesInPipe': bytesInPipe}
        self.to_ctl_q.put_nowait(msg)

    def __del__(self):
        if self._writerPipe:
            self._writerPipe.__del__()





######################{}########################
class Interleaver__Source():
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
################################################
    __page_size = None
    _source_groups = [] # all groups added
    _source_next_group = []

    @property
    def page_size(self):
        if len(self._source_groups) == 0: # stub, TODO REVIEW
            return 4096

        if len(self._source_groups[0]) > 0: # kludge, TODO REVIEW
            minimum_from_first_group = min(self._source_groups[0], key=lambda source: source._file_len)._file_len

        if self.__page_size is not None:
            minimum_length = self.__page_size
            # check that minimum length would not exceed the min
            if minimum_length > minimum_from_first_group:
                minimum_length = minimum_from_first_group
        else:
            minimum_length = minimum_from_first_group

        return minimum_length 
            
    @page_size.setter
    def page_size(self, size):
        self.__page_size = size

    # ------------------------------------------------------
    def __init__(self, to_ctl_q, POOL_LIMIT, page_size=None):
    # ------------------------------------------------------
        super().__init__(to_ctl_q, POOL_LIMIT)
        self.__page_size = page_size

    # ----------------------------------
    def add_file(self, filepathstring):
    # ----------------------------------
        source = Interleaver__Source(filepathstring)
        self._source_next_group.append(source)

    # called when a new group of files have been added
    # expected: at least 2 files have been added
    # ------------------------------------------------------
    def commit_added_files(self):
    # ------------------------------------------------------
        accum = 0
        for source in self._source_next_group:
            accum += source._file_len
        self._bytesSeen+=accum
        self._source_groups.append(self._source_next_group)
        self._source_next_group = []




    # post: if a group is available and readable, the _writerPipe receives a page
    # ---------------------------------------
    async def refresh(self):
    # ---------------------------------------
        def ___refresh_source_groups():
            if len(self._source_groups) > 0:
                sources = self._source_groups[0] # just treat first
                shortlist = [ source for source in sources if not source.hasPageAvailable(self.page_size) ]
                # prune first source group (always the only one read from)
                for source_list_item in shortlist:
                    self._source_groups[0].remove(source_list_item)
                    del source_list_item

            # after pruning, it is possible there are less than 2 items
            # in which case the group is popped
            if len(self._source_groups) > 0:
                current_group = self._source_groups[0]

                if len(current_group) == 0:
                    self._source_groups.pop(0)
                elif len(current_group) < 2: # dangling group has only one member
                    popped_dangling_source_group = self._source_groups.pop(0)
                    popped_dangling_source_group.clear()

        # ........................................


        ___refresh_source_groups() # viable source list (2+ members with all having at least a page of bytes) now at head of _source_groups

        # print(self._source_groups, file=sys.stderr)
        if len(self._source_groups) > 0:
            pages = []

            for source in self._source_groups[0]:
                try:
                    pages.append(io.BytesIO(source.read(self.page_size)))
                except Exception as e:
                    print(f"WTF: {e}", file=sys.stderr)
            book=io.BytesIO()
            for _ in range(self.page_size):
                for page in pages:
                    book.write(page.read(1))

            for page in pages:
                page.close()

            written = self._writerPipe.write(book.getvalue())
            # share with controller a view of the bytes written
            randomBytesView = book.getbuffer()
            msg = randomBytesView[:written].hex()
            to_ctl_cmd = {'cmd': 'add_bytes', 'hexstring': msg}
            self.to_ctl_q.put_nowait(to_ctl_cmd)

        loop = asyncio.get_running_loop()
        
        await loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(), self._writerPipe.refresh)

        

    def update_capacity(self, new_capacity):
        self._WriterPipe._set_max_capacity(new_capacity)



    def __del__(self):
        for source_group in self._source_groups:
            source_group.clear()
