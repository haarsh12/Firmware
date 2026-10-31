"""Smoke-test a running voice WebSocket with real-time silent PCM frames.

This checks protocol and Cloud Speech streaming only. It deliberately sends no
speech, so the expected result is a graceful "no clear speech" completion.
"""

from __future__ import annotations

import argparse
import time

from websockets.sync.client import connect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/voice")
    parser.add_argument("--seconds", type=float, default=1.0)
    parser.add_argument("--turns", type=int, default=1)
    args = parser.parse_args()

    frame = bytes(3200)  # 100 ms of 16 kHz, 16-bit mono PCM.
    frame_count = max(1, round(args.seconds * 10))
    with connect(args.url, open_timeout=10, close_timeout=5) as socket:
        print(f"Connected: {args.url}")
        for turn in range(1, args.turns + 1):
            print(f"Turn {turn}")
            socket.send("START")
            print(f"<- {socket.recv(timeout=5)}")
            print(f"<- {socket.recv(timeout=5)}")
            for _ in range(frame_count):
                socket.send(frame)
                time.sleep(0.1)
            socket.send("STOP")
            print("-> STOP")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                message = socket.recv(timeout=5)
                print(f"<- {message}")
                if message == "VOICE_DONE":
                    break
            else:
                raise TimeoutError("Voice turn did not finish within 30 seconds.")
        return
    raise TimeoutError("Voice turn did not finish within 30 seconds.")


if __name__ == "__main__":
    main()
