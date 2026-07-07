#!/usr/bin/env python3
"""Config validator: the proofreader for a developer's auth.yaml + commands.yaml.

Three layers of checking:

  1. SCHEMA (hard fail)  -- each file matches its JSON Schema contract
  2. CROSS-FILE (hard fail) -- the files make sense *together*:
       R1: every min_level referenced in commands.yaml is defined in auth.yaml
       R2: every factor referenced by a level's requires/requires_any is
           declared in auth.yaml's factors list
  3. POLICY (warn only) -- risky-but-allowed choices:
       W1: an irreversible command (reversible: false) should require
           L3_explicit -- warn if it doesn't (developer may override)
       W2: an irreversible command should not have confirmation: none

Exit codes (CI-friendly):
  0 = valid (warnings may still be printed)
  1 = errors found
  2 = usage / file problem

Usage:
  python validate/validate_config.py <auth.yaml> <commands.yaml>
  python validate/validate_config.py examples/smart-glasses/auth.yaml \
                                     examples/smart-glasses/commands.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schema"


# ---------------------------------------------------------------- layer 1

def schema_errors(data: Dict[str, Any], schema_file: str) -> List[str]:
    schema = yaml.safe_load(open(SCHEMA_DIR / schema_file))
    validator = Draft202012Validator(schema)
    out = []
    for e in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in e.path) or "(root)"
        out.append(f"[schema:{schema_file}] at {where}: {e.message}")
    return out


# ---------------------------------------------------------------- layer 2

def cross_file_errors(auth: Dict[str, Any], cmds: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    defined_levels = set((auth.get("levels") or {}).keys())
    declared_factors = set(auth.get("factors") or [])

    # R1: every referenced min_level exists in auth.yaml
    for cmd in cmds.get("commands", []):
        lvl = cmd.get("min_level")
        if lvl not in defined_levels:
            errors.append(
                f"[R1] command '{cmd.get('intent')}' requires min_level '{lvl}' "
                f"which is not defined in auth.yaml (defined: {sorted(defined_levels)})"
            )

    # R2: every factor a level uses is declared in factors
    for name, spec in (auth.get("levels") or {}).items():
        spec = spec or {}
        used = set(spec.get("requires", [])) | set(spec.get("requires_any", []))
        undeclared = used - declared_factors
        if undeclared:
            errors.append(
                f"[R2] level '{name}' uses factor(s) {sorted(undeclared)} "
                f"not declared in auth.yaml factors (declared: {sorted(declared_factors)})"
            )
    return errors


# ---------------------------------------------------------------- layer 3

def policy_warnings(cmds: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    for cmd in cmds.get("commands", []):
        intent = cmd.get("intent")
        if cmd.get("reversible") is False:
            if cmd.get("min_level") != "L3_explicit":
                warnings.append(
                    f"[W1] irreversible command '{intent}' is gated at "
                    f"'{cmd.get('min_level')}' -- consider L3_explicit "
                    f"(high-stakes actions should demand deliberate intent)"
                )
            if cmd.get("confirmation") == "none":
                warnings.append(
                    f"[W2] irreversible command '{intent}' has confirmation: none "
                    f"-- consider 'audio' or 'explicit'"
                )
    return warnings


# ---------------------------------------------------------------- driver

def validate(auth_path: Path, cmds_path: Path) -> Tuple[List[str], List[str]]:
    """Returns (errors, warnings)."""
    errors: List[str] = []

    def load(path: Path) -> Dict[str, Any] | None:
        if not path.exists():
            errors.append(f"file not found: {path}")
            return None
        data = yaml.safe_load(open(path))
        if not isinstance(data, dict):
            errors.append(f"{path} is not a YAML mapping")
            return None
        return data

    auth, cmds = load(auth_path), load(cmds_path)
    if errors:
        return errors, []

    errors += schema_errors(auth, "auth.schema.yaml")
    errors += schema_errors(cmds, "commands.schema.yaml")
    if errors:                       # cross-file checks need valid shapes
        return errors, []

    errors += cross_file_errors(auth, cmds)
    warnings = policy_warnings(cmds)
    return errors, warnings


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    errors, warnings = validate(Path(argv[1]), Path(argv[2]))

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")

    if errors:
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"\nOK: 0 errors, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
