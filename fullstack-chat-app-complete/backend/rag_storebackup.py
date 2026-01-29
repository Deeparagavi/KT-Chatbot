import os
import json
import faiss
import numpy as np
from pathlib import Path
from typing import List, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RAGStore:
    """
    RAG store with hybrid (semantic + keyword) search and FAISS index for speed.
    """

    def __init__(self, storage_dir="rag_data"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # In-memory data
        self.documents: List[dict] = []

        # Sentence embedding model
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.embedding_dim = self.embedder.get_sentence_embedding_dimension()

        # TF-IDF model for keyword matching
        self.tfidf_vectorizer = TfidfVectorizer(stop_words="english")
        self.tfidf_matrix = None

        # FAISS index
        self.index = faiss.IndexFlatIP(self.embedding_dim)  # Inner Product (cosine)
        self.embeddings = np.zeros((0, self.embedding_dim), dtype="float32")

    # -----------------------------------------------------------
    # Add documents
    # -----------------------------------------------------------
    def add_documents(self, docs: List[Tuple[str, dict]]):
        new_texts, new_embs = [], []

        for text, meta in docs:
            if not text.strip():
                continue
            emb = self.embedder.encode(text, normalize_embeddings=True)
            self.documents.append({"text": text, "meta": meta})
            new_texts.append(text)
            new_embs.append(emb)

        if not new_embs:
            return

        new_embs = np.array(new_embs, dtype="float32")

        # Add to FAISS index
        self.index.add(new_embs)

        # Update stored embeddings
        if self.embeddings.shape[0] == 0:
            self.embeddings = new_embs
        else:
            self.embeddings = np.vstack([self.embeddings, new_embs])

        # Update TF-IDF
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform([d["text"] for d in self.documents])

        self.save_metadata()

    # -----------------------------------------------------------
    # Semantic search (via FAISS)
    # -----------------------------------------------------------
    def semantic_search(self, query: str, k=5):
        if len(self.documents) == 0:
            return []

        q_emb = self.embedder.encode(query, normalize_embeddings=True).astype("float32").reshape(1, -1)
        scores, indices = self.index.search(q_emb, k)
        results = []

        for idx, score in zip(indices[0], scores[0]):
            if idx < len(self.documents):
                results.append({
                    **self.documents[idx],
                    "score": float(score),
                    "method": "semantic"
                })

        return results

    # -----------------------------------------------------------
    # Keyword (TF-IDF) search
    # -----------------------------------------------------------
    def keyword_search(self, query: str, k=5):
        if self.tfidf_matrix is None or not self.documents:
            return []

        q_vec = self.tfidf_vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.tfidf_matrix).flatten()
        top_idx = sims.argsort()[-k:][::-1]

        return [
            {**self.documents[i], "score": float(sims[i]), "method": "keyword"}
            for i in top_idx
        ]

    # -----------------------------------------------------------
    # Hybrid search: semantic + keyword weighted merge
    # -----------------------------------------------------------
    def search(self, query: str, k=5, alpha=0.7):
        if not self.documents:
            return []

        semantic_results = self.semantic_search(query, k * 2)
        keyword_results = self.keyword_search(query, k * 2)

        combined_scores = {}

        def add_score(item, weight):
            meta_id = item["meta"].get("path") or item["meta"].get("filename")
            combined_scores[meta_id] = combined_scores.get(meta_id, 0) + weight * item["score"]

        for r in semantic_results:
            add_score(r, alpha)
        for r in keyword_results:
            add_score(r, 1 - alpha)

        top_sorted = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        results = []
        for meta_id, score in top_sorted:
            for d in self.documents:
                if d["meta"].get("path") == meta_id or d["meta"].get("filename") == meta_id:
                    results.append({**d, "score": float(score), "method": "hybrid"})
                    break

        return results

    # -----------------------------------------------------------
    # Persistence for metadata + FAISS index
    # -----------------------------------------------------------
    def _save(self):
        data = [{"text": d["text"], "meta": d["meta"]} for d in self.documents]
        with open(self.storage_dir / "rag_store.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        faiss.write_index(self.index, str(self.storage_dir / "faiss.index"))

    def _load(self):
        json_path = self.storage_dir / "rag_store.json"
        faiss_path = self.storage_dir / "faiss.index"

        if not json_path.exists():
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.documents = data
        texts = [d["text"] for d in data]
        self.embeddings = np.array(
            [self.embedder.encode(t, normalize_embeddings=True) for t in texts],
            dtype="float32"
        )

        # Rebuild or load FAISS index
        if faiss_path.exists():
            self.index = faiss.read_index(str(faiss_path))
        else:
            self.index.add(self.embeddings)

        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
