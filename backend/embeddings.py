from sentence_transformers import SentenceTransformer
import numpy as np
import logging
import os
import time

logger = logging.getLogger(__name__)

# Function to try loading the model with retries
def load_model_with_retries(model_name, max_retries=3, retry_delay=5):
    """
    Try loading the model with retries in case of network issues.
    
    Args:
        model_name: The name of the model to load
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        The loaded model or None if failed
    """
    for attempt in range(max_retries):
        try:
            logger.info(f"Loading embedding model {model_name} (attempt {attempt+1}/{max_retries})...")
            return SentenceTransformer(model_name)
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Failed to load model after {max_retries} attempts")
                return None

# Try to load the primary model
model = load_model_with_retries("all-mpnet-base-v2")

# If the primary model fails, try a smaller/simpler model as fallback
if model is None:
    logger.warning("Trying fallback models...")
    # Try a smaller model
    model = load_model_with_retries("paraphrase-MiniLM-L3-v2")  # Much smaller model
    
    # If that fails too, use a dummy embedder
    if model is None:
        logger.warning("All embedding models failed to load. Using dummy embedder.")
        
        # Define a dummy class that returns random embeddings
        class DummyEmbedder:
            def __init__(self):
                logger.warning("Using random embeddings as fallback!")
                
            def encode(self, text, normalize_embeddings=True):
                # Return a random embedding of the right dimensionality (384)
                import random
                return [random.uniform(-0.1, 0.1) for _ in range(384)]
        
        model = DummyEmbedder()

def generate_embedding(text: str):
    """Generate an embedding for a given text."""
    embedding = model.encode(text, normalize_embeddings=True)
    return np.array(embedding, dtype=np.float32).tolist()
