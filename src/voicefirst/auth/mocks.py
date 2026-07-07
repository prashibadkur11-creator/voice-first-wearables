"""Fake verifiers that ship in-box.

These let the repo run with zero real hardware or APIs: fork it, run the
examples and tests, everything works. Use them in your own tests to simulate
pass/fail sequences without real audio or devices.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .verifiers import VerifyResult


class MockVerifier:
    """A scriptable fake verifier.

    - MockVerifier("voiceprint")                     -> always passes
    - MockVerifier("pin_voice", script=[False, True]) -> fails once, then
      passes, then keeps returning the last outcome.
    """

    def __init__(self, factor: str, script: Optional[List[bool]] = None) -> None:
        self.factor = factor
        self._script = list(script) if script else [True]
        self._calls = 0

    def verify(self, challenge: Dict[str, Any]) -> VerifyResult:
        idx = min(self._calls, len(self._script) - 1)
        outcome = self._script[idx]
        self._calls += 1
        return VerifyResult(
            success=outcome,
            factor=self.factor,
            confidence=1.0 if outcome else 0.0,
            detail=f"mock call #{self._calls} -> {'pass' if outcome else 'fail'}",
        )


class AlwaysFailVerifier:
    """Always says no. Use it to test fallback and challenge-failure paths."""

    def __init__(self, factor: str) -> None:
        self.factor = factor

    def verify(self, challenge: Dict[str, Any]) -> VerifyResult:
        return VerifyResult(
            success=False,
            factor=self.factor,
            confidence=0.0,
            detail="always-fail verifier",
        )
