#!/usr/bin/env python3
# server.py
# one implementation of a server to deliver from entropythief pipe
import asyncio
import select
import sys
import socket

class MyServer(asyncio.Protocol):
    """implement asyncio.Protocol to hook a callback for data received and manage multiple connections"""
    _transports = [] # transports added after each connection
    _ondata_cb = None
    _request_handler = None
    def __init__(self, ondata_cb):
        self._ondata_cb = ondata_cb
    def connection_made(self, transport):
        print("connection established", flush=True)
        self._transports.append(transport)
    def connection_lost(self, exc):
        print("DEBUG, CONNECTION LOST")
        print(exc)
        # identify which transport has been closed and remove from _transports
        closed_transport = None
        for transport in self._transports:
            if transport.is_closing():
                closed_transport = transport
                break
        self._transports.remove(closed_transport)
        print(f"Length of transports is now: {len(self._transports)}")
    def data_received(self, data):
        print("[server.py][MyServer::data_received]")
        self._ondata_cb(self, data)
    def eof_received(self):
        print("DEBUG, EOF RECEIVED")



async def main():
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: MyServer(handle_request_for_bytes), host="localhost", port="54321", reuse_address=True)
    # server = await asyncio.start_server(pilferer.server_on_connection, "127.0.0.1", "54321", reuse_address=True, start_serving=True)
    print(f"server is serving: {server.is_serving()}")
    while True:
        if select.select([sys.stdin,],[],[],0.0)[0]:
            theinput = sys.stdin.readline()
            if(theinput.strip() == "q"):
                break
        await asyncio.sleep(0.01)


# if __name__ == "__main__":
#     asyncio.run(main())

