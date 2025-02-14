from sentence_transformers import SentenceTransformer
import numpy as np

# Load embedding model
model = SentenceTransformer("all-mpnet-base-v2")

def generate_embedding(text: str):
    """Generate an embedding for a given text."""
    embedding = model.encode(text, normalize_embeddings=True)
    return np.array(embedding, dtype=np.float32).tolist()
