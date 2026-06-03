import json
import re
from pathlib import Path
from collections import defaultdict
from rank_bm25 import BM25Okapi

CHUNKS_PATH = Path("data/processed/KDB/chunks_hybrid/chunks.jsonl")
INDEX_PATH = Path("data/processed/VDB/faiss.index")
META_PATH = Path("data/processed/VDB/chunk_metadata.json")
CONFIG_PATH = Path("data/processed/VDB/build_config.json")

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
TOP_K_DENSE = 20
TOP_K_BM25 = 20
TOP_K_FINAL = 3
RRF_K = 60

# General IR guidance query — always blended in to ensure coverage beyond technique-specific hits
_IR_GUIDANCE_QUERY = (
    "OT ICS incident response containment investigation recovery "
    "industrial control system mitigation validation forensics"
)

_STOPWORDS = {
    "the","and","of","to","in","a","is","for","on","that","with","as","are","by",
    "this","be","or","an","from","at","it","we","was","which","can","have","has",
    "their","will","not","they","also","these","may","our","into","than","about",
    "all","its","been","were","but","should","how","if","when","more","such",
    "there","other","then","any","over","do","up","no","out","so","use","would",
    "could","after","each","through","during","before","between","both","only",
    "own","same","too","very","just","because","most",
}

def load_chunks():
    rows = []
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def load_faiss_and_config():
    import faiss
    index = faiss.read_index(str(INDEX_PATH))
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return index, config

def tokenise(text: str):
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]

def build_bm25_index(corpus_texts):
    tokenised = [tokenise(t) for t in corpus_texts]
    return BM25Okapi(tokenised)

def bm25_search(query, bm25, n=TOP_K_BM25):
    q_tokens = tokenise(query)
    if not q_tokens:
        return []
    scores = bm25.get_scores(q_tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:n]
    return ranked

def dense_search(query, model, faiss_index, n=TOP_K_DENSE):
    q_vec = model.encode([QUERY_PREFIX + query], normalize_embeddings=True).astype("float32")
    scores, idxs = faiss_index.search(q_vec, n)
    return [(int(idx), float(sc)) for idx, sc in zip(idxs[0], scores[0]) if idx >= 0]

def rrf_fuse(ranked_lists, k=RRF_K):
    rrf_scores = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (doc_idx, _) in enumerate(ranked, start=1):
            rrf_scores[doc_idx] += 1.0 / (k + rank)
    return sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    def __init__(self):
        self.chunks = load_chunks()
        self.texts = [c.get("text", "") for c in self.chunks]
        self.bm25 = build_bm25_index(self.texts)

        self.faiss_index, self.config = load_faiss_and_config()

        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(self.config["model_name"])

    def search(self, query: str, top_k: int = TOP_K_FINAL) -> list[dict]:
        """
        Blended retrieval strategy:
        - Run full hybrid search (dense + BM25) on the primary technique query.
        - Run a second hybrid search on a general IR-guidance query.
        - Reserve up to 1 slot (out of top_k) for a unique IR-guidance hit not
          already covered by the primary results, ensuring broad coverage even
          when top_k=3.
        """
        # ── Primary search ────────────────────────────────────────────────
        primary_results = self._hybrid_search(query, top_k=max(top_k + 5, 10))

        # ── Secondary IR guidance search ──────────────────────────────────
        secondary_results = self._hybrid_search(_IR_GUIDANCE_QUERY, top_k=10)

        # ── Merge: keep top (top_k - 1) primary + 1 unique secondary slot ─
        primary_ids = {r["chunk_idx"] for r in primary_results}
        secondary_unique = [r for r in secondary_results if r["chunk_idx"] not in primary_ids]

        merged = primary_results[: max(top_k - 1, 1)]
        if secondary_unique and len(merged) < top_k:
            merged.append(secondary_unique[0])

        # Re-rank merged list by rrf_score descending, assign new ranks
        merged.sort(key=lambda x: x["rrf_score"], reverse=True)
        final = merged[:top_k]
        for rank, r in enumerate(final, start=1):
            r["rank"] = rank

        return final

    def _hybrid_search(self, query: str, top_k: int) -> list[dict]:
        """Run dense + BM25 hybrid search for a single query."""
        dense_hits = dense_search(query, self.model, self.faiss_index, TOP_K_DENSE)
        bm25_hits  = bm25_search(query, self.bm25, TOP_K_BM25)
        fused = rrf_fuse([dense_hits, bm25_hits], k=RRF_K)[:top_k]

        results = []
        for rank, (chunk_idx, rrf_score) in enumerate(fused, start=1):
            ch = self.chunks[chunk_idx]
            results.append({
                "rank":          rank,
                "chunk_idx":     chunk_idx,
                "rrf_score":     round(rrf_score, 6),
                "doc_id":        ch.get("doc_id", ""),
                "source_org":    ch.get("source_org", ""),
                "category":      ch.get("category", ""),
                "technique_id":  ch.get("technique_id", ""),
                "attack_classes":ch.get("attack_classes", []),
                "word_count":    ch.get("word_count", 0),
                "text":          ch.get("text", ""),
            })
        return results


if __name__ == "__main__":
    retriever = HybridRetriever()
    query = "adversary-in-the-middle ICS network attack detection"
    hits = retriever.search(query, top_k=3)
    print(f"Top-{len(hits)} results for query: {query}")
    for i, r in enumerate(hits, 1):
        print(f"#{i} {r['source_org']} {r['doc_id']} rrf={r['rrf_score']:.6f}")
