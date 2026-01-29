import json
from pathlib import Path
from typing import List, Tuple, Dict
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import faiss

class RAGStore:
    def __init__(self, storage_dir: str = "./rag_data", emb_model: str = "all-MiniLM-L6-v2"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.documents: List[Dict] = []
        self.embedder = SentenceTransformer(emb_model)
        self.embedding_dim = self.embedder.get_sentence_embedding_dimension()
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.embeddings = np.zeros((0, self.embedding_dim), dtype="float32")
        self.tfidf = TfidfVectorizer(stop_words="english", max_features=20000)
        self.tfidf_matrix = None
        self._load()

    def _load(self):
        jsonp = self.storage_dir / "rag_store.json"
        faissp = self.storage_dir / "faiss.index"
        if jsonp.exists():
            data = json.loads(jsonp.read_text(encoding="utf-8"))
            self.documents = data
            texts = [d["text"] for d in self.documents]
            if texts:
                self.embeddings = np.array([self.embedder.encode(t, normalize_embeddings=True) for t in texts], dtype="float32")
                try:
                    if faissp.exists():
                        self.index = faiss.read_index(str(faissp))
                    else:
                        self.index = faiss.IndexFlatIP(self.embedding_dim)
                        if self.embeddings.shape[0] > 0:
                            self.index.add(self.embeddings)
                except Exception:
                    self.index = faiss.IndexFlatIP(self.embedding_dim)
                    if self.embeddings.shape[0] > 0:
                        self.index.add(self.embeddings)
                self.tfidf_matrix = self.tfidf.fit_transform(texts)

    def _save(self):
        jsonp = self.storage_dir / "rag_store.json"
        faissp = self.storage_dir / "faiss.index"
        jsonp.write_text(json.dumps(self.documents, indent=2), encoding="utf-8")
        try:
            faiss.write_index(self.index, str(faissp))
        except Exception:
            pass

    def add_documents(self, docs: List[Tuple[str, Dict]]):
        new_texts = []
        new_embs = []
        for text, meta in docs:
            if not text or not text.strip():
                continue
            self.documents.append({"text": text, "meta": meta})
            emb = self.embedder.encode(text, normalize_embeddings=True)
            new_embs.append(emb)
            new_texts.append(text)
        if new_embs:
            arr = np.array(new_embs, dtype="float32")
            self.index.add(arr)
            if self.embeddings.shape[0] == 0:
                self.embeddings = arr
            else:
                self.embeddings = np.vstack([self.embeddings, arr])
        texts = [d["text"] for d in self.documents]
        if texts:
            self.tfidf_matrix = self.tfidf.fit_transform(texts)
        self._save()

    def semantic_search(self, query: str, k: int = 5):
        if not self.documents:
            return []
        q_emb = self.embedder.encode(query, normalize_embeddings=True).astype("float32").reshape(1, -1)
        D, I = self.index.search(q_emb, k)
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            results.append({**self.documents[idx], "score": float(score), "method": "semantic"})
        return results

    def keyword_search(self, query: str, k: int = 5):
        if self.tfidf_matrix is None or not self.documents:
            return []
        qv = self.tfidf.transform([query])
        sims = cosine_similarity(qv, self.tfidf_matrix).flatten()
        idx = sims.argsort()[::-1][:k]
        return [{**self.documents[i], "score": float(sims[i]), "method": "keyword"} for i in idx]

    def search(self, query: str, k: int = 5, alpha: float = 0.7):
        if not self.documents:
            return []
        sem = self.semantic_search(query, k*2)
        key = self.keyword_search(query, k*2)
        combined = {}
        def add(item, weight):
            meta_id = item["meta"].get("path") or item["meta"].get("filename") or str(id(item))
            combined[meta_id] = combined.get(meta_id, 0) + weight * item["score"]
        for r in sem:
            add(r, alpha)
        for r in key:
            add(r, 1 - alpha)
        top = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:k]
        results = []
        for meta_id, score in top:
            for d in self.documents:
                if d["meta"].get("path") == meta_id or d["meta"].get("filename") == meta_id or str(id(d)) == meta_id:
                    results.append({**d, "score": float(score), "method": "hybrid"})
                    break
        return results
