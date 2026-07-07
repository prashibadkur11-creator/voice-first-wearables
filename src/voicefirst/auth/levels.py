"""The assurance engine: tracks how much we trust the wearer right now.

Canonical ladder: L0_none < L1_passive < L2_verified < L3_explicit.
A config may define only a subset (L0_none is always required); decay drops
trust to the next-lowest *defined* level.

Rules implemented here:
  - elevate: a level is granted only if its `requires` (AND) and/or
    `requires_any` (OR) factor conditions are met by verified factors
  - decay: after `decay_seconds`, the session drops one defined level
  - never_cache: flagged levels are granted for exactly one authorize() and
    then revert to the previous level
  - events: fallbacks from config (device_unworn -> reset_to_l0, ...)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Canonical ladder, lowest to highest. No custom levels.
LEVEL_ORDER: List[str] = ["L0_none", "L1_passive", "L2_verified", "L3_explicit"]


def level_index(name: str) -> int:
    """Position of a level on the canonical ladder (raises on unknown names)."""
    return LEVEL_ORDER.index(name)


@dataclass
class AuthDecision:
    """Answer to: 'may this session run a command needing `required_level`?'"""

    allowed: bool
    current_level: str
    required_level: str
    missing_factors: List[str] = field(default_factory=list)


class AuthSession:
    """Mutable trust state for one wearer on one device."""

    def __init__(self, config: Dict[str, Any], clock=time.monotonic) -> None:
        self._config = config
        self._clock = clock
        self._levels: Dict[str, Any] = config.get("levels", {})
        self._defined: List[str] = [l for l in LEVEL_ORDER if l in self._levels]
        self.current_level: str = "L0_none"
        self._established_at: float = self._clock()
        self._one_shot_from: Optional[str] = None  # level to revert to after a
                                                   # never_cache level is used

    # -- trust goes up -----------------------------------------------------

    def elevate(self, target_level: str, verified_factors: List[str]) -> bool:
        """Try to raise trust to `target_level` given the factors that just
        verified successfully. Returns True on success."""
        spec = self._levels.get(target_level)
        if spec is None:
            return False  # level not defined in this config
        spec = spec or {}

        requires = spec.get("requires", [])
        requires_any = spec.get("requires_any", [])
        if any(f not in verified_factors for f in requires):
            return False
        if requires_any and not any(f in verified_factors for f in requires_any):
            return False

        if spec.get("never_cache", False):
            # Grant for exactly one authorize(); remember where to fall back.
            self._one_shot_from = self.effective_level()
        self.current_level = target_level
        self._established_at = self._clock()
        return True

    # -- trust goes down ---------------------------------------------------

    def effective_level(self) -> str:
        """Current level after applying decay."""
        spec = self._levels.get(self.current_level) or {}
        decay = spec.get("decay_seconds")
        if decay is not None and (self._clock() - self._established_at) > decay:
            self._drop_one_level()
        return self.current_level

    def _drop_one_level(self) -> None:
        """Drop to the next-lowest *defined* level (L0_none is the floor)."""
        idx = level_index(self.current_level)
        for name in reversed(self._defined):
            if level_index(name) < idx:
                self.current_level = name
                self._established_at = self._clock()
                return
        self.current_level = "L0_none"
        self._established_at = self._clock()

    def on_event(self, event: str) -> None:
        """Apply a config fallback for an event.

        Events: 'device_unworn' | 'proximity_lost' | 'voiceprint_fail'
        Actions: 'reset_to_l0' | 'drop_to_l0' | 'drop_one_level' | 'hold'
        (challenge_pin / retry_once are surfaced to the caller by AuthEngine,
        not handled here -- the session only tracks trust.)
        """
        action = (self._config.get("fallbacks") or {}).get(event)
        if action in ("reset_to_l0", "drop_to_l0"):
            self.current_level = "L0_none"
            self._established_at = self._clock()
        elif action == "drop_one_level":
            self._drop_one_level()
        # 'hold', None, and challenge-type actions: no state change here.

    def consume_one_shot(self) -> None:
        """Called by AuthEngine after a never_cache level is used once."""
        if self._one_shot_from is not None:
            self.current_level = self._one_shot_from
            self._established_at = self._clock()
            self._one_shot_from = None


class AuthEngine:
    """The orchestrator developers call.

    Construct with a parsed auth config and a {factor_name: Verifier} dict
    (mocks or real). The router asks one question: authorize(min_level, session).
    """

    def __init__(self, config: Dict[str, Any], verifiers: Dict[str, Any]) -> None:
        declared = set(config.get("factors", []))
        missing = declared - set(verifiers)
        if missing:
            raise ValueError(
                f"No verifier plugged in for declared factor(s): {sorted(missing)}"
            )
        self.config = config
        self.verifiers = verifiers

    def authorize(
        self, min_level: str, session: AuthSession, _consume: bool = True
    ) -> AuthDecision:
        current = session.effective_level()
        if level_index(current) >= level_index(min_level):
            # If the satisfying level is one-shot (never_cache), spend it now --
            # but only for a real command authorization (_consume=True), not
            # for the post-challenge status check.
            spec = (self.config.get("levels", {}).get(current) or {})
            if _consume and spec.get("never_cache", False):
                session.consume_one_shot()
            return AuthDecision(True, current, min_level)

        missing = self._missing_factors(min_level, session)
        return AuthDecision(False, current, min_level, missing_factors=missing)

    def challenge(
        self,
        session: AuthSession,
        target_level: str,
        challenges: Dict[str, Dict[str, Any]],
    ) -> AuthDecision:
        """Run verifiers for the given factors and try to elevate.

        `challenges` maps factor name -> challenge payload for its verifier,
        e.g. {"pin_voice": {"audio": ..., "expected_pin": "4321"}}.
        """
        verified = [
            factor
            for factor, payload in challenges.items()
            if factor in self.verifiers
            and self.verifiers[factor].verify(payload).success
        ]
        session.elevate(target_level, verified)
        return self.authorize(target_level, session, _consume=False)

    def _missing_factors(self, target_level: str, session: AuthSession) -> List[str]:
        spec = (self.config.get("levels", {}).get(target_level) or {})
        needed = list(spec.get("requires", []))
        if spec.get("requires_any"):
            needed.append("any_of:" + "|".join(spec["requires_any"]))
        return needed
