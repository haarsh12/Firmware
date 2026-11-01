"""Non-destructive MCP compatibility probe for the local Xiaozhi endpoint."""

from __future__ import annotations

import argparse
import json

import httpx


def call(client: httpx.Client, url: str, request_id: int, method: str, params: dict | None = None) -> dict:
    response = client.post(url, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    with httpx.Client(headers={"X-Xiaozhi-Key": args.key}, timeout=10) as client:
        print(json.dumps(call(client, args.url, 1, "initialize", {"protocolVersion": "2025-03-26"}), indent=2))
        print(json.dumps(call(client, args.url, 2, "tools/list"), indent=2))


if __name__ == "__main__":
    main()
