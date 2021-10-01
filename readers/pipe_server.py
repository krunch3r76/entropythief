#!/usr/bin/env python3
# standard dependencies
import asyncio
import select
import sys
from datetime import datetime

# local dependencies
from pipe_reader import PipeReader
from server import MyServer

class PipeReaderServer(PipeReader):
    # description: read requested number of bytes and send over the server transport
    # pre: msg is a string convertible to an whole number
    # in: handle to a server object, message
    # out: none
    # post: none
    def handle_message_from_client(self, myServer, msg):
        count_of_random_bytes_requested = int.from_bytes(msg, "big")
        print(f"received request for {count_of_random_bytes_requested} bytes")
        for transport in myServer._transports:
            if not transport.is_closing():
                print(f"writing to client for {count_of_random_bytes_requested}")
                temp = self.read(count_of_random_bytes_requested)
                transport.write(temp)
                # transport.write(self.read(count_of_random_bytes_requested) )
                print("written")
                # print(f"written at {str(datetime.now())}")











# MyServer constructor takes a callable with signature (myServer, msg)
async def main():
    loop = asyncio.get_running_loop()
    pipeReaderServer = PipeReaderServer()
    host=None
    # host="192.168.223.129"
    port="54321"
    server = await loop.create_server(lambda: MyServer(pipeReaderServer.handle_message_from_client), host=host, port=port, reuse_address=True)
    # server = await loop.create_server(lambda: MyServer(handle_request_for_bytes), host="localhost", port="54321", reuse_address=True)
    print(f"server is serving: {server.is_serving()} on {host}:{port}")
    while True:
        await asyncio.sleep(0.01)
        if select.select([sys.stdin,],[],[],0.0)[0]:
            theinput = sys.stdin.readline()
            if(theinput.strip() == "q"):
                break








if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        task = loop.create_task(main() )
        loop.run_until_complete(task)
        pending=asyncio.all_tasks()
        for task in pending:
            task.cancel()
        group = asyncio.gather(*pending, return_exceptions=True)
        loop.run_until_complete(group)
        print(group)
        loop.close()
    except KeyboardInterrupt:
        print("--------------------keyboard interrupt")
    except Exception as e:
        print(f"+++++++++++++++ exception {e}")

