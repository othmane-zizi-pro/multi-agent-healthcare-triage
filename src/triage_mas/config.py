"""Run configuration: model selection + the naive↔governed governance toggle.

Two jobs:

1. **Model selection** — `resolve_model()` reads `OPENAI_MODEL` (the source of truth; the
   constant below is only a fallback). `supports_temperature()` lets the code stay
   model-agnostic: GPT-5-series / o-series reasoning models reject the `temperature` param,
   gpt-4.x accept it ([SDK 43-46]: "settings are part of the contract").

2. **Governance toggle** — `GovernanceConfig` is the single switch behind the M6 emergence
   demo. In `governed` mode the safety controls from plan §3 are ON; in `naive` mode they are
   OFF, which lets the same case reproduce a *named* emergent failure (acuity inflation /
   under-triage collusion). "The architecture decides which version of emergence shows up"
   [MAS 15-16]. Crucially, even `naive` keeps the deterministic red-flag *screen* running —
   what `naive` removes is the system's *use* of it (the veto, the no-down-coding envelope,
   the approval gate), never the audit trail.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Fallback only — `OPENAI_MODEL` in .env is the source of truth. Matches .env.example.
DEFAULT_MODEL = "gpt-5.4-mini"


def resolve_model(model: str | None = None) -> str:
    return model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL


def supports_temperature(model: str) -> bool:
    """gpt-4.x accept `temperature`; gpt-5.x / o-series reasoning models reject it."""
    m = model.lower()
    return not m.startswith(("gpt-5", "o1", "o3", "o4"))


@dataclass(frozen=True)
class GovernanceConfig:
    """The controls plan §3 installs. `governed` = all ON; `naive` = safety machinery OFF."""

    mode: str = "governed"
    risk_veto_enabled: bool = True          # §3.4 independent risk veto can force escalation
    enforce_no_down_coding: bool = True     # §3.5 scheduler cannot down-code to fit capacity
    approval_gate_enabled: bool = True      # §3.7 HITL approval on high-acuity dispositions
    calibrated_risk_reward: bool = True     # §3.5 penalize over-escalation (kills alarm fatigue)
    bounded_clarification: bool = True      # §3.2 bound the intake↔specialist loop
    max_clarification_rounds: int = 2

    @classmethod
    def governed(cls) -> "GovernanceConfig":
        return cls(mode="governed")

    @classmethod
    def naive(cls) -> "GovernanceConfig":
        """Throughput-first incentives, no safety envelope — the failure configuration."""
        return cls(
            mode="naive",
            risk_veto_enabled=False,
            enforce_no_down_coding=False,
            approval_gate_enabled=False,
            calibrated_risk_reward=False,
            bounded_clarification=False,
        )

    @classmethod
    def from_mode(cls, mode: str) -> "GovernanceConfig":
        return cls.naive() if mode == "naive" else cls.governed()
