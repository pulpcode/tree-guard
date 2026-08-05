"""Optional local CPU Provider for the frozen H2 BGE profile."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from treeguard.hashing import canonical_digest
from treeguard.models import CanonicalTree
from treeguard.retrieval_hybrid import (
    HybridNodeDocument,
    HybridQueryDocument,
    HybridRetrievalError,
    build_hybrid_node_documents,
    validate_hybrid_embedding_vector,
)
from treeguard.retrieval_hybrid_h2 import (
    EMBEDDING_DIMENSIONS,
    MAX_TOKENS,
    MODEL_ID,
    MODEL_REVISION,
    QUERY_INSTRUCTION,
    WEIGHTS_SHA256,
    H2EmbeddingIndex,
    H2EmbeddingProfile,
    H2QueryEmbedding,
    build_h2_embedding_index,
    build_h2_query_embedding,
)


REQUIRED_SNAPSHOT_FILES = (
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


class LocalEmbeddingProviderError(RuntimeError):
    """A local H2 runtime or output failed without exposing model text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class H2EmbeddingBackend(Protocol):
    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]: ...


class LocalBgeH2EmbeddingProvider:
    model_id = MODEL_ID
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(
        self,
        profile: H2EmbeddingProfile,
        backend: H2EmbeddingBackend,
    ) -> None:
        if (
            not isinstance(profile, H2EmbeddingProfile)
            or not callable(getattr(backend, "embed", None))
        ):
            raise LocalEmbeddingProviderError("H2_LOCAL_PROFILE_INVALID")
        self.profile = profile
        self._backend = backend
        self.inference_call_count = 0

    @classmethod
    def from_local_snapshot(
        cls,
        snapshot_dir: Path,
        *,
        batch_size: int,
    ) -> "LocalBgeH2EmbeddingProvider":
        artifact_hash = verify_local_h2_snapshot(snapshot_dir)
        profile = H2EmbeddingProfile.build(
            artifact_manifest_hash=artifact_hash,
            batch_size=batch_size,
        )
        backend = _TransformersBgeBackend(snapshot_dir)
        return cls(profile, backend)

    def embed_document_batch(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=False)

    def embed_query_batch(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return self._embed(texts, query=True)

    def _embed(
        self,
        texts: tuple[str, ...],
        *,
        query: bool,
    ) -> tuple[tuple[float, ...], ...]:
        if (
            not isinstance(texts, tuple)
            or not 1 <= len(texts) <= self.profile.batch_size
            or any(not _valid_text(text) for text in texts)
        ):
            raise LocalEmbeddingProviderError("H2_LOCAL_INPUT_INVALID")
        model_texts = (
            tuple(QUERY_INSTRUCTION + text for text in texts) if query else texts
        )
        self.inference_call_count += 1
        try:
            raw = self._backend.embed(model_texts)
            if not isinstance(raw, tuple) or len(raw) != len(texts):
                raise ValueError
            return tuple(validate_hybrid_embedding_vector(vector) for vector in raw)
        except (HybridRetrievalError, TypeError, ValueError):
            raise LocalEmbeddingProviderError("H2_LOCAL_OUTPUT_INVALID") from None


def embed_h2_documents(
    provider: LocalBgeH2EmbeddingProvider,
    documents: tuple[HybridNodeDocument, ...],
) -> tuple[tuple[float, ...], ...]:
    if (
        not isinstance(provider, LocalBgeH2EmbeddingProvider)
        or not isinstance(documents, tuple)
        or not documents
        or any(not isinstance(item, HybridNodeDocument) for item in documents)
    ):
        raise LocalEmbeddingProviderError("H2_LOCAL_PROVIDER_INVALID")
    vectors = []
    for offset in range(0, len(documents), provider.profile.batch_size):
        batch = documents[offset : offset + provider.profile.batch_size]
        vectors.extend(
            provider.embed_document_batch(
                tuple(document.to_model_text() for document in batch)
            )
        )
    return tuple(vectors)


def build_h2_index_with_provider(
    provider: LocalBgeH2EmbeddingProvider,
    tree: CanonicalTree,
) -> H2EmbeddingIndex:
    if not isinstance(provider, LocalBgeH2EmbeddingProvider):
        raise LocalEmbeddingProviderError("H2_LOCAL_PROVIDER_INVALID")
    documents = build_hybrid_node_documents(tree)
    vectors = embed_h2_documents(provider, documents)
    return build_h2_embedding_index(
        tree,
        documents,
        {
            document.node_id: vector
            for document, vector in zip(documents, vectors, strict=True)
        },
        provider.profile,
    )


def build_h2_query_embedding_with_provider(
    provider: LocalBgeH2EmbeddingProvider,
    document: HybridQueryDocument,
) -> H2QueryEmbedding:
    if not isinstance(provider, LocalBgeH2EmbeddingProvider) or not isinstance(
        document, HybridQueryDocument
    ):
        raise LocalEmbeddingProviderError("H2_QUERY_DOCUMENT_INVALID")
    vectors = provider.embed_query_batch((document.to_model_text(),))
    try:
        return build_h2_query_embedding(
            document,
            vectors[0],
            provider.profile,
        )
    except (HybridRetrievalError, IndexError, TypeError, ValueError):
        raise LocalEmbeddingProviderError("H2_LOCAL_OUTPUT_INVALID") from None


def verify_local_h2_snapshot(snapshot_dir: Path) -> str:
    if not isinstance(snapshot_dir, Path):
        raise LocalEmbeddingProviderError("H2_LOCAL_SNAPSHOT_INVALID")
    try:
        root = snapshot_dir.resolve(strict=True)
        if not root.is_dir() or root.name != MODEL_REVISION:
            raise ValueError
        files = []
        for name in REQUIRED_SNAPSHOT_FILES:
            path = root / name
            if not path.is_file():
                raise ValueError
            digest = _sha256_file(path)
            files.append({"name": name, "sha256": digest})
        weights = next(
            item["sha256"]
            for item in files
            if item["name"] == "model.safetensors"
        )
        if weights != WEIGHTS_SHA256:
            raise ValueError
    except (OSError, StopIteration, ValueError):
        raise LocalEmbeddingProviderError("H2_LOCAL_SNAPSHOT_INVALID") from None
    return canonical_digest(
        {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "files": files,
        }
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 2_000
        and not any(
            ord(character) < 9
            or 10 < ord(character) < 32
            or ord(character) == 127
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in value
        )
    )


class _TransformersBgeBackend:
    def __init__(self, snapshot_dir: Path) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(
                str(snapshot_dir),
                local_files_only=True,
                trust_remote_code=False,
            )
            self._model = AutoModel.from_pretrained(
                str(snapshot_dir),
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
            )
            if getattr(self._model.config, "hidden_size", None) != EMBEDDING_DIMENSIONS:
                raise ValueError
            self._model.to(device="cpu", dtype=torch.float32)
            self._model.eval()
            self._model.requires_grad_(False)
        except (ImportError, OSError, TypeError, ValueError):
            raise LocalEmbeddingProviderError("H2_LOCAL_RUNTIME_UNAVAILABLE") from None

    def embed(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
        try:
            encoded = self._tokenizer(
                list(texts),
                padding=True,
                truncation=True,
                max_length=MAX_TOKENS,
                return_tensors="pt",
            )
            encoded = {key: value.to("cpu") for key, value in encoded.items()}
            with self._torch.no_grad():
                output = self._model(**encoded)
                pooled = output.last_hidden_state[:, 0]
                normalized = self._torch.nn.functional.normalize(
                    pooled.to(dtype=self._torch.float32),
                    p=2,
                    dim=1,
                )
            rows = normalized.detach().cpu().tolist()
            return tuple(tuple(float(value) for value in row) for row in rows)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            raise LocalEmbeddingProviderError("H2_LOCAL_INFERENCE_FAILED") from None


__all__ = [
    "H2EmbeddingBackend",
    "LocalBgeH2EmbeddingProvider",
    "LocalEmbeddingProviderError",
    "build_h2_index_with_provider",
    "build_h2_query_embedding_with_provider",
    "embed_h2_documents",
    "verify_local_h2_snapshot",
]
