# Xiaozhi portal — exact copy/paste checklist

## 1. Role tab

1. Open the agent **Configure** window.
2. Select **Role** and leave language as **Hindi** with the male voice you selected.
3. Turn on **Customize**.
4. Replace the existing Role Introduction with the entire content of `XIAOZHI_PORTAL_ROLE_PROMPT.md` (do not include its first Markdown title line).
5. Click **Save**.

## 2. Knowledge Base tab

1. Open **Extensions**.
2. In **Knowledge Base**, choose create new.
3. Name: `SVPCET MCP Knowledge Backup`
4. Description (copy exactly):

   `Short backup for the SVPCET assistant. The full verified college and project knowledge is searched live from the backend ChromaDB through MCP tools.`

5. Save the knowledge base.
6. Upload only `XIAOZHI_PORTAL_SHORT_KNOWLEDGE.md` from this folder. The portal permits one selected knowledge base; do not split facts across multiple portal knowledge bases.
7. Select this knowledge base for the agent, then save the agent configuration.

Do not upload Google credentials, `.env`, private MCP token, Wi-Fi password, or source-code files to Xiaozhi.

The backend ChromaDB is the master knowledge source for ESP32, Xiaozhi, and the future mobile/web app. Xiaozhi calls `search_college_knowledge` to query it; the portal backup document is deliberately short.

## 3. MCP tab

Leave the existing portal-generated MCP endpoint exactly as it is. It is read-only because the backend connects outward to it. The backend log line `Xiaozhi MCP bridge CONNECTED` confirms the connection.

## 4. Test phrases

- `Tumhe kisne banaya?`
- `Kaunsa AI model use karte ho?`
- `Dr Avinash Lambat kaun hain?`
- `E&TC ke HOD kaun hain?`
- `e-Yantra lab ke in-charge kaun hain?`
- `Light on karo.`
- `Fan band karo.`
- `Ghar ka status batao.`
