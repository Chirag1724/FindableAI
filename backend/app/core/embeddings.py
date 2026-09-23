import hashlib
import logging
import math
from collections.abc import Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536


def _deterministic_fallback_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    Generate a deterministic, unit-normalized float vector of length `dim`
    derived from SHA-256 hashes of the input text tokens.
    Used for local development, CI/CD, and offline testing without paid API credits.
    """
    if not text:
        return [0.0] * dim

    words = text.lower().split()
    vector = [0.0] * dim

    for i, word in enumerate(words):
        # Generate hash bytes for each token
        h = hashlib.sha256(f"{word}_{i % 64}".encode()).digest()
        # Distribute hash values across vector dimensions
        for byte_idx, b in enumerate(h):
            target_dim = (i * 32 + byte_idx) % dim
            vector[target_dim] += (b - 128.0) / 128.0

    # Calculate L2 norm for cosine normalization
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0.0:
        vector = [x / norm for x in vector]
    else:
        vector[0] = 1.0

    return vector


async def get_embedding(text: str) -> list[float]:
    """
    Generate a 1536-dimensional embedding vector for a single text string.
    Uses OpenAI/LiteLLM if OPENAI_API_KEY is configured; otherwise uses deterministic fallback.
    """
    cleaned = text.strip()
    if not cleaned:
        return [0.0] * EMBEDDING_DIM

    if settings.OPENAI_API_KEY:
        try:
            import litellm

            response = await litellm.aembedding(
                model="text-embedding-3-small",
                input=[cleaned],
                api_key=settings.OPENAI_API_KEY,
            )
            raw_emb = response.data[0]["embedding"]
            return [float(x) for x in raw_emb]
        except Exception as e:
            logger.warning("LiteLLM embedding failed, falling back to deterministic vector: %s", e)

    return _deterministic_fallback_embedding(cleaned)


async def get_embeddings_batch(texts: Sequence[str]) -> list[list[float]]:
    """
    Generate 1536-dimensional embeddings for a batch of text strings.
    """
    if not texts:
        return []

    if settings.OPENAI_API_KEY:
        try:
            import litellm

            cleaned_texts = [t.strip() or " " for t in texts]
            response = await litellm.aembedding(
                model="text-embedding-3-small",
                input=cleaned_texts,
                api_key=settings.OPENAI_API_KEY,
            )
            return [[float(x) for x in item["embedding"]] for item in response.data]
        except Exception as e:
            logger.warning("Batch LiteLLM embedding failed, using deterministic fallback: %s", e)

    return [_deterministic_fallback_embedding(t.strip()) for t in texts]
