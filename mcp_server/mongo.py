from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("MONGO_DB_NAME", "job_scraper")
_COLLECTION_NAME = os.environ.get("MONGO_COLLECTION_NAME", "scrape_runs")

_client: Any = None


def get_collection() -> Any:
    global _client
    if _client is None:
        from pymongo import MongoClient  # deferred so import cost is zero when unused

        _client = MongoClient(MONGO_URI)
    return _client[_DB_NAME][_COLLECTION_NAME]


def insert_run(data: dict[str, Any]) -> str:
    """Insert a scrape run document. Returns the inserted _id as a string."""
    collection = get_collection()
    doc = {**data, "_created_at": datetime.now(UTC).isoformat()}
    result = collection.insert_one(doc)
    return str(result.inserted_id)


def get_latest_run() -> dict[str, Any] | None:
    """Return the most recent scrape run document, or None if none exist."""
    collection = get_collection()
    doc = collection.find_one(sort=[("_created_at", -1)])
    if doc is None:
        return None
    return {**doc, "_id": str(doc["_id"])}
