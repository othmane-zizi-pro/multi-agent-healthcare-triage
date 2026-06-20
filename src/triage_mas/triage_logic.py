"""The deterministic triage engine — the authoritative safety backbone (CODE, not the model).

This module decides everything that, if a model got it wrong at 3 a.m. with no human, could
hurt a patient: which red flags fire, the ESI acuity, the disposition band, whether a slot
exists, and whether human approval is required. The LLM agents (see `agents.py`) narrate and
structure around these results; they cannot override them. This is the "what should CODE
decide" half of the three-way split [SDK 137], and the answer to reward-hacking: a model that
grades its own safety will eventually game it [DRL 147], [DRL 153], [SDK 64].

Every function here is pure (`World` is read-only), which makes the offline "logic-mode" evals
(`tests/test_triage_logic.py`) fully deterministic and reproducible.
"""

from __future__ import annotations

from .config import GovernanceConfig
from .schemas import (
    Disposition,
    DispositionBand,
    PatientCase,
    RedFlag,
    RedFlagRule,
    RiskAssessment,
    SchedulingProposal,
    Severity,
)

_SEVERITY_ORDER: dict[Severity, int] = {
    "info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4,
}
#: Disposition bands from most to least acute — the ONLY legal direction is "stay or escalate".
_BAND_ORDER: list[DispositionBand] = ["ED_NOW", "URGENT", "PRIMARY_CARE", "SELF_CARE"]


# ── Red-flag screen (deterministic safety) ────────────────────────────────────
def fired_rules(case: PatientCase, rules: list[RedFlagRule]) -> list[tuple[RedFlagRule, list[str]]]:
    """Return each rule that fires, with the evidence (findings/vitals) that triggered it."""
    out: list[tuple[RedFlagRule, list[str]]] = []
    findings = set(case.clinical_findings)
    for rule in rules:
        evidence: list[str] = []
        evidence += [f for f in rule.findings_any if f in findings]
        for cond in rule.vitals_any:
            if cond.matches(case.vitals):
                evidence.append(f"{cond.metric} {cond.op} {cond.value:g}")
        if evidence:
            out.append((rule, evidence))
    return out


def screen_red_flags(case: PatientCase, rules: list[RedFlagRule]) -> RiskAssessment:
    """The independent safety screen. Builds a RiskAssessment from the deterministic rule set —
    the model never sees this logic, it only relays the verdict."""
    fired = fired_rules(case, rules)
    flags = [
        RedFlag(code=r.code, label=r.label, severity=r.severity, evidence=ev)
        for r, ev in fired
    ]
    highest: Severity = "info"
    for f in flags:
        if _SEVERITY_ORDER[f.severity] > _SEVERITY_ORDER[highest]:
            highest = f.severity
    return RiskAssessment(
        red_flags=flags,
        highest_severity=highest,
        recommend_escalate=bool(flags),
        rationale=(
            "; ".join(f"{f.code} ({', '.join(f.evidence)})" for f in flags)
            if flags else "No red-flag rule fired on the authoritative findings/vitals."
        ),
    )


# ── Acuity (deterministic ESI) ────────────────────────────────────────────────
def compute_acuity(
    case: PatientCase, esi_map, fired, *, apply_red_flag_floor: bool = True
) -> tuple[int, DispositionBand]:
    """ESI = the MOST-acute (lowest-numbered) level implied by any present finding or dangerous
    vital. When `apply_red_flag_floor` is set (the governed risk VETO), a fired rule then floors
    the acuity to its `min_esi` and the band to its `forces_band`.

    The floor IS the veto: with it off (naive mode), an atypical presentation whose individual
    findings look low-acuity is NOT escalated even though a red-flag rule fired — exactly the
    under-triage failure the M6 demo exhibits. Explicit-acuity findings (e.g. classic radiating
    chest pain) are caught regardless, because they are acute on their own."""
    candidates: list[int] = []
    for f in case.clinical_findings:
        if f in esi_map.finding_acuity:
            candidates.append(int(esi_map.finding_acuity[f]))
    if any(cond.matches(case.vitals) for cond in esi_map.vitals_danger):
        candidates.append(int(esi_map.vitals_danger_esi))
    esi = min(candidates) if candidates else int(esi_map.default_esi)
    band: DispositionBand = esi_map.band_for_esi[str(esi)]

    if apply_red_flag_floor:
        for rule, _ev in fired:
            esi = min(esi, int(rule.min_esi))
        band = esi_map.band_for_esi[str(esi)]
        for rule, _ev in fired:
            if _BAND_ORDER.index(rule.forces_band) < _BAND_ORDER.index(band):
                band = rule.forces_band
    return esi, band


# ── Scheduling (the no-down-coding envelope) ──────────────────────────────────
def propose_slot(
    band: DispositionBand, clinic, *, enforce_no_down_coding: bool = True
) -> SchedulingProposal:
    """Book a slot in the ACUITY-LOCKED band. The band is decided before capacity is seen.

    Governed: if the band is full, OVERFLOW/divert — never down-code [DRL 153], [MAS 76-82].
    Naive: down-code to a lower-acuity band that has capacity — the under-triage collusion
    failure the M6 demo exhibits. The choice is the whole point of this function."""
    avail = [s for s in clinic.slots if s.band == band and s.available]
    if clinic.capacity.get(band, 0) > 0 and avail:
        slot = avail[0]
        return SchedulingProposal(
            band=band, slot_id=slot.slot_id, slot_time=slot.time,
            within_capacity=True, overflow=False,
            notes=f"Booked {slot.slot_id} in the acuity-correct band {band}.",
        )

    if enforce_no_down_coding:
        return SchedulingProposal(
            band=band, within_capacity=False, overflow=True,
            notes=f"Acuity-correct band {band} is full — OVERFLOW/divert (no down-coding).",
        )

    # NAIVE path: quietly fit the patient into a lower-acuity band that has room.
    idx = _BAND_ORDER.index(band)
    for lower in _BAND_ORDER[idx + 1:]:
        lavail = [s for s in clinic.slots if s.band == lower and s.available]
        if clinic.capacity.get(lower, 0) > 0 and lavail:
            slot = lavail[0]
            return SchedulingProposal(
                band=lower, slot_id=slot.slot_id, slot_time=slot.time,
                within_capacity=True, overflow=False,
                notes=f"DOWN-CODED from {band} to {lower} to fit capacity (UNSAFE).",
            )
    return SchedulingProposal(
        band=band, within_capacity=False, overflow=True,
        notes=f"Acuity-correct band {band} is full and no lower band has room.",
    )


# ── Final disposition assembly (deterministic) ────────────────────────────────
def requires_approval(esi: int, risk: RiskAssessment, esi_map) -> bool:
    """Critical-risk gate: ESI ≤ threshold OR any red flag ⇒ explicit human authorization
    required [Intro 96]. Monotonic on safety — it can only ADD an approval requirement."""
    return esi <= int(esi_map.approval_required_max_esi) or risk.recommend_escalate


def build_disposition(
    case: PatientCase, world, governance: GovernanceConfig | None = None
) -> tuple[Disposition, RiskAssessment, SchedulingProposal]:
    """Run the whole deterministic pipeline for one case (the logic-mode reference path).

    Order matters: screen → lock acuity → THEN schedule. Capacity can never feed back into
    acuity. Returns the disposition plus the risk + scheduling artifacts for the audit trail."""
    gov = governance or GovernanceConfig.governed()
    fired = fired_rules(case, world.red_flag_rules)
    risk = screen_red_flags(case, world.red_flag_rules)
    # The risk VETO == applying the red-flag floor. Off in naive mode → atypical cases under-triage.
    esi, band = compute_acuity(case, world.esi, fired, apply_red_flag_floor=gov.risk_veto_enabled)

    sched = propose_slot(band, world.clinic, enforce_no_down_coding=gov.enforce_no_down_coding)
    # In naive mode the scheduler may have down-coded the band; the disposition follows it (harm).
    final_band = sched.band if not gov.enforce_no_down_coding else band

    action = world.esi.action_for_band[final_band]
    if sched.overflow:
        action += " [capacity overflow — divert / activate on-call; do NOT down-code]"

    needs = requires_approval(esi, risk, world.esi)
    disp = Disposition(
        esi=esi,  # acuity is reported as decided, independent of the booked band
        band=final_band,
        action=action,
        red_flags=risk.red_flags,
        requires_human_approval=needs and gov.approval_gate_enabled,
        approval_reason=(
            f"ESI {esi} / red flags {[f.code for f in risk.red_flags]}" if needs else None
        ),
        committed=False,
        rationale=risk.rationale,
        summary=(
            f"ESI {esi} → {final_band}. "
            + ("Red flags: " + ", ".join(f.code for f in risk.red_flags) + ". " if risk.red_flags else "")
            + action
        ),
    )
    return disp, risk, sched
