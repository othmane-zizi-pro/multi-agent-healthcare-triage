"""M1 — the synthetic fixture world loads, is internally consistent, and is well-formed."""

from __future__ import annotations

from triage_mas.fixtures import all_case_ids, load_world


def test_world_loads():
    w = load_world()
    assert len(w.cases) >= 10, "plan calls for ~10 synthetic cases"
    assert len(w.red_flag_rules) >= 6
    assert w.esi.band_for_esi and w.clinic.on_call_clinician


def test_required_edge_cases_present():
    kinds = {c.edge_kind for c in load_world().cases.values() if c.edge}
    for required in {"prompt_injection", "missing_info", "capacity_conflict", "undertriage_trap"}:
        assert required in kinds, f"missing required edge case: {required}"


def test_every_finding_in_cases_has_an_acuity_or_is_a_red_flag():
    """No case may carry a finding the deterministic maps don't recognize (else silent gaps)."""
    w = load_world()
    known = set(w.esi.finding_acuity)
    for rule in w.red_flag_rules:
        known.update(rule.findings_any)
    for case in w.cases.values():
        for f in case.clinical_findings:
            assert f in known, f"finding {f!r} in {case.case_id} is unmapped"


def test_gold_bands_match_esi_mapping():
    """Each case's gold band must be the band the ESI map assigns to its gold ESI."""
    w = load_world()
    for case in w.cases.values():
        expected_band = w.esi.band_for_esi[str(case.gold.esi)]
        assert case.gold.band == expected_band, (
            f"{case.case_id}: gold band {case.gold.band} != band_for_esi[{case.gold.esi}] "
            f"= {expected_band}"
        )


def test_gold_approval_consistent_with_esi_threshold():
    w = load_world()
    for case in w.cases.values():
        forced = case.gold.esi <= w.esi.approval_required_max_esi or case.gold.red_flag
        assert case.gold.requires_approval == forced, (
            f"{case.case_id}: gold requires_approval inconsistent with ESI/red-flag"
        )


def test_all_case_ids_unique_and_listable():
    ids = all_case_ids()
    assert len(ids) == len(set(ids))
