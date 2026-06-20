"""Read-only loaders for the synthetic fixture world.

The JSON files in `data/` are the **immutable source of truth** (the [[runner-and-state]]
"recomputed" axis): read fresh, never mutated. `World` bundles the four fixtures so the
deterministic tools have a single read-only handle. All data is synthetic — no real PHI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .schemas import Clinic, EsiMap, PatientCase, RedFlagRule


def _data_dir() -> Path:
    """`data/` at the project root, overridable via TRIAGE_DATA_DIR (used by tests)."""
    env = os.getenv("TRIAGE_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"


def _load_json(name: str) -> dict:
    with open(_data_dir() / name, encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class World:
    """The whole synthetic world, read-only."""

    cases: dict[str, PatientCase]
    red_flag_rules: list[RedFlagRule]
    esi: EsiMap
    clinic: Clinic

    def get_case(self, case_id: str) -> PatientCase:
        try:
            return self.cases[case_id]
        except KeyError:
            raise KeyError(
                f"unknown case_id {case_id!r}; known: {sorted(self.cases)}"
            ) from None


@lru_cache(maxsize=1)
def load_world() -> World:
    cases_raw = _load_json("cases.json")["cases"]
    cases = {c["case_id"]: PatientCase(**c) for c in cases_raw}
    rules = [RedFlagRule(**r) for r in _load_json("red_flags.json")["rules"]]
    esi = EsiMap(**{k: v for k, v in _load_json("esi.json").items() if not k.startswith("_")})
    clinic = Clinic(**{k: v for k, v in _load_json("clinic.json").items() if not k.startswith("_")})
    return World(cases=cases, red_flag_rules=rules, esi=esi, clinic=clinic)


def get_case(case_id: str) -> PatientCase:
    return load_world().get_case(case_id)


def all_case_ids() -> list[str]:
    return list(load_world().cases.keys())
