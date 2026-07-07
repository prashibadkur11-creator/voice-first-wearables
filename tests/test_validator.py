"""Tests for validate/validate_config.py: schema, cross-file, and policy layers.

Also pins the shipped examples: the clean configs must stay warning-free and
the risky teaching file must keep producing exactly W1 + W2.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "validate"))

from validate_config import validate  # noqa: E402


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data))
    return p


GOOD_AUTH = {
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

GOOD_CMDS = {
    "commands": [
        {
            "intent": "pay",
            "min_level": "L3_explicit",
            "reversible": False,
            "availability": ["online"],
            "confirmation": "explicit",
        }
    ]
}


def test_valid_pair_passes(tmp_path):
    errors, warnings = validate(
        write(tmp_path, "a.yaml", GOOD_AUTH), write(tmp_path, "c.yaml", GOOD_CMDS)
    )
    assert errors == [] and warnings == []


def test_schema_layer_rejects_unknown_factor(tmp_path):
    bad = {"factors": ["laser"], "levels": {"L0_none": {}}}
    errors, _ = validate(
        write(tmp_path, "a.yaml", bad), write(tmp_path, "c.yaml", GOOD_CMDS)
    )
    assert any("laser" in e for e in errors)


def test_r1_min_level_must_be_defined(tmp_path):
    minimal_auth = {"factors": ["proximity"], "levels": {"L0_none": {}}}
    errors, _ = validate(
        write(tmp_path, "a.yaml", minimal_auth), write(tmp_path, "c.yaml", GOOD_CMDS)
    )
    assert any("[R1]" in e and "pay" in e for e in errors)


def test_r2_factors_must_be_declared(tmp_path):
    auth = {
        "factors": ["voiceprint", "proximity"],  # pin_voice missing
        "levels": {
            "L0_none": {},
            "L3_explicit": {"requires": ["voiceprint", "proximity", "pin_voice"]},
        },
    }
    errors, _ = validate(
        write(tmp_path, "a.yaml", auth), write(tmp_path, "c.yaml", GOOD_CMDS)
    )
    assert any("[R2]" in e and "pin_voice" in e for e in errors)


def test_w1_w2_warn_only_still_valid(tmp_path):
    risky = {
        "commands": [
            {
                "intent": "delete_all",
                "min_level": "L1_passive",
                "reversible": False,
                "availability": ["online"],
                "confirmation": "none",
            }
        ]
    }
    errors, warnings = validate(
        write(tmp_path, "a.yaml", GOOD_AUTH), write(tmp_path, "c.yaml", risky)
    )
    assert errors == []                                  # warn-only: no errors
    assert any("[W1]" in w for w in warnings)
    assert any("[W2]" in w for w in warnings)


def test_missing_file_is_an_error(tmp_path):
    errors, _ = validate(tmp_path / "nope.yaml", write(tmp_path, "c.yaml", GOOD_CMDS))
    assert any("not found" in e for e in errors)


# ------------------------------------------------- pin the shipped examples

def test_example_smart_glasses_is_clean():
    errors, warnings = validate(
        REPO_ROOT / "examples/smart-glasses/auth.yaml",
        REPO_ROOT / "examples/smart-glasses/commands.yaml",
    )
    assert errors == [] and warnings == []


def test_example_earbuds_is_clean():
    errors, warnings = validate(
        REPO_ROOT / "examples/earbuds/auth.yaml",
        REPO_ROOT / "examples/earbuds/commands.yaml",
    )
    assert errors == [] and warnings == []


def test_example_risky_file_warns_exactly_w1_w2():
    errors, warnings = validate(
        REPO_ROOT / "examples/smart-glasses/auth.yaml",
        REPO_ROOT / "examples/smart-glasses/commands.risky.yaml",
    )
    assert errors == []
    assert len(warnings) == 2
    assert any("[W1]" in w for w in warnings)
    assert any("[W2]" in w for w in warnings)
