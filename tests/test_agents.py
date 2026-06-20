"""M2 — worker agents are constructed with the right contracts (offline, no API)."""

from __future__ import annotations

from triage_mas.agents import build_workers
from triage_mas.config import supports_temperature
from triage_mas.schemas import (
    IntakeSummary,
    RiskAssessment,
    SchedulingProposal,
    SpecialistOpinion,
)


def test_four_workers_with_expected_output_types():
    w = build_workers(model="gpt-4.1")
    assert set(w) == {"intake", "risk", "specialist", "scheduler"}
    assert w["intake"].output_type is IntakeSummary
    assert w["risk"].output_type is RiskAssessment
    assert w["specialist"].output_type is SpecialistOpinion
    assert w["scheduler"].output_type is SchedulingProposal


def test_tool_permissions_are_distinct():
    w = build_workers(model="gpt-4.1")
    names = {role: {t.name for t in a.tools} for role, a in w.items()}
    assert names["intake"] == set(), "intake has no tools (no safety authority)"
    assert names["risk"] == {"run_red_flag_screen"}
    assert names["specialist"] == {"lookup_clinical_guideline"}
    assert names["scheduler"] == {"book_clinic_slot"}


def test_reasoning_models_omit_temperature():
    # gpt-5.x rejects temperature; gpt-4.x accepts it.
    assert supports_temperature("gpt-4.1") is True
    assert supports_temperature("gpt-5.4-mini") is False
    w5 = build_workers(model="gpt-5.4-mini")
    assert w5["risk"].model_settings.temperature is None
    w4 = build_workers(model="gpt-4.1")
    assert w4["risk"].model_settings.temperature == 0
