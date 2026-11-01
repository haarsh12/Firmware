# Xiaozhi Cloud configuration

This folder is additive. The existing Google Vertex, Google Speech, Google TTS, manual ESP32 microphone firmware, and relay APIs remain in place.

## Official Xiaozhi Cloud connection

The portal-generated `wss://api.xiaozhi.me/mcp/?token=...` address is
read-only by design. It is **not** a place to paste this backend's URL. It is
the remote socket that this local backend connects to outward.

1. Copy the portal address.
2. Place it only in local `.env` as `XIAOZHI_CLOUD_MCP_URL=...`.
3. Start `new_backend` and wait for `Xiaozhi MCP bridge CONNECTED`.
4. In the portal, click the refresh icon beside **Endpoint Status**. It should
   change from **Not Connected** to **Connected**.

At present the bridge has already connected successfully. Do not paste another
address into the read-only portal field; just use its refresh icon to update the
display.

No Cloudflare tunnel is required for this official WSS connection.

## Security first

The WSS token previously pasted into chat is a bearer credential and must be revoked/regenerated in Xiaozhi before use. Never paste replacement tokens into source code, screenshots, chat, or Git.

Set a new, private local key in `.env` instead:

```dotenv
XIAOZHI_MCP_ENABLED=true
XIAOZHI_MCP_SHARED_SECRET=replace-with-a-long-random-private-value
XIAOZHI_MCP_ALLOW_UNAUTHENTICATED=false
```

## Backend tools

Endpoint: `POST /xiaozhi/mcp`

| MCP tool | Physical action |
| --- | --- |
| `set_light({"state": true/false})` | Relay 1: light on/off |
| `set_fan({"state": true/false})` | Relay 2: fan on/off |
| `get_home_status()` | Read-only relay, sensor, and board status |

Every tool request is logged in the `new_backend` terminal. Relay commands use the existing `/ws/relay` ESP32 connection—the same pathway used by the Google/Vertex voice workflow.

## Test locally first

Start the backend and relay ESP32. Then run:

```powershell
cd D:\home_ss\new_backend
& 'C:\Users\LOQ\AppData\Local\Programs\Python\Python311\python.exe' -m xiaozhi_connect.mcp_probe --url http://127.0.0.1:8000/xiaozhi/mcp --key 'YOUR_PRIVATE_KEY'
```

It must list the three tools above and does **not** toggle a relay.

## Simplest public test URL (Windows)

Run this in a second PowerShell window:

```powershell
cd D:\home_ss\new_backend
.\xiaozhi_connect\start_public_test_tunnel.ps1
```

It starts the backend if necessary and prints a temporary `https://...trycloudflare.com` URL. Append `/xiaozhi/mcp?key=YOUR_PRIVATE_KEY` to that URL before adding it to the portal. The URL changes every time the tunnel stops; this is a test-only connection.

## Optional direct HTTP MCP test endpoint

`/xiaozhi/mcp` remains available as an optional direct HTTP MCP test endpoint.
It is not used by the portal-generated WSS endpoint. If another MCP client
needs to call this PC directly, Xiaozhi Cloud cannot reach `localhost` or a
private `192.168.x.x` / `172.20.x.x` laptop address, so publish it through a
public HTTPS reverse proxy/tunnel, for example:

```text
https://your-public-host.example/xiaozhi/mcp
```

In **Agent → Configure → Extensions → MCP Endpoint**, add that public endpoint using the portal's supported HTTP/HTTPS transport. Configure the `X-Xiaozhi-Key` header if the portal supports custom headers. Otherwise use the public URL with `?key=YOUR_PRIVATE_KEY` appended; it must be HTTPS and must never be shared.

Do not use the console-generated `wss://api.xiaozhi.me/...` URL as this PC's endpoint: it is a Xiaozhi-side bearer credential, not a public address for the backend.

If the portal only accepts WSS or cannot send a custom header, it needs a Xiaozhi transport adapter. Do not expose an unauthenticated public MCP endpoint just to test it.

## Role Introduction prompt

Paste this into **Role → Role Introduction**:

```text
# Role: GharSathi, a calm Hindi smart-home companion

You are GharSathi: a mature, calm, respectful male Hindi voice assistant for a home. Speak naturally in Hindi/Hinglish, briefly and clearly. Be warm, patient, practical, and honest. Use short sentences suitable for a speaker.

## Home controls
- Relay 1 controls the light. Relay 2 controls the fan.
- When the user explicitly asks to turn a light or fan on/off, call set_light or set_fan exactly once.
- Use true only for on and false only for off.
- For a question such as "is the light on?", call get_home_status; do not change a relay.
- Confirm an action only after the tool says it succeeded. Never pretend an action happened.

## Conversation style
- If an instruction is ambiguous, ask one short clarification.
- Respect privacy; do not invent sensor data, internet facts, or completed physical actions.
- For dangerous or irreversible actions ask confirmation. Light/fan on/off does not require extra confirmation.

Useful phrases: "Bilkul, main check karta hun.", "Theek hai, light on kar raha hun.", "Koi baat nahi, main madad ke liye yahin hun."
```

## Knowledge base

Create it with this name:

```text
GharSathi Home Guide
```

Description:

```text
Home assistant facts: relay mapping, safe operating rules, device availability, and response expectations for the GharSathi smart-home agent.
```

Add `knowledge_base.md` as its first document, select it in Extensions, then save the agent.
