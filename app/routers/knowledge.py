"""Read-only API for the local college/project knowledge base."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter(prefix="/knowledge", tags=["knowledge-base"])


@router.get("/status")
async def knowledge_status(request: Request) -> dict[str, object]:
    knowledge_base = request.app.state.knowledge_base
    count = await asyncio.to_thread(knowledge_base.count)
    return {
        "enabled": request.app.state.settings.knowledge_base_enabled,
        "chunks": count,
        "ready": count > 0,
        "refresh_command": ".\\venv\\Scripts\\python.exe .\\scripts\\refresh_college_knowledge.py",
    }


@router.get("/search")
async def knowledge_search(
    request: Request,
    query: str = Query(min_length=2, max_length=500),
) -> dict[str, object]:
    knowledge_base = request.app.state.knowledge_base
    hits = await asyncio.to_thread(knowledge_base.retrieve, query)
    if not hits:
        raise HTTPException(status_code=404, detail="No local knowledge-base results. Refresh the corpus first.")
    return {
        "query": query,
        "results": [
            {"title": hit.title, "url": hit.url, "text": hit.text, "distance": round(hit.distance, 4)}
            for hit in hits
        ],
    }
