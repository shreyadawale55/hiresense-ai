"""PyTorch models for HireSense AI training and inference.

The training pipeline still centers on a TF-IDF classifier for stability, but
the architecture is modernized, checkpointable, and compatible with the
semantic scoring layer used by the inference service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import structlog
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = structlog.get_logger(__name__)


class SemanticEmbedder:
    """Optional SentenceTransformers wrapper used for semantic experiments."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self.embedding_dim = 384
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self.model = SentenceTransformer(model_name)
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info("Loaded SentenceTransformer", model_name=model_name, embedding_dim=self.embedding_dim)
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("SentenceTransformer unavailable, falling back to zeros", error=str(exc))

    def encode(self, texts: list[str]) -> np.ndarray:
        if self.model is None:
            return np.zeros((len(texts), self.embedding_dim), dtype=np.float32)
        return self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class ResidualBlock(nn.Module):
    """Light residual block for classifier bottlenecks."""

    def __init__(self, dim: int, dropout: float = 0.3):
        super().__init__()
        self.block = nn.Sequential(
            nn.Linear(dim, dim),
            nn.LayerNorm(dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim, dim),
            nn.LayerNorm(dim),
        )
        self.activation = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.activation(x + self.block(x))


class FusionScorerNet(nn.Module):
    """Optional dual-path model for semantic + TF-IDF fusion."""

    def __init__(
        self,
        semantic_dim: int = 384,
        tfidf_dim: int = 5000,
        num_categories: int = 10,
        hidden_dims: Optional[list[int]] = None,
        dropout: float = 0.3,
    ):
        super().__init__()
        hidden_dims = hidden_dims or [1024, 512, 256]

        self.semantic_encoder = nn.Sequential(
            nn.Linear(semantic_dim, hidden_dims[0]),
            nn.LayerNorm(hidden_dims[0]),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.tfidf_encoder = nn.Sequential(
            nn.Linear(tfidf_dim, hidden_dims[0]),
            nn.LayerNorm(hidden_dims[0]),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        fusion_layers: list[nn.Module] = []
        fusion_in = hidden_dims[0] * 2
        for hidden_dim in hidden_dims:
            fusion_layers.extend(
                [
                    nn.Linear(fusion_in, hidden_dim),
                    nn.LayerNorm(hidden_dim),
                    nn.GELU(),
                    nn.Dropout(dropout),
                ]
            )
            fusion_in = hidden_dim

        self.fusion = nn.Sequential(*fusion_layers)
        self.classifier = nn.Linear(hidden_dims[-1], num_categories)
        self.similarity_head = nn.Linear(hidden_dims[-1], 1)

    def forward(self, semantic_emb: torch.Tensor, tfidf_features: torch.Tensor) -> Dict[str, torch.Tensor]:
        semantic_out = self.semantic_encoder(semantic_emb)
        tfidf_out = self.tfidf_encoder(tfidf_features)
        fused = torch.cat([semantic_out, tfidf_out], dim=-1)
        features = self.fusion(fused)
        return {
            "logits": self.classifier(features),
            "similarity": torch.sigmoid(self.similarity_head(features)).squeeze(-1),
            "features": features,
        }


class ResumeScorerNet(nn.Module):
    """Stable TF-IDF classifier used by the training and scoring services."""

    def __init__(
        self,
        input_dim: int = 5000,
        num_classes: int = 10,
        hidden_dims: Optional[list[int]] = None,
        dropout: float = 0.3,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.num_classes = num_classes
        self.hidden_dims = hidden_dims or [1024, 512, 256, 128]
        self.dropout = dropout

        layers: list[nn.Module] = [
            nn.Linear(input_dim, self.hidden_dims[0]),
            nn.BatchNorm1d(self.hidden_dims[0]),
            nn.GELU(),
            nn.Dropout(dropout),
        ]

        for idx in range(len(self.hidden_dims) - 1):
            layers.extend(
                [
                    nn.Linear(self.hidden_dims[idx], self.hidden_dims[idx + 1]),
                    nn.BatchNorm1d(self.hidden_dims[idx + 1]),
                    nn.GELU(),
                    nn.Dropout(dropout),
                ]
            )

        self.encoder = nn.Sequential(*layers)
        self.residual = ResidualBlock(self.hidden_dims[-1], dropout)
        self.classifier = nn.Linear(self.hidden_dims[-1], num_classes)
        self._init_weights()

        logger.info(
            "ResumeScorerNet initialized",
            input_dim=input_dim,
            num_classes=num_classes,
            hidden_dims=self.hidden_dims,
            dropout=dropout,
            params=sum(p.numel() for p in self.parameters()),
        )

    def _init_weights(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, (nn.BatchNorm1d, nn.LayerNorm)):
                if getattr(module, "weight", None) is not None:
                    nn.init.ones_(module.weight)
                if getattr(module, "bias", None) is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.encoder(x)
        features = self.residual(features)
        return self.classifier(features)

    def get_probabilities(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            logits = self.forward(x)
            return F.softmax(logits, dim=-1)

    def get_match_score(self, resume_features: torch.Tensor, target_class_idx: int) -> float:
        probs = self.get_probabilities(resume_features)
        target_prob = probs[0, target_class_idx].item()
        score = 100.0 * (1.0 - (1.0 - target_prob) ** 0.5)
        return round(min(100.0, max(0.0, score)), 2)

    def save_checkpoint(self, path: str, extra: dict | None = None) -> None:
        state: dict[str, Any] = {
            "model_state_dict": self.state_dict(),
            "input_dim": self.input_dim,
            "num_classes": self.num_classes,
            "hidden_dims": self.hidden_dims,
            "dropout": self.dropout,
        }
        if extra:
            state.update(extra)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(state, path)
        logger.info("Checkpoint saved", path=path)

    @classmethod
    def from_checkpoint(cls, path: str, device: Optional[str] = None) -> "ResumeScorerNet":
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        checkpoint = torch.load(path, map_location=device)
        model = cls(
            input_dim=int(checkpoint.get("input_dim", 5000)),
            num_classes=int(checkpoint.get("num_classes", 10)),
            hidden_dims=list(checkpoint.get("hidden_dims", [1024, 512, 256, 128])),
            dropout=float(checkpoint.get("dropout", 0.3)),
        )

        state_dict = (
            checkpoint.get("model_state_dict")
            or checkpoint.get("model_state")
            or checkpoint.get("state_dict")
            or checkpoint.get("fusion_state")
        )
        if state_dict:
            missing, unexpected = model.load_state_dict(state_dict, strict=False)
            if missing or unexpected:
                logger.warning(
                    "Checkpoint loaded with partial state",
                    missing=missing,
                    unexpected=unexpected,
                )

        model.to(device)
        model.eval()
        logger.info("Model loaded from checkpoint", path=path, device=device)
        return model
