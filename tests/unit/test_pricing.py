"""Unit tests for PricingTable — Story 1.4.

TDD: these tests are written BEFORE the implementation exists.
They must fail (RED) before any implementation is written.
"""

import pytest

from prompt_ledger.services.pricing import PricingTable


class TestPricingTableGlobMatching:
    """PricingTable uses fnmatch glob patterns to match model names."""

    def test_claude_haiku_glob_matches_versioned_name(self):
        """claude-haiku-4-5-* should match claude-haiku-4-5-20251001."""
        table = PricingTable.default()
        cost = table.calculate_cost("claude-haiku-4-5-20251001", 1000, 1000)
        assert cost is not None

    def test_gpt4o_mini_glob_matches_dated_variant(self):
        """gpt-4o-mini* should match gpt-4o-mini-2024-07-18 (forward-compat)."""
        table = PricingTable.default()
        cost = table.calculate_cost("gpt-4o-mini-2024-07-18", 1000, 1000)
        assert cost is not None

    def test_claude_sonnet_glob_matches(self):
        """claude-sonnet-4-6* should match claude-sonnet-4-6."""
        table = PricingTable.default()
        cost = table.calculate_cost("claude-sonnet-4-6", 1000, 1000)
        assert cost is not None

    def test_gpt4o_glob_does_not_match_gpt4o_mini(self):
        """gpt-4o* should match gpt-4o but gpt-4o-mini is matched by its own pattern.

        Both patterns may match — what matters is that gpt-4o-mini has a price entry.
        This test just ensures the glob system works for gpt-4o base name.
        """
        table = PricingTable.default()
        cost = table.calculate_cost("gpt-4o", 1000, 1000)
        assert cost is not None


class TestPricingTableCostCalculation:
    """PricingTable calculates cost correctly for known models."""

    def test_anthropic_haiku_correct_total_cost(self):
        """Known Anthropic model with known token counts produces correct total_cost.

        claude-haiku-4-5-*: input $0.00080/1k, output $0.00400/1k
        1000 input + 500 output = (1000/1000 * 0.00080) + (500/1000 * 0.00400)
                                 = 0.00080 + 0.00200 = 0.00280
        """
        table = PricingTable.default()
        cost = table.calculate_cost("claude-haiku-4-5-20251001", 1000, 500)
        assert cost == pytest.approx(0.00280, rel=1e-4)

    def test_anthropic_sonnet_correct_total_cost(self):
        """claude-sonnet-4-6: input $0.00300/1k, output $0.01500/1k.

        500 input + 200 output = (500/1000 * 0.00300) + (200/1000 * 0.01500)
                                = 0.00150 + 0.00300 = 0.00450
        """
        table = PricingTable.default()
        cost = table.calculate_cost("claude-sonnet-4-6", 500, 200)
        assert cost == pytest.approx(0.00450, rel=1e-4)

    def test_openai_gpt4o_mini_correct_total_cost(self):
        """gpt-4o-mini: input $0.00015/1k, output $0.00060/1k.

        2000 input + 1000 output = (2000/1000 * 0.00015) + (1000/1000 * 0.00060)
                                  = 0.00030 + 0.00060 = 0.00090
        """
        table = PricingTable.default()
        cost = table.calculate_cost("gpt-4o-mini", 2000, 1000)
        assert cost == pytest.approx(0.00090, rel=1e-4)

    def test_zero_tokens_produces_zero_cost(self):
        """Zero input and output tokens produce $0.00 cost, not null."""
        table = PricingTable.default()
        cost = table.calculate_cost("claude-haiku-4-5-20251001", 0, 0)
        assert cost == pytest.approx(0.0)


class TestPricingTableUnknownModel:
    """Unknown models fall back to null, not an exception."""

    def test_unknown_model_returns_none(self):
        """Unrecognised model returns None — callers distinguish unknown from zero."""
        table = PricingTable.default()
        cost = table.calculate_cost("some-future-unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_none_model_name_returns_none(self):
        """None model name (span has no model) returns None gracefully."""
        table = PricingTable.default()
        cost = table.calculate_cost(None, 1000, 500)
        assert cost is None

    def test_empty_model_name_returns_none(self):
        """Empty string model name returns None gracefully."""
        table = PricingTable.default()
        cost = table.calculate_cost("", 1000, 500)
        assert cost is None


class TestPricingTableProviderInference:
    """Provider is inferred from model name — no provider column needed on Span."""

    def test_claude_prefix_infers_anthropic(self):
        """claude-* model names infer anthropic provider."""
        table = PricingTable.default()
        provider = table.infer_provider("claude-haiku-4-5-20251001")
        assert provider == "anthropic"

    def test_gpt_prefix_infers_openai(self):
        """gpt-* model names infer openai provider."""
        table = PricingTable.default()
        provider = table.infer_provider("gpt-4o-mini")
        assert provider == "openai"

    def test_unknown_model_infers_none(self):
        """Unknown model prefix returns None provider."""
        table = PricingTable.default()
        provider = table.infer_provider("some-unknown-model")
        assert provider is None

    def test_none_model_infers_none(self):
        """None model name returns None provider."""
        table = PricingTable.default()
        provider = table.infer_provider(None)
        assert provider is None


class TestPricingTableLoading:
    """PricingTable loads from YAML and has a default() factory."""

    def test_default_has_entries(self):
        """PricingTable.default() loads the bundled pricing.yaml with entries."""
        table = PricingTable.default()
        assert len(table) > 0

    def test_default_covers_all_documented_models(self):
        """All five documented model patterns resolve to non-None cost."""
        table = PricingTable.default()
        models = [
            ("claude-haiku-4-5-20251001", 100, 100),
            ("claude-sonnet-4-6", 100, 100),
            ("claude-opus-4-6", 100, 100),
            ("gpt-4o-mini", 100, 100),
            ("gpt-4o", 100, 100),
        ]
        for model, inp, out in models:
            cost = table.calculate_cost(model, inp, out)
            assert cost is not None, f"Expected non-null cost for model {model!r}"
