"""triage_mas — a small but credible multi-agent healthcare-triage system.

Capstone (Assignment 3). A team of specialized agents — intake · risk · specialist ·
scheduler — coordinated by a SUPERVISOR over a shared BLACKBOARD case file, with an
independent risk VETO and a human-clinician APPROVAL gate, turns a synthetic patient
presentation into a triage disposition (ESI acuity + disposition band + next action).

DECISION-SUPPORT PROTOTYPE — NOT A MEDICAL DEVICE. All patient data is synthetic.
Every design decision traces to a course concept in `llm-wiki-agentic-ai/` (cited inline as
[MAS …], [SDK …], [DRL …], [Intro …]).
"""

__version__ = "0.1.0"

#: Shown on every CLI run and written into every evidence packet. Non-negotiable framing.
SAFETY_BANNER = (
    "DECISION-SUPPORT PROTOTYPE — NOT A MEDICAL DEVICE. Synthetic data only. "
    "High-acuity dispositions require human-clinician approval before any action."
)
