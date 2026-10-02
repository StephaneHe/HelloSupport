"""RAG retrieval: Markdown sections -> embeddings -> Chroma (top-k) -> cross-encoder rerank (top-n).

The knowledge base is split by `##` section so that every hit can be cited as
`doc_id#section`. Embeddings are computed with a multilingual Sentence-Transformers
bi-encoder and stored in an embedded, persistent Chroma collection; the collection is
rebuilt only when the knowledge base content (or the embedding model) changes.
"""

import hashlib
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = PROJECT_ROOT / "data" / "kb"
CHROMA_DIR = PROJECT_ROOT / ".chroma"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
COLLECTION = "kb_sections"
# Cross-encoder logit below which a passage is flagged as off-topic. A coarse filter chosen
# empirically on this knowledge base (docs/BENCH.md, J1): useful hits scored >= -4.3, every
# section scored <= -9.2 for an off-topic query (Kafka). Vector search always returns
# neighbours; this flag lets the agent say "not covered" instead of answering from an
# unrelated passage. It is not a precision guarantee.
RELEVANCE_THRESHOLD = -5.0

# Keep the CLI output (and the MCP stdio channel later) free of download/loading progress bars.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")  # Chroma telemetry off


@dataclass
class Chunk:
    doc_id: str  # file name, e.g. postgres_connection.md
    section: str  # `##` heading, e.g. Service status
    text: str  # "<doc title> - <section>\n<body>", the doc title gives context to the section

    @property
    def chunk_id(self) -> str:
        return f"{self.doc_id}#{self.section}"


@dataclass
class Hit:
    doc_id: str
    section: str
    text: str
    score: float  # cosine similarity from the bi-encoder (ranking signal, not a probability)
    rerank_score: float  # cross-encoder relevance logit (higher is better)
    vector_rank: int  # 1-based rank before reranking
    relevant: bool  # rerank_score >= RELEVANCE_THRESHOLD

    def to_dict(self) -> dict:
        return asdict(self)


def chunk_markdown(path: Path) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", text, flags=re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    chunks = []
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = part.partition("\n")
        chunks.append(Chunk(path.name, heading.strip(), f"{title} - {heading.strip()}\n{body.strip()}"))
    return chunks


def load_chunks(kb_dir: Path = KB_DIR) -> list[Chunk]:
    return [c for p in sorted(kb_dir.glob("*.md")) for c in chunk_markdown(p)]


def pick_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class Retriever:
    def __init__(self, kb_dir: Path = KB_DIR, chroma_dir: Path = CHROMA_DIR, device: str | None = None):
        # Heavy imports are local so that the CLI and the tests stay fast when RAG is not used.
        import chromadb
        from sentence_transformers import CrossEncoder, SentenceTransformer

        self.device = device or pick_device()
        self.embedder = SentenceTransformer(EMBED_MODEL, device=self.device)
        self.reranker = CrossEncoder(RERANK_MODEL, device=self.device)
        self.chunks = {c.chunk_id: c for c in load_chunks(kb_dir)}
        client = chromadb.PersistentClient(path=str(chroma_dir))
        self.collection, self.rebuilt = self._sync_collection(client)
        # Warm-up: the first CUDA call compiles/loads kernels (~2-3 s); keep it out of query latency.
        self.search("warm-up", top_k=1, top_n=1)

    def _kb_fingerprint(self) -> str:
        h = hashlib.sha256(EMBED_MODEL.encode())
        for cid in sorted(self.chunks):
            h.update(cid.encode() + self.chunks[cid].text.encode())
        return h.hexdigest()[:16]

    def _sync_collection(self, client):
        fingerprint = self._kb_fingerprint()
        try:
            col = client.get_collection(COLLECTION)
            if (col.metadata or {}).get("fingerprint") == fingerprint:
                return col, False
            client.delete_collection(COLLECTION)
        except Exception:  # collection does not exist yet
            pass
        col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine", "fingerprint": fingerprint})
        ids = list(self.chunks)
        docs = [self.chunks[i].text for i in ids]
        vectors = self.embedder.encode(docs, normalize_embeddings=True).tolist()
        metas = [{"doc_id": self.chunks[i].doc_id, "section": self.chunks[i].section} for i in ids]
        col.add(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
        return col, True

    def search(self, query: str, top_k: int = 5, top_n: int = 2) -> list[Hit]:
        """Vector search for `top_k` candidates, rerank them with the cross-encoder, keep `top_n`."""
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        qvec = self.embedder.encode([query], normalize_embeddings=True).tolist()
        res = self.collection.query(query_embeddings=qvec, n_results=min(top_k, len(self.chunks)))
        candidates = []
        for rank, (cid, dist) in enumerate(zip(res["ids"][0], res["distances"][0]), start=1):
            c = self.chunks[cid]
            candidates.append((rank, c, 1.0 - dist))  # Chroma cosine distance = 1 - cosine similarity
        scores = self.reranker.predict([(query, c.text) for _, c, _ in candidates])
        hits = [
            Hit(c.doc_id, c.section, c.text, round(sim, 4), round(float(s), 4), rank, float(s) >= RELEVANCE_THRESHOLD)
            for (rank, c, sim), s in zip(candidates, scores)
        ]
        hits.sort(key=lambda h: h.rerank_score, reverse=True)
        return hits[:top_n] if top_n else hits
