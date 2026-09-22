from __future__ import annotations

import numpy as np

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMS = 384


class Embedder:
    """Local sentence embeddings. No API key, no network at query time.

    fastembed downloads the ONNX weights once on first construction. By default
    it caches them under a system temp directory, which is not stable across
    reboots or container layers; set the FASTEMBED_CACHE_PATH environment
    variable (or pass cache_dir to TextEmbedding) to pin the cache to a fixed
    location, e.g. so a Docker build-time warm-up step is not discarded.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self._model.embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return (vecs / np.clip(norms, 1e-12, None)).astype(np.float32)
