"""Tests for voicefirst.commands.CommandRouter: the 4-step checklist."""

import pytest

from voicefirst.auth import AuthEngine, AuthSession, MockVerifier
from voicefirst.commands import CommandRouter

AUTH = {
    "factors": ["voiceprint", "proximity", "pin_voice"],
    "levels": {
        "L0_none": {},
        "L1_passive": {"requires_any": ["voiceprint", "proximity"]},
        "L2_verified": {"requires": ["voiceprint", "proximity"]},
        "L3_explicit": {
            "requires": ["voiceprint", "proximity", "pin_voice"],
            "never_cache": True,
        },
    },
}

COMMANDS = {
    "commands": [
        {
            "intent": "what_time",
            "min_level": "L0_none",
            "reversible": True,
            "availability": ["online", "offline"],
            "confirmation": "none",
        },
        {
            "intent": "send_message",
            "min_level": "L2_verified",
            "reversible": True,
            "availability": ["online"],
            "confirmation": "audio",
        },
        {
            "intent": "pay",
            "min_level": "L3_explicit",
            "reversible": False,
            "availability": ["online"],
            "confirmation": "explicit",
        },
    ]
}


@pytest.fixture()
def setup():
    engine = AuthEngine(
        AUTH,
        {
            "voiceprint": MockVerifier("voiceprint"),
            "proximity": MockVerifier("proximity"),
            "pin_voice": MockVerifier("pin_voice"),
        },
    )
    session = AuthSession(AUTH)
    router = CommandRouter(COMMANDS, engine)
    router.register("what_time", lambda ctx: "3:04 PM")
    router.register("send_message", lambda ctx: f"sent:{ctx.get('text')}")
    router.register("pay", lambda ctx: f"paid:{ctx.get('amount')}")
    return engine, session, router


def test_unknown_intent(setup):
    _, session, router = setup
    assert router.dispatch("self_destruct", session).status == "unknown_intent"


def test_l0_command_runs_cold(setup):
    _, session, router = setup
    r = router.dispatch("what_time", session)
    assert r.status == "ok" and r.result == "3:04 PM"


def test_auth_gate_blocks_and_reports_missing(setup):
    _, session, router = setup
    r = router.dispatch("send_message", session, {"text": "hi"})
    assert r.status == "auth_required"
    assert r.required_level == "L2_verified"
    assert r.current_level == "L0_none"
    assert r.missing_factors  # tells the dev what to challenge


def test_confirmation_gate(setup):
    engine, session, router = setup
    engine.challenge(session, "L2_verified", {"voiceprint": {}, "proximity": {}})
    r = router.dispatch("send_message", session, {"text": "hi"})
    assert r.status == "confirmation_required" and r.confirmation_type == "audio"
    r = router.dispatch("send_message", session, {"text": "hi"}, confirmed=True)
    assert r.status == "ok" and r.result == "sent:hi"


def test_router_never_auto_confirms_l3(setup):
    engine, session, router = setup
    engine.challenge(
        session, "L3_explicit", {"voiceprint": {}, "proximity": {}, "pin_voice": {}}
    )
    r = router.dispatch("pay", session, {"amount": 40})
    assert r.status == "confirmation_required"  # confirmed not passed -> blocked


def test_register_unknown_intent_raises(setup):
    _, _, router = setup
    with pytest.raises(KeyError):
        router.register("not_declared", lambda ctx: None)


def test_missing_handler_is_reported(setup):
    engine = AuthEngine(
        AUTH,
        {
            "voiceprint": MockVerifier("voiceprint"),
            "proximity": MockVerifier("proximity"),
            "pin_voice": MockVerifier("pin_voice"),
        },
    )
    session = AuthSession(AUTH)
    router = CommandRouter(COMMANDS, engine)  # nothing registered
    r = router.dispatch("what_time", session)
    assert r.status == "handler_error" and "No handler" in r.error


def test_handler_exception_is_surfaced_not_swallowed(setup):
    engine, session, router = setup

    def boom(ctx):
        raise RuntimeError("network down")

    router.register("what_time", boom)
    r = router.dispatch("what_time", session)
    assert r.status == "handler_error" and "network down" in r.error
