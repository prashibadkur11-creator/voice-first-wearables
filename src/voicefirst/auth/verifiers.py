"""The pluggable verifier contract.

This module is deliberately tiny: it defines the *socket* that developers plug
their real verification tech into (cloud voiceprint APIs, Whisper-based PIN
transcription, BLE pairing checks...). The library never implements real
verification -- see mocks.py for the fakes that ship in-box.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class VerifyResult:
    """Uniform result shape returned by every verifier."""

    success: bool
    factor: str                      # "voiceprint" | "proximity" | "pin_voice"
    confidence: float = 1.0          # 0.0 - 1.0; mocks default to 1.0
    detail: str = ""                 # human-readable note (for logs/debugging)


@runtime_checkable
class Verifier(Protocol):
    """Anything with a verify() method fits the socket.

    `challenge` is a loose dict so developers aren't locked into our input
    types. Typical keys: {"audio": ..., "expected_pin": ...,
    "pairing_state": ...} -- whatever the real implementation needs.
    """

    def verify(self, challenge: Dict[str, Any]) -> VerifyResult:
        ...
