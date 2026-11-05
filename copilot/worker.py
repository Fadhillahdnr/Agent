"""Worker indexing: polling berkala (inotify tidak andal pada mount Docker Desktop)."""
import logging
import time

from . import db
from .config import get_settings
from .embeddings import get_embedder
from .gitsync import sync_git
from .indexer import index_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")


def run_once() -> dict:
    stats = index_all()
    stats["git"] = sync_git()
    db.set_state("last_index", stats)
    return stats


def main():
    s = get_settings()
    for attempt in range(30):
        try:
            db.init_schema()
            break
        except Exception as e:
            log.warning("menunggu database: %s", e)
            time.sleep(2)
    get_embedder()
    last_req = None
    while True:
        try:
            run_once()
        except Exception:
            log.exception("siklus indexing gagal")
        db.set_state("worker_heartbeat", {"ok": True})
        waited = 0
        while waited < s.scan_interval:  # reindex manual dari admin memutus tunggu
            time.sleep(2)
            waited += 2
            db.set_state("worker_heartbeat", {"ok": True})
            req = db.get_state("reindex_request")
            if req and req["updated_at"] != last_req:
                last_req = req["updated_at"]
                break


if __name__ == "__main__":
    main()
