"""Typed function tools — where model intent meets app authority [SDK 36].

Three tools, each a distinct trust boundary (plan §3.1, §3.6):

  * `run_red_flag_screen`   — risk agent. Returns the DETERMINISTIC screen. The model relays
                              it; it cannot edit the verdict [DRL 153], [SDK 64].
  * `lookup_clinical_guideline` — specialist agent. A mocked **MCP** server (clinical-guideline
                              lookup); PHI/guideline access is an auth-scope decision [MAS 95].
  * `book_clinic_slot`      — scheduler agent. A mocked **A2A** seam to the clinic/EHR. Reads the
                              acuity-LOCKED band from local context, so the model cannot
                              down-code to fit capacity [MAS 92-99], [MAS 76-82].

The first parameter `wrapper: RunContextWrapper[TriageContext]` is injected by the SDK and is
never shown to the model (it carries [[local-vs-model-context|local context]]).
"""

from __future__ import annotations

from agents import RunContextWrapper, function_tool

from . import triage_logic
from .context import TriageContext
from .schemas import RiskAssessment, SchedulingProposal

# ── Mocked MCP clinical-guideline server (the specialist's external tool) ──────
_GUIDELINE_KB: dict[str, dict] = {
    "chest_pain": {
        "summary": "Treat undifferentiated chest pain as possible ACS until excluded; obtain "
                   "ECG within 10 minutes; do not rely on a reassuring story in diabetics/elderly.",
        "refs": ["AHA/ACC ACS guideline (synthetic)", "ESI handbook v4 (synthetic)"],
    },
    "stroke": {
        "summary": "FAST-positive findings are time-critical; activate stroke pathway; last-known-"
                   "well time drives thrombolysis eligibility.",
        "refs": ["AHA stroke guideline (synthetic)"],
    },
    "abdominal_pain": {
        "summary": "RLQ pain with nausea: keep appendicitis on the differential; serial exams; "
                   "do not discharge ambiguous cases without follow-up.",
        "refs": ["Surgical triage protocol (synthetic)"],
    },
    "anaphylaxis": {
        "summary": "Airway/breathing involvement is ESI-1; IM epinephrine first-line; biphasic "
                   "reactions require observation.",
        "refs": ["Anaphylaxis guideline (synthetic)"],
    },
    "fever_pediatric": {
        "summary": "Toddler fever: assess hydration, activity, and source; most are URGENT not "
                   "emergent if well-perfused and maintaining intake.",
        "refs": ["Pediatric fever pathway (synthetic)"],
    },
}


@function_tool
def run_red_flag_screen(wrapper: RunContextWrapper[TriageContext]) -> RiskAssessment:
    """Run the deterministic red-flag safety screen on THIS case's authoritative findings and
    vitals. Returns the fired red flags, the highest severity, and whether escalation is
    recommended. This is the source of truth for safety — relay it, do not second-guess it."""
    ctx = wrapper.context
    risk = triage_logic.screen_red_flags(ctx.case, ctx.world.red_flag_rules)
    ctx.log_tool("run_red_flag_screen", {"case_id": ctx.case.case_id},
                 f"escalate={risk.recommend_escalate} flags={[f.code for f in risk.red_flags]}")
    return risk


@function_tool
def lookup_clinical_guideline(
    wrapper: RunContextWrapper[TriageContext], topic: str
) -> dict:
    """Look up a clinical guideline from the (mocked) guideline service [MCP boundary].

    Args:
        topic: a condition key, e.g. "chest_pain", "stroke", "abdominal_pain", "anaphylaxis",
               "fever_pediatric". Unknown topics return a generic, conservative note.
    """
    ctx = wrapper.context
    key = topic.strip().lower().replace(" ", "_")
    entry = _GUIDELINE_KB.get(key, {
        "summary": "No specific guideline found; default to the more cautious disposition and "
                   "recommend in-person assessment if uncertain.",
        "refs": ["general triage principles (synthetic)"],
    })
    ctx.log_tool("lookup_clinical_guideline", {"topic": topic}, f"{len(entry['refs'])} ref(s)")
    return entry


@function_tool
def book_clinic_slot(wrapper: RunContextWrapper[TriageContext]) -> SchedulingProposal:
    """Propose a clinic slot in the acuity-LOCKED band [A2A boundary to the clinic/EHR].

    The band is fixed by the supervisor before this runs (from local context); you do not and
    cannot choose it. If the correct band is full, this returns an overflow/divert — it will
    never silently move the patient to a lower-acuity band to make them fit."""
    ctx = wrapper.context
    if ctx.locked_band is None:
        raise RuntimeError("book_clinic_slot called before the acuity band was locked.")
    proposal = triage_logic.propose_slot(
        ctx.locked_band, ctx.world.clinic,
        enforce_no_down_coding=ctx.governance.enforce_no_down_coding,
    )
    ctx.log_tool("book_clinic_slot", {"locked_band": ctx.locked_band},
                 f"band={proposal.band} slot={proposal.slot_id} overflow={proposal.overflow}")
    return proposal
