"""Typed data contracts — the spine of the system [SDK 30-31], [MAS 50-61].

Three families live here:

1. **The fixture world** (`PatientCase`, `Vitals`, `RedFlagRule`, `EsiMap`, `Clinic`) — the
   immutable, synthetic source of truth the agents reason over.
2. **The typed message envelope + payloads** (`Message` + the `*Payload` models) — the
   communication contract [MAS 50-61]: every inter-agent exchange is a typed `Message` with
   headers (`trace_id`, `case_id`, `from_agent`, `to_agent`, `msg_type`, `deadline`,
   `idempotency_key`, `seq`) and a discriminated-union `payload`. A `model_validator`
   enforces that `msg_type` and `payload.kind` agree — so a malformed message cannot exist.
3. **The blackboard** (`CaseFile`) — the shared, auditable case record [MAS 18, 50-61].
   Each section is owned by exactly one agent; `post()` enforces write discipline (only the
   section owner or the supervisor may write a section) and appends an audit trail.

The model never grades safety: `RiskAssessment`/`Disposition` carry fields the *code* fills
from deterministic tools, not prose the model invents ([DRL 153], [SDK 64]).
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

# ── Vocabularies ──────────────────────────────────────────────────────────────
AgentName = Literal["intake", "risk", "specialist", "scheduler", "supervisor", "clinician"]
Severity = Literal["info", "low", "moderate", "high", "critical"]
#: ESI = Emergency Severity Index. 1 = resuscitation (most acute) … 5 = non-urgent.
ESILevel = Literal[1, 2, 3, 4, 5]
DispositionBand = Literal["ED_NOW", "URGENT", "PRIMARY_CARE", "SELF_CARE"]

MsgType = Literal[
    "CaseIntake",
    "ClarificationRequest",
    "RiskAssessment",
    "SpecialistOpinion",
    "SchedulingProposal",
    "DispositionDraft",
    "ApprovalRequest",
    "ApprovalDecision",
    "AuditEvent",
]


# ── The fixture world (synthetic, immutable) ──────────────────────────────────
class Vitals(BaseModel):
    """Structured vital signs — the *authoritative* channel (like a monitor feed / coded EHR
    data), NOT free text. The deterministic safety screen reads these, never the narrative."""

    hr: Optional[int] = None       # heart rate, bpm
    rr: Optional[int] = None       # respiratory rate, /min
    sbp: Optional[int] = None      # systolic blood pressure, mmHg
    spo2: Optional[int] = None     # oxygen saturation, %
    temp_c: Optional[float] = None # temperature, °C
    gcs: Optional[int] = None      # Glasgow Coma Scale, 3-15
    pain: Optional[int] = None     # 0-10


class GoldLabel(BaseModel):
    """The known-correct answer for a synthetic case — used only by evals, never by agents."""

    esi: ESILevel
    band: DispositionBand
    red_flag: bool
    requires_approval: bool
    notes: str = ""
    #: For abuse/guardrail cases: the guardrail we expect to trip (e.g. "PROMPT_INJECTION").
    expect_guardrail: Optional[str] = None


class PatientCase(BaseModel):
    """One synthetic presentation. `narrative` is UNTRUSTED free text; `vitals` +
    `clinical_findings` are the authoritative structured channel the safety code trusts."""

    case_id: str
    title: str
    arrival_mode: Literal["walk_in", "ambulance", "phone", "portal"]
    age: int
    sex: Optional[str] = None
    narrative: str
    vitals: Vitals = Field(default_factory=Vitals)
    clinical_findings: list[str] = Field(default_factory=list)
    edge: bool = False
    edge_kind: Optional[str] = None
    gold: GoldLabel


class VitalCondition(BaseModel):
    """A deterministic threshold on one vital, e.g. spo2 < 90."""

    metric: Literal["hr", "rr", "sbp", "spo2", "temp_c", "gcs", "pain"]
    op: Literal["<", "<=", ">", ">=", "=="]
    value: float

    def matches(self, vitals: Vitals) -> bool:
        got = getattr(vitals, self.metric, None)
        if got is None:
            return False
        if self.op == "<":
            return got < self.value
        if self.op == "<=":
            return got <= self.value
        if self.op == ">":
            return got > self.value
        if self.op == ">=":
            return got >= self.value
        return got == self.value


class RedFlagRule(BaseModel):
    """One deterministic safety rule. Fires if ANY listed finding is present OR ANY vitals
    condition is true. Firing forces a band floor and an ESI ceiling — code, not prose."""

    code: str
    label: str
    severity: Severity
    findings_any: list[str] = Field(default_factory=list)
    vitals_any: list[VitalCondition] = Field(default_factory=list)
    forces_band: DispositionBand = "ED_NOW"
    min_esi: ESILevel = 2  # the most-acute (lowest-numbered) ESI this flag permits


class EsiMap(BaseModel):
    """Deterministic findings/vitals → ESI acuity → disposition band → action mapping."""

    finding_acuity: dict[str, ESILevel]
    vitals_danger: list[VitalCondition] = Field(default_factory=list)
    vitals_danger_esi: ESILevel = 2
    default_esi: ESILevel = 5
    band_for_esi: dict[str, DispositionBand]
    action_for_band: dict[str, str]
    #: ESI ≤ this forces human-clinician approval (critical risk → explicit authorization).
    approval_required_max_esi: ESILevel = 2


class ClinicSlot(BaseModel):
    slot_id: str
    band: DispositionBand
    time: str
    available: bool = True


class Clinic(BaseModel):
    """The scheduler's constrained world — the inventory-RL-flavored sub-problem."""

    on_call_clinician: str
    capacity: dict[str, int]          # band -> remaining capacity
    slots: list[ClinicSlot] = Field(default_factory=list)


# ── Typed payloads (the discriminated union carried by every Message) ──────────
class RedFlag(BaseModel):
    code: str
    label: str
    severity: Severity
    evidence: list[str] = Field(default_factory=list)


class IntakeSummary(BaseModel):
    kind: Literal["intake_summary"] = "intake_summary"
    chief_complaint: str = ""
    structured_symptoms: list[str] = Field(default_factory=list)
    onset: str = ""
    pertinent_negatives: list[str] = Field(default_factory=list)
    complete: bool = True
    missing_info: list[str] = Field(default_factory=list)
    notes: str = ""


class ClarificationRequestPayload(BaseModel):
    kind: Literal["clarification_request"] = "clarification_request"
    questions: list[str] = Field(default_factory=list)
    round: int = 1


class RiskAssessment(BaseModel):
    kind: Literal["risk_assessment"] = "risk_assessment"
    #: Filled by the DETERMINISTIC screen (code), not the model.
    red_flags: list[RedFlag] = Field(default_factory=list)
    highest_severity: Severity = "info"
    recommend_escalate: bool = False  # the independent VETO signal
    rationale: str = ""


class SpecialistOpinion(BaseModel):
    kind: Literal["specialist_opinion"] = "specialist_opinion"
    differential: list[str] = Field(default_factory=list)
    suggested_esi: Optional[ESILevel] = None
    reasoning: str = ""
    guideline_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class SchedulingProposal(BaseModel):
    kind: Literal["scheduling_proposal"] = "scheduling_proposal"
    #: The band is LOCKED by acuity before the scheduler sees capacity (no down-coding).
    band: DispositionBand
    slot_id: Optional[str] = None
    slot_time: Optional[str] = None
    within_capacity: bool = True
    overflow: bool = False  # acuity-correct band is full → escalate/divert, never down-code
    notes: str = ""


class Disposition(BaseModel):
    kind: Literal["disposition"] = "disposition"
    esi: ESILevel
    band: DispositionBand
    action: str = ""
    red_flags: list[RedFlag] = Field(default_factory=list)
    requires_human_approval: bool = False
    approval_reason: Optional[str] = None
    committed: bool = False  # nothing patient-facing is committed until approved
    rationale: str = ""
    summary: str = ""


class ApprovalRequest(BaseModel):
    kind: Literal["approval_request"] = "approval_request"
    reason: str = ""
    esi: ESILevel
    band: DispositionBand


class ApprovalDecision(BaseModel):
    kind: Literal["approval_decision"] = "approval_decision"
    approved: bool
    decided_by: str = "on_call_clinician"
    note: str = ""


class AuditEvent(BaseModel):
    kind: Literal["audit_event"] = "audit_event"
    event: str
    detail: str = ""


Payload = Annotated[
    Union[
        IntakeSummary,
        ClarificationRequestPayload,
        RiskAssessment,
        SpecialistOpinion,
        SchedulingProposal,
        Disposition,
        ApprovalRequest,
        ApprovalDecision,
        AuditEvent,
    ],
    Field(discriminator="kind"),
]

#: msg_type → the payload `kind` it must carry. The contract that makes a Message well-typed.
MSG_TYPE_TO_KIND: dict[str, str] = {
    "CaseIntake": "intake_summary",
    "ClarificationRequest": "clarification_request",
    "RiskAssessment": "risk_assessment",
    "SpecialistOpinion": "specialist_opinion",
    "SchedulingProposal": "scheduling_proposal",
    "DispositionDraft": "disposition",
    "ApprovalRequest": "approval_request",
    "ApprovalDecision": "approval_decision",
    "AuditEvent": "audit_event",
}

#: msg_type → the blackboard section it writes (None = transcript-only message).
MSG_TYPE_TO_SECTION: dict[str, Optional[str]] = {
    "CaseIntake": "intake",
    "RiskAssessment": "risk",
    "SpecialistOpinion": "specialist",
    "SchedulingProposal": "scheduling",
    "DispositionDraft": "disposition",
    "ClarificationRequest": None,
    "ApprovalRequest": None,
    "ApprovalDecision": None,
    "AuditEvent": None,
}

#: section → the single agent that owns its write. The supervisor may also write any section.
SECTION_OWNER: dict[str, AgentName] = {
    "intake": "intake",
    "risk": "risk",
    "specialist": "specialist",
    "scheduling": "scheduler",
    "disposition": "supervisor",
}


class Message(BaseModel):
    """The typed message envelope [MAS 50-61]. Headers + a discriminated-union payload."""

    trace_id: str
    case_id: str
    from_agent: AgentName
    to_agent: AgentName
    msg_type: MsgType
    seq: int = 0
    created_at: str = ""
    deadline: Optional[str] = None
    idempotency_key: str = ""
    confidence: Optional[float] = None
    evidence: list[str] = Field(default_factory=list)
    payload: Payload

    @model_validator(mode="after")
    def _msg_type_matches_payload(self) -> "Message":
        expected = MSG_TYPE_TO_KIND[self.msg_type]
        if self.payload.kind != expected:
            raise ValueError(
                f"msg_type {self.msg_type!r} requires payload.kind {expected!r}, "
                f"got {self.payload.kind!r}"
            )
        return self


# ── The blackboard ────────────────────────────────────────────────────────────
class WriteDisciplineError(PermissionError):
    """Raised when an agent tries to write a blackboard section it does not own [MAS 112]."""


class CaseFile(BaseModel):
    """The shared, auditable case record [MAS 18]. Star-routed: agents read the whole file;
    only the section owner (or the supervisor) writes a section, via `post()`."""

    trace_id: str
    case_id: str
    governance_mode: Literal["governed", "naive"] = "governed"

    # sections (each owned by one agent)
    intake: Optional[IntakeSummary] = None
    risk: Optional[RiskAssessment] = None
    specialist: Optional[SpecialistOpinion] = None
    scheduling: Optional[SchedulingProposal] = None
    disposition: Optional[Disposition] = None

    # audit / control
    transcript: list[Message] = Field(default_factory=list)
    red_flag_raised: bool = False     # the hard stop-rule latch (monotonic: never un-set)
    clarification_rounds: int = 0
    _seq: int = 0

    def post(self, message: Message) -> Message:
        """Append a message to the transcript, enforcing write discipline + idempotency, and
        (if the message writes a section) update that section. Returns the applied message.

        Idempotency [MAS 50-61]: a repeated `idempotency_key` is dropped (exactly-once), which
        neutralizes front-running / duplicate-delivery (plan §3.5). Write discipline [MAS 112]:
        only the section owner (or the supervisor) may write a section."""
        if message.idempotency_key:
            for prior in self.transcript:
                if prior.idempotency_key == message.idempotency_key:
                    return prior  # already applied — drop the duplicate

        section = MSG_TYPE_TO_SECTION.get(message.msg_type)
        if section is not None:
            owner = SECTION_OWNER[section]
            if message.from_agent not in {owner, "supervisor"}:
                raise WriteDisciplineError(
                    f"{message.from_agent!r} may not write section {section!r} "
                    f"(owned by {owner!r})"
                )
        self._seq += 1
        message.seq = self._seq
        self.transcript.append(message)
        if section is not None:
            setattr(self, section, message.payload)
        # The RED_FLAG stop rule latches the moment any risk assessment recommends escalation.
        if isinstance(message.payload, RiskAssessment) and message.payload.recommend_escalate:
            self.red_flag_raised = True
        return message
