"""Storage: MongoDB when available, otherwise a local JSON file. Same interface for both."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("proofpay.storage")


class LocalJsonStore:
    name = "local JSON file"

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = {"milestones": {}}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data.setdefault("milestones", {})
            except (OSError, ValueError):
                log.warning("Could not read %s; starting with an empty store.", self.path)

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def list_milestones(self) -> list:
        with self._lock:
            return json.loads(json.dumps(list(self._data["milestones"].values())))

    def get(self, mid: str):
        with self._lock:
            doc = self._data["milestones"].get(mid)
            return json.loads(json.dumps(doc)) if doc else None

    def save(self, doc: dict) -> None:
        with self._lock:
            self._data["milestones"][doc["id"]] = json.loads(json.dumps(doc))
            self._flush()

    def clear(self) -> None:
        with self._lock:
            self._data["milestones"] = {}
            self._flush()


class MongoStore:
    name = "MongoDB"

    def __init__(self, uri: str, db_name: str):
        from pymongo import MongoClient

        self._client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        self._client.admin.command("ping")  # raises if unreachable
        self._col = self._client[db_name]["milestones"]

    def list_milestones(self) -> list:
        out = []
        for d in self._col.find({}):
            d["id"] = d.pop("_id")
            out.append(d)
        return out

    def get(self, mid: str):
        d = self._col.find_one({"_id": mid})
        if not d:
            return None
        d["id"] = d.pop("_id")
        return d

    def save(self, doc: dict) -> None:
        body = dict(doc)
        body["_id"] = body.pop("id")
        self._col.replace_one({"_id": body["_id"]}, body, upsert=True)

    def clear(self) -> None:
        self._col.delete_many({})


def make_store(settings):
    mode = settings.storage_mode
    if mode in ("auto", "mongo") and settings.mongodb_uri:
        try:
            store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
            log.info("Using MongoDB storage.")
            return store
        except Exception as exc:  # noqa: BLE001 - any connection problem
            if mode == "mongo":
                raise RuntimeError(f"STORAGE_MODE=mongo but MongoDB is unreachable: {exc}") from exc
            log.warning("MongoDB unavailable (%s). Falling back to the local JSON file.", exc)
    elif mode == "mongo":
        raise RuntimeError("STORAGE_MODE=mongo but MONGODB_URI is empty.")
    log.info("Using local JSON storage at %s", settings.local_data_file)
    return LocalJsonStore(settings.local_data_file)
