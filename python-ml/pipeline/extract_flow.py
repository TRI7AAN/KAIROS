"""Validation helpers for canonical finite feature vectors from Java."""

from __future__ import annotations

import math
from typing import Mapping, Sequence


class FeatureValidationError(ValueError):
    """Raised when a graph feature vector violates its declared schema."""


def validate_feature_map(
    features: Mapping[str, float],
    schema: Sequence[str],
) -> tuple[float, ...]:
    """Return a schema-ordered vector, filling absent declared values with zero."""
    undeclared = set(features) - set(schema)
    if undeclared:
        raise FeatureValidationError(
            f"undeclared features: {sorted(undeclared)}")
    vector = tuple(float(features.get(name, 0.0)) for name in schema)
    if not all(math.isfinite(value) for value in vector):
        raise FeatureValidationError("feature values must be finite")
    return vector
