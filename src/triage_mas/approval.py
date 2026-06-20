"""Human-in-the-loop approval gate — the SDK `needs_approval` primitive [SDK 64-71].

Nothing patient-facing is COMMITTED until a high-acuity disposition is approved by the
on-call clinician. The commit runs through a single approval-gated tool whose `needs_approval`
is a *callable*: it pauses the run (interruption) only when the deterministic pipeline says the
disposition requires human authorization (ESI ≤ threshold or a red flag) [Intro 96]. Low-acuity
dispositions commit immediately. Resume is `RunState.approve()` / `.reject()` — the same run,
not a new turn (human approval, runner and state).

This is the "what should a HUMAN decide" third of the three-way split [SDK 137].
"""

from __future__ import annotations

from typing import Any

from agents import Agent, ModelSettings, RunContextWrapper, function_tool

from .config import resolve_model, supports_temperature
from .context import TriageContext

COMMIT_APPROVAL_RULE = "HIGH_ACUITY_COMMIT_APPROVAL"


async def _needs_commit_approval(
    ctx: RunContextWrapper[TriageContext], params: dict[str, Any], call_id: str
) -> bool:
    """Pause for the clinician iff the deterministic pipeline flagged this disposition."""
    return bool(ctx.context.pending_requires_approval)


@function_tool(needs_approval=_needs_commit_approval)
def commit_disposition(
    wrapper: RunContextWrapper[TriageContext],
    esi: int,
    band: str,
    action: str,
) -> str:
    """Commit the final triage disposition (the one patient-facing side effect).

    GATED: for a high-acuity disposition this pauses for on-call-clinician approval before it
    executes (needs_approval). The agent never approves its own high-acuity commit.

    Args:
        esi: the locked ESI acuity (1 most acute … 5 least).
        band: the locked disposition band (ED_NOW | URGENT | PRIMARY_CARE | SELF_CARE).
        action: the recommended next action to record.
    """
    ctx = wrapper.context
    ctx.commit_executed = True
    ctx.commit_record = {"esi": esi, "band": band, "action": action}
    ctx.log_tool("commit_disposition", ctx.commit_record, "disposition committed")
    return f"Committed disposition: ESI {esi} / {band}. Action: {action}"


COMMITTER_INSTRUCTIONS = """\
You are the COMMIT step of the triage supervisor. You are given the final, already-decided
disposition (ESI, band, action) — you do not change it. Call `commit_disposition` EXACTLY once
with those exact values to record it. For a high-acuity disposition the tool will pause for the
on-call clinician's approval; that is expected. After it returns, briefly confirm in one line.
"""


def build_committer_agent(model: str | None = None) -> Agent[TriageContext]:
    model = resolve_model(model)
    settings = ModelSettings(temperature=0) if supports_temperature(model) else ModelSettings()
    return Agent[TriageContext](
        name="Disposition Committer",
        instructions=COMMITTER_INSTRUCTIONS,
        model=model,
        model_settings=settings,
        tools=[commit_disposition],
    )
