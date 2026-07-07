"""Tests for voicefirst.auth: levels, decay, never-cache, events, verifiers."""

import itertools

import pytest

from voicefirst.auth import (
    AlwaysFailVerifier,
    AuthEngine,
    AuthSession,
    MockVerifier,
)

FULL_CONFIG = {
    "factors": ["voiceprint", "proximity", "pin_voice"],
    "levels": {
        "L0_none": {},
        "L1_passive": {"requires_any": ["voiceprint", "proximity"]},
        "L2_verified": {"requires": ["voiceprint", "proximity"], "decay_seconds": 300},
        "L3_explicit": {
            "requires": ["voiceprint", "proximity", "pin_voice"],
            "never_cache": True,
        },
    },
    "fallbacks": {
        "voiceprint_fail": "challenge_pin",
        "proximity_lost": "drop_one_level",
        "device_unworn": "reset_to_l0",
    },
}

MINIMAL_CONFIG = {
    "factors": ["proximity"],
    "levels": {"L0_none": {}, "L1_passive": {"requires": ["proximity"]}},
    "fallbacks": {"device_unworn": "reset_to_l0"},
}


def full_engine():
    return AuthEngine(
        FULL_CONFIG,
        {
            "voiceprint": MockVerifier("voiceprint"),
            "proximity": MockVerifier("proximity"),
            "pin_voice": MockVerifier("pin_voice"),
        },
    )


# ---------------------------------------------------------------- sessions

def test_session_starts_at_l0():
    assert AuthSession(FULL_CONFIG).effective_level() == "L0_none"


def test_elevate_requires_all_and_factors():
    s = AuthSession(FULL_CONFIG)
    assert not s.elevate("L2_verified", ["voiceprint"])       # missing proximity
    assert s.elevate("L2_verified", ["voiceprint", "proximity"])
    assert s.effective_level() == "L2_verified"


def test_elevate_requires_any_accepts_either_factor():
    s = AuthSession(FULL_CONFIG)
    assert s.elevate("L1_passive", ["proximity"])
    s2 = AuthSession(FULL_CONFIG)
    assert s2.elevate("L1_passive", ["voiceprint"])


def test_elevate_to_undefined_level_fails():
    s = AuthSession(MINIMAL_CONFIG)
    assert not s.elevate("L3_explicit", ["proximity"])


def test_decay_drops_to_next_defined_level():
    t = itertools.count(0, 400)  # every clock read jumps 400s > 300s decay
    s = AuthSession(FULL_CONFIG, clock=lambda: next(t))
    s.elevate("L2_verified", ["voiceprint", "proximity"])
    assert s.effective_level() == "L1_passive"


def test_decay_skips_undefined_levels():
    # Config defining only L0 and L2: decay from L2 must land on L0.
    cfg = {
        "factors": ["voiceprint", "proximity"],
        "levels": {
            "L0_none": {},
            "L2_verified": {
                "requires": ["voiceprint", "proximity"],
                "decay_seconds": 10,
            },
        },
    }
    t = itertools.count(0, 60)
    s = AuthSession(cfg, clock=lambda: next(t))
    s.elevate("L2_verified", ["voiceprint", "proximity"])
    assert s.effective_level() == "L0_none"


def test_device_unworn_resets_to_l0():
    s = AuthSession(FULL_CONFIG)
    s.elevate("L2_verified", ["voiceprint", "proximity"])
    s.on_event("device_unworn")
    assert s.effective_level() == "L0_none"


def test_proximity_lost_drops_one_level():
    s = AuthSession(FULL_CONFIG)
    s.elevate("L2_verified", ["voiceprint", "proximity"])
    s.on_event("proximity_lost")
    assert s.effective_level() == "L1_passive"


# ---------------------------------------------------------------- engine

def test_engine_requires_verifier_per_declared_factor():
    with pytest.raises(ValueError):
        AuthEngine(FULL_CONFIG, {"voiceprint": MockVerifier("voiceprint")})


def test_authorize_allows_at_or_above_min_level():
    engine = full_engine()
    s = AuthSession(FULL_CONFIG)
    s.elevate("L2_verified", ["voiceprint", "proximity"])
    assert engine.authorize("L1_passive", s).allowed
    assert engine.authorize("L2_verified", s).allowed
    assert not engine.authorize("L3_explicit", s).allowed


def test_challenge_elevates_on_passing_verifiers():
    engine = full_engine()
    s = AuthSession(FULL_CONFIG)
    d = engine.challenge(s, "L2_verified", {"voiceprint": {}, "proximity": {}})
    assert d.allowed and s.effective_level() == "L2_verified"


def test_challenge_fails_with_failing_verifier():
    engine = AuthEngine(
        FULL_CONFIG,
        {
            "voiceprint": AlwaysFailVerifier("voiceprint"),
            "proximity": MockVerifier("proximity"),
            "pin_voice": MockVerifier("pin_voice"),
        },
    )
    s = AuthSession(FULL_CONFIG)
    d = engine.challenge(s, "L2_verified", {"voiceprint": {}, "proximity": {}})
    assert not d.allowed


def test_l3_never_cached_single_use():
    engine = full_engine()
    s = AuthSession(FULL_CONFIG)
    engine.challenge(
        s, "L3_explicit", {"voiceprint": {}, "proximity": {}, "pin_voice": {}}
    )
    assert engine.authorize("L3_explicit", s).allowed        # first use: spends it
    assert not engine.authorize("L3_explicit", s).allowed    # second use: re-challenge


def test_mock_verifier_script_sequences():
    v = MockVerifier("pin_voice", script=[False, True])
    assert not v.verify({}).success
    assert v.verify({}).success
    assert v.verify({}).success  # sticks at last outcome
