"""FastEmbed (ONNX) embeddings — no PyTorch."""

from fastembed import TextEmbedding

# FastEmbed - lightweight ONNX-based embeddings (no PyTorch required).
#
# Built lazily: instantiating TextEmbedding downloads the ONNX model, and doing that
# at import time means merely importing this module hits the network.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_embedding_model = None


def get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(EMBEDDING_MODEL_NAME)
    return _embedding_model


def compute_embedding(text: str) -> list:
    """
    Computes embedding using FastEmbed (ONNX-based, no PyTorch).
    Returns a list of floats with 384 dimensions.
    """
    # Limitar o texto para evitar problemas de performance
    max_length = 512
    if len(text) > max_length * 4:
        text = text[:max_length * 4]

    # FastEmbed retorna um generator, pegamos o primeiro resultado
    embeddings = list(get_embedding_model().embed([text]))
    return embeddings[0].tolist()
