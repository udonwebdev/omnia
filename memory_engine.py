import time
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions

class MemoryEngine:
    """Manages continuous ingestion and retrieval of browsing context and user activity."""

    def __init__(self, persist_dir: str = "./omnia_memory"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Default lightweight local sentence-transformer embedding model
        self.embed_fn = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name="web_context",
            embedding_function=self.embed_fn
        )

    def store_tab_context(self, tab_id: int, url: str, title: str, content: str) -> None:
        """Stores or updates active tab content in vector memory."""
        doc_id = f"tab_{tab_id}_{int(time.time())}"
        metadata = {
            "tab_id": tab_id,
            "url": url,
            "title": title,
            "timestamp": time.time()
        }
        # Truncate content to avoid vector overhead
        sanitized_doc = f"Page Title: {title}\nURL: {url}\nPage Content: {content[:3000]}"
        
        self.collection.add(
            documents=[sanitized_doc],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def search_context(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Finds most relevant recent browsing sessions matching natural language commands."""
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )
        
        hits = []
        if results and results["documents"]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                hits.append({
                    "title": meta.get("title"),
                    "url": meta.get("url"),
                    "timestamp": meta.get("timestamp"),
                    "snippet": doc[:300]
                })
        return hits

memory = MemoryEngine()
