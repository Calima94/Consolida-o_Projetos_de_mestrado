"""TCP relay for Docker Desktop: published port -> port on the Docker VM.

    port_forward.py LISTEN:TARGET [LISTEN:TARGET ...]

Runs in a bridge-network container (see docker/compose.desktop.yaml). Every
connection to LISTEN is relayed to TARGET on the container's default gateway,
which is the Docker VM, where the host-network services listen. The bytes are
copied as they are, so HTTP and websockets pass through untouched.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import sys


def default_gateway() -> str:
    with open("/proc/net/route") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000":  # destination 0.0.0.0: the default route
                return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    raise SystemExit("no default route")


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


async def serve(listen: int, target: int, host: str) -> None:
    async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(host, target)
        except OSError as e:  # e.g. the web service is not up yet
            print(f":{listen} -> {host}:{target} unreachable: {e}", flush=True)
            writer.close()
            return
        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))

    server = await asyncio.start_server(relay, "0.0.0.0", listen)
    print(f"relay :{listen} -> {host}:{target}", flush=True)
    await server.serve_forever()


async def main(pairs: list[tuple[int, int]]) -> None:
    host = default_gateway()
    await asyncio.gather(*(serve(listen, target, host) for listen, target in pairs))


if __name__ == "__main__":
    pairs = [(int(a), int(b)) for a, b in (arg.split(":") for arg in sys.argv[1:])]
    if not pairs:
        raise SystemExit(__doc__)
    try:
        asyncio.run(main(pairs))
    except KeyboardInterrupt:  # docker compose stop / Ctrl+C
        pass
