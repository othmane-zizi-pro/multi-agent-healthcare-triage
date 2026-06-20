"""M1 — schema validity + the communication contract + blackboard write discipline.

Offline, no API. These give the interaction-level "message-schema validity" metric
(plan §3.7) its teeth: a malformed message simply cannot be constructed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from triage_mas.schemas import (
    MSG_TYPE_TO_KIND,
    CaseFile,
    Disposition,
    IntakeSummary,
    Message,
    RiskAssessment,
    SchedulingProposal,
    WriteDisciplineError,
)


def _msg(from_agent, msg_type, payload, to_agent="supervisor", idempotency_key=None):
    return Message(
        trace_id="t1",
        case_id="c1",
        from_agent=from_agent,
        to_agent=to_agent,
        msg_type=msg_type,
        idempotency_key=idempotency_key if idempotency_key is not None
        else f"{from_agent}:{msg_type}",
        payload=payload,
    )


def test_every_msg_type_has_a_payload_kind():
    # The contract table must cover every declared message type.
    from triage_mas.schemas import MsgType
    import typing

    declared = set(typing.get_args(MsgType))
    assert declared == set(MSG_TYPE_TO_KIND), "MSG_TYPE_TO_KIND must cover all MsgType values"


def test_well_typed_message_validates():
    m = _msg("intake", "CaseIntake", IntakeSummary(chief_complaint="chest pain"))
    assert m.payload.kind == "intake_summary"
    assert m.msg_type == "CaseIntake"


def test_msg_type_payload_mismatch_is_rejected():
    # A RiskAssessment payload under a CaseIntake msg_type must fail validation.
    with pytest.raises(ValidationError):
        _msg("intake", "CaseIntake", RiskAssessment())


def test_discriminated_union_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        Message(
            trace_id="t",
            case_id="c",
            from_agent="intake",
            to_agent="supervisor",
            msg_type="CaseIntake",
            payload={"kind": "not_a_real_kind"},
        )


def test_blackboard_post_writes_owned_section():
    cf = CaseFile(trace_id="t", case_id="c")
    cf.post(_msg("intake", "CaseIntake", IntakeSummary(chief_complaint="x")))
    assert cf.intake is not None and cf.intake.chief_complaint == "x"
    assert len(cf.transcript) == 1 and cf.transcript[0].seq == 1


def test_blackboard_rejects_non_owner_write():
    cf = CaseFile(trace_id="t", case_id="c")
    # scheduler may not write the risk section
    with pytest.raises(WriteDisciplineError):
        cf.post(_msg("scheduler", "RiskAssessment", RiskAssessment()))


def test_supervisor_may_write_any_section():
    cf = CaseFile(trace_id="t", case_id="c")
    cf.post(_msg("supervisor", "DispositionDraft",
                 Disposition(esi=2, band="ED_NOW")))
    assert cf.disposition is not None and cf.disposition.esi == 2


def test_red_flag_latch_sets_on_escalating_risk():
    cf = CaseFile(trace_id="t", case_id="c")
    assert cf.red_flag_raised is False
    cf.post(_msg("risk", "RiskAssessment",
                 RiskAssessment(recommend_escalate=True, highest_severity="critical")))
    assert cf.red_flag_raised is True


def test_idempotent_post_drops_duplicate_key():
    cf = CaseFile(trace_id="t", case_id="c")
    cf.post(_msg("intake", "CaseIntake", IntakeSummary(chief_complaint="a"),
                 idempotency_key="dup"))
    # A second message with the same idempotency_key is dropped (exactly-once).
    cf.post(_msg("intake", "CaseIntake", IntakeSummary(chief_complaint="b"),
                 idempotency_key="dup"))
    assert len(cf.transcript) == 1
    assert cf.intake.chief_complaint == "a"  # the first one stuck


def test_seq_is_monotonic():
    cf = CaseFile(trace_id="t", case_id="c")
    cf.post(_msg("intake", "CaseIntake", IntakeSummary()))
    cf.post(_msg("risk", "RiskAssessment", RiskAssessment()))
    cf.post(_msg("scheduler", "SchedulingProposal", SchedulingProposal(band="URGENT")))
    assert [m.seq for m in cf.transcript] == [1, 2, 3]
