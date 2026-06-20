"""CLI for the triage MAS.

    triage list                         # list the synthetic cases
    triage run CASE_ID                  # triage one case (governed mode)
    triage run CASE_ID --mode naive     # run with the unsafe incentive config (M6 demo)
    triage run CASE_ID --approve        # auto-approve a high-acuity commit (simulate clinician)
    triage demo [CASE_ID]               # naive-vs-governed emergence demo on one case

Reads OPENAI_API_KEY / OPENAI_MODEL from .env. Writes an evidence packet per run under
evidence/transcripts/ and the committed disposition under evidence/dispositions/.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from . import SAFETY_BANNER
from .config import GovernanceConfig, resolve_model
from .fixtures import all_case_ids, get_case
from .runtime import trace_url, write_evidence
from .supervisor import TriageResult, TriageSupervisor


def _fmt(result: TriageResult) -> str:
    d = result.disposition
    lines = [f"\nCase {result.case_id}  ·  mode={result.governance_mode}  ·  status={result.status}",
             f"[trace {result.trace_id}] {trace_url(result.trace_id)}"]
    if result.injection_flagged:
        lines.append("⚠  prompt-injection detected in narrative — quarantined; triage continued.")
    if result.status == "blocked_guardrail":
        lines.append(f"⛔ guardrail {result.guardrail_category}: {result.guardrail_reason}")
        return "\n".join(lines)
    if d is not None:
        flags = ", ".join(f.code for f in d.red_flags) or "none"
        lines += [
            f"  ESI {d.esi}  →  {d.band}",
            f"  Action: {d.action}",
            f"  Red flags: {flags}",
            f"  Requires approval: {d.requires_human_approval}   Committed: {d.committed}",
        ]
        if d.approval_reason:
            lines.append(f"  Approval reason: {d.approval_reason}")
        lines.append(f"  Summary: {d.summary}")
    if result.status == "awaiting_approval":
        lines.append("  ⏸  PAUSED for on-call-clinician approval (re-run with --approve to commit).")
    audits = [m.payload.event for m in result.case_file.transcript
              if m.msg_type == "AuditEvent"]
    lines.append(f"  Audit: {', '.join(audits)}")
    lines.append(f"  Message rounds: {result.rounds}")
    return "\n".join(lines)


def _packet(result: TriageResult, label: str) -> dict:
    d = result.disposition
    return {
        "label": label,
        "banner": SAFETY_BANNER,
        "case_id": result.case_id,
        "governance_mode": result.governance_mode,
        "model": resolve_model(),
        "status": result.status,
        "trace_id": result.trace_id,
        "trace_url": trace_url(result.trace_id),
        "injection_flagged": result.injection_flagged,
        "guardrail": {"category": result.guardrail_category, "reason": result.guardrail_reason}
        if result.status == "blocked_guardrail" else None,
        "disposition": d.model_dump() if d else None,
        "rounds": result.rounds,
        "tool_calls": result.tool_calls,
        "transcript": [m.model_dump() for m in result.case_file.transcript],
    }


async def _run(case_id: str, mode: str, approve: bool) -> None:
    sup = TriageSupervisor(case_id, governance=GovernanceConfig.from_mode(mode))
    result = await sup.run()
    print(_fmt(result))
    if result.status == "awaiting_approval" and approve:
        print("\n[on-call clinician: APPROVE]")
        result = await sup.resume(approve=True)
        print(_fmt(result))
    write_evidence(_packet(result, f"cli-run-{mode}"), "evidence/transcripts",
                   f"run-{case_id}-{mode}-{result.trace_id}")
    if result.disposition and result.disposition.committed:
        write_evidence({"banner": SAFETY_BANNER, "case_id": case_id,
                        "disposition": result.disposition.model_dump()},
                       "evidence/dispositions", f"{case_id}-{mode}")


async def _demo(case_id: str) -> None:
    print(f"\nEMERGENCE DEMO — same case ({case_id}) under naive vs governed incentives\n")
    for mode in ("naive", "governed"):
        sup = TriageSupervisor(case_id, governance=GovernanceConfig.from_mode(mode))
        result = await sup.run()
        if result.status == "awaiting_approval":
            result = await sup.resume(approve=True)
        print(_fmt(result))
        write_evidence(_packet(result, f"demo-{mode}"), "evidence/transcripts",
                       f"demo-{case_id}-{mode}-{result.trace_id}")
    print("\n(See README §emergence / report for the analysis of the difference.)")


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Multi-agent healthcare triage (synthetic, prototype)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("list", help="list synthetic cases")
    pr = sub.add_parser("run", help="triage one case")
    pr.add_argument("case_id")
    pr.add_argument("--mode", choices=["governed", "naive"], default="governed")
    pr.add_argument("--approve", action="store_true", help="auto-approve a high-acuity commit")
    pd = sub.add_parser("demo", help="naive-vs-governed emergence demo")
    pd.add_argument("case_id", nargs="?", default="undertriage_trap")
    args = p.parse_args()

    if args.cmd == "list":
        print(SAFETY_BANNER + "\n")
        for cid in all_case_ids():
            c = get_case(cid)
            edge = f"  [edge: {c.edge_kind}]" if c.edge else ""
            print(f"  {cid:18s} — {c.title}{edge}")
        return

    if not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "").startswith("REPLACE"):
        print("ERROR: OPENAI_API_KEY is not set. Add it to .env (see .env.example).",
              file=sys.stderr)
        sys.exit(2)

    print(SAFETY_BANNER)
    try:
        if args.cmd == "run":
            asyncio.run(_run(args.case_id, args.mode, args.approve))
        elif args.cmd == "demo":
            asyncio.run(_demo(args.case_id))
        else:
            p.print_help()
    except KeyboardInterrupt:
        print()
    except Exception as exc:  # noqa: BLE001 — friendly CLI boundary
        print(f"\nThe triage system hit an error and stopped: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
