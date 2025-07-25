import os
import io
import asyncio
import concurrent.futures
import functools

from . import pipe_writer
import sys  # for output to sys.stderr

from abc import ABC, abstractmethod


###################################
# TaskResultWriter{}              #
###################################
class TaskResultWriter(ABC):
    """interfaces with pipe_writer module or derivative to communicate the results of a finished task externally"""

    _bytesSeen = 0
    _writerPipe = None
    to_ctl_q = None

    def __init__(self, to_ctl_q, writer=pipe_writer.PipeWriter, target_capacity=None):
        """initialize TaskResultWriter with a message queue to the controller and a pipe writer
        
        Args:
            to_ctl_q: Queue to send messages to controller
            writer: PipeWriter class to use
            target_capacity: Target capacity limit - for controller tracking only
        """
        self.to_ctl_q = to_ctl_q
        self.target_capacity = target_capacity
        
        # Create PipeWriter without capacity limits - let data flow freely
        self._writerPipe = writer()

    async def _write_to_pipe(self, data):
        """writes data to the pipe"""
        # TRACKING: Log data being sent to PipeWriter
        data_size = len(data) if data else 0
        print(f"DEBUG: TaskResultWriter._write_to_pipe: Sending {data_size:,} bytes to PipeWriter", file=sys.stderr)
        written = await self._writerPipe.write(data)
        print(f"DEBUG: TaskResultWriter._write_to_pipe: PipeWriter accepted {written:,} bytes", file=sys.stderr)
        return written

    def __len__(self):
        """Return the number of bytes currently buffered in the writer."""
        return self._writerPipe.len()

    def update_capacity(self, new_capacity):
        """Update the target capacity for controller tracking only"""
        print(f"DEBUG: TaskResultWriter.update_capacity called with {new_capacity:,} bytes (tracking only)", file=sys.stderr)
        self.target_capacity = new_capacity
        # Note: PipeWriter has no capacity enforcement - data flows freely

    # the inheritor may wish to write processed data first then calling this as a super
    async def refresh(self):
        """flushes the pipe writer in an asynchronous loop"""
        # since the PipeWriter object must be manually refreshed regularly
        while True:
            await self._writerPipe.refresh()
            # await self._flush_pipe()
            print("refresh", file=sys.stderr)
            await asyncio.sleep(0.002)  # 2ms for responsive UI (was 0.01 = 10ms)

    # number of result files added so far
    @abstractmethod
    def count_uncommitted(self):
        """indicates the number of partial result files receieved"""
        pass

    @abstractmethod
    def add_result_file(self, filepathstring):
        """receives one new result file"""
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
class Interleaver__Source:
    """wraps a task result file for reading"""

    # required by Interleaver
    _file = None
    _filePath = None
    _file_len = None

    def __init__(self, filePath):
        """initializes with the file to wrap"""
        self._file_len = os.path.getsize(filePath)
        self._file = open(
            filePath,
            "rb",
            opener=lambda path, flags: os.open(path, os.O_RDONLY | os.O_NONBLOCK),
        )
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

    _source_groups = []  # sublists of task result groups
    _source_next_group = []  # next sublist of tasks results before being committed
    pending = False
    
    def __init__(self, to_ctl_q, target_capacity=None):
        """Initialize Interleaver without capacity enforcement
        
        Args:
            to_ctl_q: Queue to send messages to controller  
            target_capacity: Target capacity limit (ENTROPY_BUFFER_CAPACITY) - for tracking only
        """
        # Create PipeWriter without capacity limits - let data flow freely
        super().__init__(to_ctl_q, pipe_writer.PipeWriter, target_capacity=None)
        self._entropy_buffer_size = target_capacity  # Store for internal tracking only
        
        # Set default buffer size for SSD storage (most common modern setup)
        # This ensures consistency with the storage type configurations
        self.set_buffer_size_for_storage_type('ssd')

    def set_buffer_size_for_storage_type(self, storage_type: str) -> None:
        """Configure optimal buffer size based on storage type
        
        Args:
            storage_type: 'ssd', 'nvme', 'enterprise', or 'maximum'
        """
        storage_configs = {
            'ssd': 2097152,      # 2MB - Good for most modern SSDs
            'nvme': 8388608,     # 8MB - Optimal for high-end NVMe drives  
            'enterprise': 16777216,  # 16MB - For enterprise SSDs
            'maximum': 33554432,     # 32MB - Maximum throughput mode
        }
        
        if storage_type.lower() in storage_configs:
            self._optimal_buffer_size = storage_configs[storage_type.lower()]
        else:
            raise ValueError(f"Unknown storage type: {storage_type}. Use: ssd, nvme, enterprise, maximum")
    
    def set_custom_buffer_size(self, size_mb: float) -> None:
        """Set custom buffer size in megabytes"""
        self._optimal_buffer_size = int(size_mb * 1048576)  # Convert MB to bytes

    def update_capacity(self, new_capacity):
        """Update the target capacity for tracking only"""
        print(f"DEBUG: Interleaver.update_capacity called with {new_capacity:,} bytes (tracking only)", file=sys.stderr)
        super().update_capacity(new_capacity)
        old_buffer_size = getattr(self, '_entropy_buffer_size', 'None')
        self._entropy_buffer_size = new_capacity  # Update internal tracking
        print(f"DEBUG: Updated Interleaver._entropy_buffer_size from {old_buffer_size} to {new_capacity:,}", file=sys.stderr)

    # ----------------Interleaver-------------------
    @property
    def _page_size(self):
        """compute the shortest length of all files in the current group, so that all can be read from alternately"""
        # ----------------------------------------------
        if len(self._source_groups) == 0:
            return 0  # no pages no length

        if len(self._source_groups[0]) > 0:
            minimum_from_first_group = min(
                self._source_groups[0], key=lambda source: source._file_len
            )._file_len

        minimum_length = minimum_from_first_group
        return minimum_length

    """
    @_page_size.setter
    def _page_size(self, size):
        self.__page_size = size
    """

    # -----------------Interleaver--------------------------
    def add_result_file(self, filepathstring):  # implement
        # ----------------------------------
        source = Interleaver__Source(filepathstring)
        self._source_next_group.append(source)

    # ----------Interleaver-------------
    def count_uncommitted(self):  # implement
        # ----------------------------------
        return len(self._source_next_group)

    # ---------------Interleaver----------------------------
    def commit_added_result_files(self):  # implement
        # soft prereq: at least 2 files have been added
        # tip: a developer could subclass and modify commit_added_result_files to add a locally
        # generated stream to the group before adding the group
        # ------------------------------------------------------
        accum = 0
        for source in self._source_next_group:
            accum += source._file_len
        self._bytesSeen += accum
        self._source_groups.append(self._source_next_group)
        self._source_next_group = []

    # post: if a group is available and readable, the `_writerPipe` is given a "book" of interleaved bytes
    # ------------Interleaver----------------
    async def refresh(self):  # override
        """alternate across bytes from each task result, write alternated sequence to pipe and controller-view"""

        # ........................................
        # post: _source_groups either has a list of 2 or more results in the front of the queue
        #       or groups are removed until this condition has been satisfied or until empty
        async def ___refresh_source_groups():
            if len(self._source_groups) > 0:
                sources = self._source_groups[0]  # just treat head
                shortlist = [
                    source
                    for source in sources
                    if not source.hasPageAvailable(self._page_size)
                ]
                # prune from head source group
                for source_list_item in shortlist:
                    self._source_groups[0].remove(source_list_item)
                    del source_list_item  # deletes the underlying file

            # after pruning, it is possible there are less than 2 items
            # in which case the group is popped
            if len(self._source_groups) > 0:
                current_group = self._source_groups[0]

                if len(current_group) == 0:
                    self._source_groups.pop(0)  # empty pop
                elif len(current_group) < 2:  # dangling group has only one member
                    # SINGLE FILE FIX: Process single files instead of deleting them
                    # This ensures downloaded entropy always appears in UI even with small batches
                    single_file_group = self._source_groups.pop(0)
                    if single_file_group:
                        # Process the single file
                        single_source = single_file_group[0]
                        if single_source.hasPageAvailable(single_source._file_len):
                            # Read the entire file and write it to pipe
                            single_file_data = single_source.read(single_source._file_len)
                            written = await self._write_to_pipe(single_file_data)
                            
                            # Notify controller
                            to_ctl_cmd = {"cmd": "add_bytes", "hex": single_file_data[:written]}
                            self.to_ctl_q.put_nowait(to_ctl_cmd)
                            
                            # Update bytesInPipe
                            msg = {"bytesInPipe": len(self)}
                            self.to_ctl_q.put_nowait(msg)
                    
                    # Clean up the single file group
                    single_file_group.clear()

        # ........................................

        while True:
            await ___refresh_source_groups()  # ensure there are at least two results with at least length _page_size
            # at the head of _source_groups

            # [ viable source list (2+ members with all having at least a page of bytes) now at head ]
            if len(self._source_groups) > 0:
                self.pending = True
                pages = []

                # read the calculated page size from each file and add to a "pages" list
                for source in self._source_groups[0]:
                    pages.append(io.BytesIO(source.read(self._page_size)))
                    # await asyncio.sleep(0)  # ------- yield ---------

                # write the pages into a single book, alternating each byte across all pages
                book = io.BytesIO()
                # Optimize: Build much larger buffers before writing to pipe
                # This allows PipeWriter to use its large chunk capabilities efficiently
                # Large buffers are optimal for modern SSD performance
                bytes_written_to_book = 0
                # Use small fixed yield interval for UI responsiveness (not proportional to buffer size)
                async_yield_interval = 1024  # Yield every 1KB for smooth UI interaction
                
                for position in range(self._page_size):  # up to the shortest length of all results
                    for page in pages:  # read next byte from each page/result writing them alternately into the book
                        book.write(page.read(1))  # read,write
                        bytes_written_to_book += 1

                    # Yield frequently during buffer building for UI responsiveness
                    if bytes_written_to_book % async_yield_interval == 0:
                        await asyncio.sleep(0)  # Pure yield, no delay

                    # Write to pipe when we have a large optimal buffer, not frequently
                    if bytes_written_to_book >= self._optimal_buffer_size:
                        # Write large chunk to pipe for optimal performance
                        written = await self._write_to_pipe(book.getvalue())  # Convert memoryview to bytes for pickling
                        
                        # send hex serialized version to controller
                        randomBytesView = book.getvalue()
                        to_ctl_cmd = {
                            "cmd": "add_bytes",
                            "hex": randomBytesView[:written],
                        }
                        self.to_ctl_q.put_nowait(to_ctl_cmd)

                        # clear book from memory and start a new one
                        book.close()
                        book = io.BytesIO()
                        bytes_written_to_book = 0

                        # directly inform controller of any change in pipe
                        msg = {"bytesInPipe": len(self)}
                        self.to_ctl_q.put_nowait(msg)
                        
                # write remaining bytes that are less than optimal_buffer_size
                if bytes_written_to_book > 0:
                    written = await self._write_to_pipe(book.getvalue())  # Convert memoryview to bytes for pickling

                    # share with controller a view of the bytes written
                    randomBytesView = book.getvalue()
                    to_ctl_cmd = {"cmd": "add_bytes", "hex": randomBytesView[:written]}
                    self.to_ctl_q.put_nowait(to_ctl_cmd)

                for page in pages:
                    page.close()  # garbage collect pages (not really necessary in this case)
                self.pending = False
            await self._writerPipe.refresh()
            await asyncio.sleep(0.002)  # 2ms for responsive UI (was 0.01 = 10ms)
        # await self._flush_pipe()

    # ---------Interleaver-----------------
    def __del__(self):  # override
        """deletes Interleaver__source objects added to it"""
        # -------------------------------------
        # the deconstructor is called on every member of every subgroup
        for source_group in self._source_groups:
            source_group.clear()  # deletes underlying files
        super().__del__()

    def __len__(self):
        """Return the number of bytes currently buffered in the interleaver's writer."""
        return super().__len__()
