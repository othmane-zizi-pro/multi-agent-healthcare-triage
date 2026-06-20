"""M2 — the deterministic engine (logic-mode evals). No API, fully reproducible.

These are the safety guarantees in code: every synthetic case's deterministic disposition
must match its gold label, and the two structural invariants — the risk veto and the
no-down-coding envelope — must hold. If these pass, the LLM layer on top cannot make the
*safety* decision wrong; it can only narrate it.
"""

from __future__ import annotations

import pytest

from triage_mas.config import GovernanceConfig
from triage_mas.fixtures import load_world
from triage_mas.triage_logic import (
    build_disposition,
    compute_acuity,
    fired_rules,
    propose_slot,
    screen_red_flags,
)

WORLD = load_world()
CASES = list(WORLD.cases.values())
CASE_IDS = [c.case_id for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_deterministic_disposition_matches_gold(case):
    disp, risk, _sched = build_disposition(case, WORLD, GovernanceConfig.governed())
    assert disp.esi == case.gold.esi, f"{case.case_id}: ESI {disp.esi} != gold {case.gold.esi}"
    assert disp.band == case.gold.band, f"{case.case_id}: band {disp.band} != gold {case.gold.band}"
    assert bool(risk.red_flags) == case.gold.red_flag, f"{case.case_id}: red-flag mismatch"
    assert disp.requires_human_approval == case.gold.requires_approval, (
        f"{case.case_id}: approval {disp.requires_human_approval} != gold {case.gold.requires_approval}"
    )


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_red_flag_cases_recommend_escalation(case):
    risk = screen_red_flags(case, WORLD.red_flag_rules)
    assert risk.recommend_escalate == case.gold.red_flag


def test_prompt_injection_case_still_escalates_on_findings():
    """The injection narrative must NOT lower acuity — the screen runs on findings, not text."""
    case = WORLD.get_case("prompt_injection")
    disp, risk, _ = build_disposition(case, WORLD, GovernanceConfig.governed())
    assert risk.recommend_escalate is True
    assert disp.band == "ED_NOW" and disp.esi == 2


def test_undertriage_trap_is_caught_by_code():
    """Benign narrative, dangerous findings — the deterministic screen must still escalate."""
    case = WORLD.get_case("undertriage_trap")
    _, risk, _ = build_disposition(case, WORLD, GovernanceConfig.governed())
    assert any(f.code == "ACS_CHEST_PAIN" for f in risk.red_flags)


def test_naive_under_triages_atypical_acs_but_governed_catches_it():
    """The emergence demo's headline: same case, two incentive configs, two acuities.

    Governed: the red-flag veto floors the atypical 'indigestion' presentation to ED_NOW.
    Naive: the veto is off, so the individually-low-acuity findings stand → URGENT (under-triage).
    A CLASSIC presentation (chest_pain_acs) is caught either way — only the ATYPICAL one flips."""
    trap = WORLD.get_case("undertriage_trap")
    gov_disp, _, _ = build_disposition(trap, WORLD, GovernanceConfig.governed())
    naive_disp, _, _ = build_disposition(trap, WORLD, GovernanceConfig.naive())
    assert (gov_disp.esi, gov_disp.band) == (2, "ED_NOW")
    # Naive COMPOUNDS two failures: veto-off (ED_NOW→URGENT) then scheduler down-code
    # (URGENT→PRIMARY_CARE) — an ED-bound patient routed to ROUTINE primary care.
    assert (naive_disp.esi, naive_disp.band) == (3, "PRIMARY_CARE"), "naive must under-triage the trap"

    classic = WORLD.get_case("chest_pain_acs")
    c_gov, _, _ = build_disposition(classic, WORLD, GovernanceConfig.governed())
    c_naive, _, _ = build_disposition(classic, WORLD, GovernanceConfig.naive())
    assert c_gov.band == c_naive.band == "ED_NOW", "explicit ACS is caught in both modes"


def test_governed_scheduler_never_down_codes():
    """Capacity conflict: governed mode overflows in the SAME band, never a lower one."""
    case = WORLD.get_case("capacity_conflict")
    disp, _, sched = build_disposition(case, WORLD, GovernanceConfig.governed())
    assert sched.overflow is True
    assert sched.band == "URGENT" and disp.band == "URGENT"


def test_naive_scheduler_down_codes_demonstrating_the_failure():
    """The same conflict under naive incentives down-codes URGENT → a lower band (the bug)."""
    case = WORLD.get_case("capacity_conflict")
    disp, _, sched = build_disposition(case, WORLD, GovernanceConfig.naive())
    assert sched.band != "URGENT", "naive mode should down-code to fit capacity"
    assert disp.band == sched.band  # the disposition inherits the unsafe down-code


def test_pediatric_high_hr_does_not_false_trip_critical_vitals():
    case = WORLD.get_case("pediatric_fever")
    fired = fired_rules(case, WORLD.red_flag_rules)
    assert fired == [], "pediatric HR 150 must not fire CRITICAL_VITALS"


def test_acuity_is_locked_before_capacity():
    """compute_acuity depends only on findings/vitals/rules — never on the clinic state."""
    case = WORLD.get_case("capacity_conflict")
    fired = fired_rules(case, WORLD.red_flag_rules)
    esi_full, band_full = compute_acuity(case, WORLD.esi, fired)
    # Booking outcome differs by capacity, but acuity must be identical regardless.
    assert (esi_full, band_full) == (3, "URGENT")


def test_overflow_when_band_full():
    p = propose_slot("URGENT", WORLD.clinic, enforce_no_down_coding=True)
    assert p.overflow and not p.within_capacity and p.band == "URGENT"
