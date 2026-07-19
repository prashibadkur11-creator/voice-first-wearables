# voice-first-wearables
![License: MIT](https://img.shields.io/github/license/prashibadkur11-creator/voice-first-wearables) ![CI](https://img.shields.io/github/actions/workflow/status/prashibadkur11-creator/voice-first-wearables/validate.yml?branch=main&label=CI)

**A voice-first auth + command library for AI-native wearables — smart glasses, earbuds, rings.**

Developers build voice products *on top of* this library: you write two YAML files and plug in handlers; the library validates your config, tracks trust, and refuses to run anything until the safety rules are met.

> **The division of labor:** the library owns the flow (validation, auth ladder, confirmation gates, dispatch). You own the implementation (verifiers, handlers, UX).

---

## Why this exists

Voice is a low-confidence input channel on a device with no screen. A single voiceprint match shouldn't unlock a payment, and "are you sure?" can't be a dialog box. This library encodes those constraints as **enforced structure**:

- Auth resolves to an **assurance level**, not a binary logged-in/out
- Every command declares the **minimum level** it needs
- Trust **decays** over time and **resets** when the device comes off
- High-stakes trust is **never cached** — every payment re-challenges
- Irreversible commands without strong gates get **flagged in CI**

## Three hero scenarios

1. **"I'm building voice auth for my smart-glasses app"** — declare your auth policy in `auth.yaml`, plug your verifiers into the `Verifier` interface, call `AuthEngine.authorize()`. The validator catches policy gaps before they ship.
2. **"I need voice commands without hand-rolling intent routing"** — declare commands in `commands.yaml`, register handlers, let `CommandRouter` run the safety checklist. The "forgot to confirm the destructive action" bug class gets caught in CI.
3. **"I want to test voice UX before I have hardware"** — `MockVerifier` and `AlwaysFailVerifier` ship in-box; everything runs with zero devices or API keys. *(A full scripted simulator is the v2 headline.)*

## Quickstart

```bash
git clone https://github.com/prashibadkur11-creator/voice-first-wearables
cd voice-first-wearables
pip install -r requirements.txt

# validate the example configs
python validate/validate_config.py examples/smart-glasses/auth.yaml \
                                   examples/smart-glasses/commands.yaml

# see the warn-only gate fire (deliberately misconfigured file)
python validate/validate_config.py examples/smart-glasses/auth.yaml \
                                   examples/smart-glasses/commands.risky.yaml

# run the test suite (31 tests)
PYTHONPATH=src pytest tests/
```

Minimal usage:

```python
from voicefirst.config import load_auth_config, load_commands
from voicefirst.auth import AuthEngine, AuthSession, MockVerifier
from voicefirst.commands import CommandRouter

auth = load_auth_config("examples/smart-glasses/auth.yaml")
cmds = load_commands("examples/smart-glasses/commands.yaml")

engine = AuthEngine(auth, {
    "voiceprint": MockVerifier("voiceprint"),   # swap in your real verifier
    "proximity":  MockVerifier("proximity"),
    "pin_voice":  MockVerifier("pin_voice"),
})
session = AuthSession(auth)
router = CommandRouter(cmds, engine)
router.register("send_message", lambda ctx: my_send(ctx["text"]))

result = router.dispatch("send_message", session, {"text": "hi mom"})
# -> auth_required (with missing factors), confirmation_required, or ok
```

## The auth model

Four canonical assurance levels built from three pluggable factors:

| Level | Established by | Unlocks (typical) |
|---|---|---|
| `L0_none` | nothing | time, weather, transport controls |
| `L1_passive` | voiceprint **or** proximity | reads: messages, navigation |
| `L2_verified` | voiceprint **and** proximity | writes: send, schedule |
| `L3_explicit` | L2 + spoken PIN / gesture | money, unlock, delete |

| Factor | Security category | Effort |
|---|---|---|
| `voiceprint` | something you **are** | passive |
| `proximity` | something you **have** | passive |
| `pin_voice` | something you **know** / deliberate act | active |

**Trust behavior:** levels decay after a configurable window (dropping to the next-lowest *defined* level); `never_cache` levels are granted for exactly one action; `device_unworn` resets to L0 — the unworn moment is exactly when the wearer can change.

**Levels are optional (read vs. write):** a device with only read actions (earbuds playing music) defines just L0/L1 — impersonating a reader gains little. L2/L3 exist for write actions (send, pay, delete), where impersonation causes real damage. Define only the rungs you use; the validator hard-fails any command referencing an undefined level.

## What the validator enforces

| Rule | Severity | Meaning |
|---|---|---|
| Schema | error | each file matches its JSON Schema contract |
| R1 | error | every `min_level` in commands.yaml is defined in auth.yaml |
| R2 | error | every factor a level uses is declared in `factors` |
| W1 | **warn** | irreversible command not gated at `L3_explicit` |
| W2 | **warn** | irreversible command with `confirmation: none` |

W1/W2 are deliberately warn-only: high-stakes gating is the library's opinion, but the developer can override it — the warning makes the choice visible, not forbidden.

## Repo structure

```
schema/       JSON Schema (Draft 2020-12) contracts for auth + commands
examples/     smart-glasses (full ladder) and earbuds (minimal) configs
src/          the library: auth engine, verifier interface, mocks, router, loader
validate/     the CI-runnable validator (schema + cross-file + policy layers)
tests/        31 tests pinning the ladder, the gates, and the shipped examples
```

## Design decisions (and why)

- **Pluggable verifiers, not shipped biometrics** — the library defines the `Verifier` socket; you bring Whisper, a cloud speaker-ID API, or BLE pairing checks. Shipping a "reference" PIN verifier would be a security footgun; an interface isn't.
- **The router never auto-confirms** — it returns `confirmation_required` and waits for your UX to pass `confirmed=True`. No step can be skipped; no step is done for you.
- **No I/O in core** — no audio, no network, no STT/TTS anywhere in the library. That's your layer. It also makes the core 100% unit-testable and the v2 simulator possible.
- **Two enforcement points, one schema** — configs are validated at load time (fast feedback in dev) and in CI (gate on merge), against the same schema files.

## Related

Part of a connected AI product toolkit — this library puts several patterns from
[`voice-ai-ux-patterns`](https://github.com/prashibadkur11-creator/voice-ai-ux-patterns) into
running code (confirmation-for-irreversible-actions, error-recovery-without-blame),
and follows the same YAML → schema → validator → CI idiom as
[`ai-failure-mode-taxonomy`](https://github.com/prashibadkur11-creator/ai-failure-mode-taxonomy),
[`prompt-regression-suite`](https://github.com/prashibadkur11-creator/prompt-regression-suite), and
[`persona-spec-template`](https://github.com/prashibadkur11-creator/persona-spec-template).

## Roadmap (v2)

- **Scripted wearable simulator** — feed sequences of voice inputs incl. failures (mis-recognition, dropped proximity, noisy PIN) and assert how the config behaves
- Gesture factor as a first-class verifier type
- Multi-wearer support (shared devices)

## License

MIT
