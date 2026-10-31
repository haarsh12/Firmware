"""Exercise the MAX98357A test WebSocket against a running backend."""

from __future__ import annotations

import argparse

from websockets.sync.client import connect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/speaker-test")
    parser.add_argument("--text", default="Hello world")
    args = parser.parse_args()

    received_pcm_bytes = 0
    expected_pcm_bytes: int | None = None
    with connect(args.url, open_timeout=10, close_timeout=10) as socket:
        print(f"<- {socket.recv(timeout=5)}")
        socket.send(f"SPEAK:{args.text}")
        while True:
            message = socket.recv(timeout=45)
            if isinstance(message, bytes):
                received_pcm_bytes += len(message)
                continue
            print(f"<- {message}")
            if message == "AUDIO_START":
                expected_pcm_bytes = int(socket.recv(timeout=5))
                print(f"<- expected bytes: {expected_pcm_bytes}")
            elif message == "AUDIO_END":
                break

    if not expected_pcm_bytes or received_pcm_bytes != expected_pcm_bytes:
        raise RuntimeError(
            f"Expected {expected_pcm_bytes} PCM bytes but received {received_pcm_bytes}."
        )
    print(f"Speaker TTS stream verified: {received_pcm_bytes} PCM bytes")


if __name__ == "__main__":
    main()
