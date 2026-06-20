"""Local run context (`RunContextWrapper`) — application state the model never sees [SDK 34].

Holds the read-only world, the specific case under triage, the governance config, the locked
acuity band (set by the supervisor in CODE before the scheduler runs, so the model cannot
down-code), and the tool-call audit log. Tools read this; the model does not.
See local vs model context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import GovernanceConfig
from .fixtures import World, load_world
from .schemas import DispositionBand, PatientCase


@dataclass
class TriageContext:
    world: World
    case: PatientCase
    trace_id: str
    governance: GovernanceConfig
    #: Set by the supervisor (code) after acuity is locked; the scheduler tool reads it so the
    #: model cannot choose a band (and therefore cannot down-code to fit capacity).
    locked_band: Optional[DispositionBand] = None
    #: Approval-gate signals (read by the commit tool's conditional `needs_approval`).
    pending_requires_approval: bool = False
    commit_executed: bool = False
    commit_record: Optional[dict] = None
    tool_calls: list[dict] = field(default_factory=list)

    def log_tool(self, name: str, args: dict, summary: str) -> None:
        self.tool_calls.append({"tool": name, "args": args, "summary": summary})


def build_context(
    case_id: str,
    trace_id: str,
    governance: GovernanceConfig | None = None,
) -> TriageContext:
    world = load_world()
    return TriageContext(
        world=world,
        case=world.get_case(case_id),
        trace_id=trace_id,
        governance=governance or GovernanceConfig.governed(),
    )
