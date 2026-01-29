import faiss, numpy as np

class RAGStore:
    def __init__(self):
        self.texts = []
        self.embeddings = []
        self.index = None

    def add_documents(self, docs):
        for text, meta in docs:
            self.texts.append(text)
            emb = np.random.rand(768).astype("float32")
            self.embeddings.append(emb)
        self.index = faiss.IndexFlatL2(768)
        self.index.add(np.array(self.embeddings))

    def search(self, query, k=5):
        if not self.texts:
            return []
        q_emb = np.random.rand(768).astype("float32")
        D,I = self.index.search(np.array([q_emb]), k)
        return [{"text": self.texts[i]} for i in I[0]]

    def save(self):
        pass
