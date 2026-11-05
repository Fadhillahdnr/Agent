"""Embedding: fastembed (multibahasa, lokal) atau hash (deterministik, untuk tes/offline)."""
import hashlib
import logging
import re

import numpy as np

from .config import get_settings

log = logging.getLogger(__name__)
_STOP = set("yang dan di ke dari untuk dengan pada ini itu apa bagaimana adalah the is are of to in for and a an how what where which do does".split())


def tokenize(text: str) -> list[str]:
    """Token pencarian: kata utuh + pecahan camelCase/snake_case, huruf kecil."""
    out = []
    for w in re.findall(r"[A-Za-z0-9]+", text):
        lw = w.lower()
        out.append(lw)
        parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+", w)
        if len(parts) > 1:
            out.extend(p.lower() for p in parts)
    return out


def query_tokens(text: str) -> list[str]:
    return [t for t in dict.fromkeys(tokenize(text)) if t not in _STOP and len(t) > 1]


class HashEmbedder:
    name = "hash"

    def __init__(self, dim: int):
        self.dim = dim

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.zeros(self.dim, dtype=np.float32)
            for tok in tokenize(t):
                h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
                v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out


class FastEmbedder:
    name = "fastembed"

    def __init__(self, model: str, dim: int):
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model_name=model, cache_dir="/opt/models" if _exists("/opt/models") else None)
        self.dim = dim
        probe = next(iter(self.model.embed(["probe"])))
        if len(probe) != dim:
            raise RuntimeError(f"EMBEDDING_DIM={dim} tidak cocok dengan model ({len(probe)})")

    def embed(self, texts):
        return [v.tolist() for v in self.model.embed(texts, batch_size=32)]


def _exists(p):
    import os
    return os.path.isdir(p)


_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        s = get_settings()
        _embedder = HashEmbedder(s.embedding_dim) if s.embedding_provider == "hash" else FastEmbedder(s.embedding_model, s.embedding_dim)
        log.info("embedder: %s", _embedder.name)
    return _embedder
