import os
# import asyncio
import pipe_writer

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
    _page_size = None

    def __init__(self, filePath, page_size):
        self._file_len = os.path.getsize(filePath)
        self_file = open(filePath, 'rb', opener=lambda path, flags: os.open(path, os.O_RDONLY | os.O_NONBLOCK))
        self._filePath = filePath
        self._page_size = page_size

    def hasPageAvailable():

        def ___remaining():
            told = self._file.tell()
            remaining = self._file_len - told - 1

        return ___remaining() >= self._page_size

    def read():
        return self._file.read(self._page_size)

    

    def delete():
        self._file.close()
        os.unlink(self._filePath)


######################{}########################
class Interleaver(TaskResultWriter):
################################################
    _page_size = None
    _sources = [] # all groups added
    _sources_uncommitted = [] # current group

    def __init__(self, to_ctl_q, POOL_LIMIT, page_size=4096):
        super().__init__(to_ctl_q, POOL_LIMIT)
        self._page_size = page_size

    def add_file(self, filepathstring):
        source = Interleaver__Source(filepathstring, self._page_size)
        self._sources.append(source)

    # called when a new group of files have been added
    # expected: at least 2 files have been added
    def commit_added_files(self):
        _sources.append(_sources_uncommitted)


    # post: if a group is available and readable, the _writerPipe receives a page
    async def refresh():
        def ___refresh_sources():
            if len(self._sources) > 0:
                sources = self._sources[0]
                shortlist = [ source for source in source_group if source.hasPageAvailable() ]
                for source_list_item in shortlist:
                    self._sources.remove(source_list_item)
                    source_list_item.delete()

            while len(self._sources) < 2:
                popped_source = list.pop(0)
                popped_source.delete()

        ___refresh_sources() # viable source list (2+ members with all having at least a page of bytes) now at head of _sources

        if len(self._sources) >= 0:
            pages = []
            for source in self._sources:
                pages.append(io.BytesIO(sources.read()))


            book=bytearray()
            for _ in range(self._page_size):
                for page in pages:
                    book.append(page.read1())

            for page in pages:
                page.close()

            self._writerPipe.write(book)


    def __del__():
        for source_group in self._sources:
            for source in source_group:
                source.delete()

