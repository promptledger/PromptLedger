"""TDD Example: Following our mandatory TDD rules.

This test demonstrates our Test-Driven Development approach:
1. Write failing test FIRST (RED)
2. Implement minimal code to pass (GREEN)
3. Refactor while keeping tests green (REFACTOR)

This is the ONLY way we develop features in this project.
"""

import pytest

from prompt_ledger.models.prompt import compute_checksum


class TestTDDExample:
    """Example demonstrating our mandatory TDD approach."""

    def test_checksum_computation_follows_tdd_rules(self):
        """GREEN PHASE: Test now passes with correct implementation.

        This demonstrates the TDD cycle:
        1. RED: Write failing test ✓
        2. GREEN: Make test pass with minimal implementation
        3. REFACTOR: Improve while keeping green
        """
        # Arrange - Test data
        template = "Hello {{name}}, welcome to {{place}}!"

        # Act & Assert - Now this passes with correct implementation
        checksum = compute_checksum(template)

        # Real SHA-256 hash for this specific template
        expected = "865bf6664dbd9f05e93aecca3e3bc4b3a25755b7fdcc401fb4bfbc72f81db81b"

        assert checksum == expected, f"Expected {expected}, got {checksum}"
        assert len(checksum) == 64, "Checksum should be 64 characters (SHA-256)"
        assert all(
            c in "0123456789abcdef" for c in checksum
        ), "Checksum should be hexadecimal"

    def test_checksum_is_deterministic(self):
        """RED PHASE: Test that same input always produces same checksum."""
        template = "Test template with {{variable}}"

        # Multiple calls should produce same result
        checksum1 = compute_checksum(template)
        checksum2 = compute_checksum(template)

        assert checksum1 == checksum2, "Checksum should be deterministic"

    def test_checksum_changes_with_content(self):
        """RED PHASE: Test that different content produces different checksums."""
        template1 = "Hello {{name}}"
        template2 = "Hello {{world}}"

        checksum1 = compute_checksum(template1)
        checksum2 = compute_checksum(template2)

        assert (
            checksum1 != checksum2
        ), "Different templates should have different checksums"


# TDD RULE REMINDER:
# 1. These tests were written BEFORE any implementation
# 2. They MUST fail initially (RED phase)
# 3. Then implement minimal code to pass (GREEN phase)
# 4. Finally refactor while keeping tests green (REFACTOR phase)
#
# NO EXCEPTIONS - This applies to EVERY feature, bug fix, and enhancement!
