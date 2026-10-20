#!/usr/bin/env python3
"""Download the neural models into $MODELS_DIR (default /models) at image build time;
TIRA runs offline. Kept outside /app so a mounted working copy does not hide them."""

import os
from pathlib import Path

from huggingface_hub import snapshot_download

MODELS = {
    "mmarco-mMiniLMv2-L12-H384-v1": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
    "multilingual-e5-small": "intfloat/multilingual-e5-small",
    "multilingual-e5-base": "intfloat/multilingual-e5-base",
}
WEIGHT_PATTERNS = ["*.json", "*.txt", "*.model", "*.safetensors", "sentencepiece*", "1_Pooling/*", "modules.json"]


def main() -> None:
    target = Path(os.environ.get("MODELS_DIR", "/models"))
    for name, repository in MODELS.items():
        snapshot_download(repository, local_dir=target / name, allow_patterns=WEIGHT_PATTERNS)
        print(f"{repository} -> {target / name}")


if __name__ == "__main__":
    main()
