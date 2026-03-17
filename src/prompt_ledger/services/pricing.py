"""YAML-backed pricing table for multi-provider cost calculation — Story 1.4.

Loaded once at startup. Operators can override by setting PRICING_YAML_PATH
to point at a custom file (Docker volume or Railway config).

Cost formula:
    cost = (input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate)

Unknown models return None so callers can distinguish "cost unknown" from "zero cost".
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

# Default path: pricing.yaml at the repository root (two levels above this file's package).
_DEFAULT_PRICING_PATH = Path(__file__).parent.parent.parent.parent / "pricing.yaml"

# Provider inference: glob patterns applied in order to a model name.
_PROVIDER_PATTERNS = [
    ("claude-*", "anthropic"),
    ("gpt-*", "openai"),
]


@dataclass
class PricingRow:
    provider: str
    model_pattern: str
    input_cost_per_1k: float
    output_cost_per_1k: float


class PricingTable:
    """In-memory pricing table loaded from YAML.

    Usage::

        table = PricingTable.default()        # load bundled pricing.yaml
        cost  = table.calculate_cost("claude-haiku-4-5-20251001", 1000, 500)
        # → 0.0028

        provider = table.infer_provider("gpt-4o-mini")
        # → "openai"
    """

    def __init__(self, rows: list[PricingRow]) -> None:
        self._rows = rows

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> "PricingTable":
        """Load the default bundled pricing.yaml (or override via PRICING_YAML_PATH)."""
        path_override = os.environ.get("PRICING_YAML_PATH")
        path = Path(path_override) if path_override else _DEFAULT_PRICING_PATH
        return cls.from_yaml(path)

    @classmethod
    def from_yaml(cls, path: Path) -> "PricingTable":
        """Load a pricing table from a YAML file."""
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        rows = []
        for entry in data.get("pricing", []):
            rows.append(
                PricingRow(
                    provider=entry["provider"],
                    model_pattern=entry["model_pattern"],
                    input_cost_per_1k=float(entry["input_cost_per_1k"]),
                    output_cost_per_1k=float(entry["output_cost_per_1k"]),
                )
            )
        return cls(rows)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_cost(
        self,
        model: Optional[str],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
    ) -> Optional[float]:
        """Calculate total cost for a model call.

        Returns None if the model is unrecognised or if model is None/empty.
        Returns 0.0 if both token counts are zero/None and model is known.
        """
        if not model:
            return None

        row = self._find_row(model)
        if row is None:
            return None

        inp = input_tokens or 0
        out = output_tokens or 0
        return (inp / 1000.0 * row.input_cost_per_1k) + (
            out / 1000.0 * row.output_cost_per_1k
        )

    def infer_provider(self, model: Optional[str]) -> Optional[str]:
        """Infer provider name from a model name using glob patterns.

        Returns None for unknown or missing model names.
        """
        if not model:
            return None
        for pattern, provider in _PROVIDER_PATTERNS:
            if fnmatch.fnmatch(model, pattern):
                return provider
        return None

    def __len__(self) -> int:
        return len(self._rows)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_row(self, model: str) -> Optional[PricingRow]:
        """Return the first pricing row whose model_pattern matches model."""
        for row in self._rows:
            if fnmatch.fnmatch(model, row.model_pattern):
                return row
        return None
