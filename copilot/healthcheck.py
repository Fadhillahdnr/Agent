"""Healthcheck container: python -m copilot.healthcheck api|worker|telegram"""
import sys
import time
import urllib.request


def main():
    kind = sys.argv[1]
    if kind == "api":
        urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=4).read()
    elif kind == "worker":
        from . import db
        hb = db.get_state("worker_heartbeat")
        if not hb:
            raise SystemExit("worker belum aktif")
        with db.conn() as c:
            age = c.execute("SELECT extract(epoch FROM now()-updated_at) a FROM index_state WHERE key='worker_heartbeat'").fetchone()["a"]
        if age > 120:
            raise SystemExit("heartbeat worker basi")
    elif kind == "telegram":
        import pathlib
        p = pathlib.Path("/tmp/telegram.heartbeat")
        if not p.exists() or time.time() - float(p.read_text()) > 90:
            raise SystemExit("heartbeat bot basi")


if __name__ == "__main__":
    main()
