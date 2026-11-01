"""Persistent local ChromaDB retrieval backed by Vertex embeddings.

Website pages are downloaded only by the explicit refresh script. Normal voice,
Xiaozhi, and future mobile/web requests query this local persistent database.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from app.config import Settings
    from app.google_cloud import GoogleCloudService

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    source_id: str
    title: str
    text: str
    url: str
    source_type: str


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    text: str
    title: str
    url: str
    distance: float


def chunk_text(text: str, chunk_size: int = 1100, overlap: int = 180) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start + (chunk_size // 2):
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


class CollegeKnowledgeBase:
    """Local ChromaDB collection shared by all backend clients."""

    def __init__(self, settings: Settings, cloud: GoogleCloudService) -> None:
        self._settings = settings
        self._cloud = cloud

    def _collection(self):
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:
            raise RuntimeError("ChromaDB is not installed. Run .\\setup_venv.ps1.") from exc
        self._settings.knowledge_base_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(self._settings.knowledge_base_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return client.get_or_create_collection(
            name=self._settings.knowledge_base_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        if not self._settings.knowledge_base_enabled:
            return 0
        try:
            return int(self._collection().count())
        except Exception as exc:
            LOGGER.warning("Knowledge-base status unavailable: %s", exc)
            return 0

    def replace_documents(self, documents: Iterable[KnowledgeDocument]) -> int:
        """Replace the source corpus on an explicit administrator refresh."""

        collection = self._collection()
        existing_ids = collection.get(include=[]).get("ids", [])
        if existing_ids:
            collection.delete(ids=existing_ids)

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, str | int]] = []
        for document in documents:
            for index, chunk in enumerate(chunk_text(document.text)):
                ids.append(f"{document.source_id}-{index}")
                texts.append(chunk)
                metadatas.append(
                    {
                        "source_id": document.source_id,
                        "title": document.title,
                        "url": document.url,
                        "source_type": document.source_type,
                        "chunk": index,
                    }
                )
        if not texts:
            raise RuntimeError("Knowledge-base refresh produced no usable text.")
        # Website chunks can be close to the embedding-token limit. Small
        # batches are more reliable over a home network than a huge request.
        for start in range(0, len(texts), 4):
            end = start + 4
            vectors = self._embed_with_retry(texts[start:end], "RETRIEVAL_DOCUMENT")
            collection.upsert(ids=ids[start:end], documents=texts[start:end], metadatas=metadatas[start:end], embeddings=vectors)
        LOGGER.info("College knowledge base refreshed with %s ChromaDB chunks.", len(texts))
        return len(texts)

    def _embed_with_retry(self, texts: list[str], task_type: str) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return self._cloud.embed_texts(texts, task_type)
            except Exception as exc:
                last_error = exc
                LOGGER.warning("Vertex embedding batch failed (attempt %s/3): %s", attempt + 1, exc)
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        assert last_error is not None
        raise RuntimeError("Could not create Vertex embeddings after 3 attempts.") from last_error

    def retrieve(self, question: str) -> list[KnowledgeHit]:
        if not self._settings.knowledge_base_enabled or not question.strip() or self.count() == 0:
            return []
        try:
            vector = self._embed_with_retry([question], "RETRIEVAL_QUERY")[0]
            result = self._collection().query(
                query_embeddings=[vector],
                n_results=self._settings.knowledge_base_results,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            LOGGER.exception("College knowledge retrieval failed: %s", exc)
            return []
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[KnowledgeHit] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            if not isinstance(metadata, dict):
                continue
            source_id = str(metadata.get("source_id", ""))
            # Official pages repeat a large navigation menu in every chunk.
            # Give concise, source-attributed facts a modest rank preference so
            # a voice question gets the answer rather than website chrome.
            curated_bonus = 0.12 if source_id in {"svpcet-verified-facts", "project-facts"} else 0.0
            hits.append(
                KnowledgeHit(
                    str(text),
                    str(metadata.get("title", "Untitled source")),
                    str(metadata.get("url", "")),
                    max(0.0, float(distance) - curated_bonus),
                )
            )
        return sorted(hits, key=lambda item: item.distance)

    def context_for(self, question: str) -> str:
        remaining = self._settings.knowledge_base_max_context_chars
        blocks: list[str] = []
        for hit in self.retrieve(question):
            header = f"Source: {hit.title} ({hit.url})\n"
            body = hit.text[: max(0, remaining - len(header))]
            if not body:
                break
            blocks.append(header + body)
            remaining -= len(header) + len(body)
            if remaining <= 0:
                break
        return "\n\n---\n\n".join(blocks)


def curated_documents(project_root: Path) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for facts_path in sorted((project_root / "knowledge").glob("*.md")):
        documents.append(
            KnowledgeDocument(
                facts_path.stem.replace("_", "-"),
                f"Curated knowledge: {facts_path.stem.replace('_', ' ')}",
                facts_path.read_text(encoding="utf-8"),
                f"local://knowledge/{facts_path.name}",
                "curated",
            )
        )
    return documents
