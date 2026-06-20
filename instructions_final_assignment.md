Multi-agent system project

Hide Assignment Information
Instructions
The brief

This is the capstone. Design and prototype a small but credible multi-agent system — with a real coordination mechanism, a real safety story, and evidence that you thought about how it could fail.

You are not expected to build a production system. You are expected to think like someone who eventually will.

Use case menu

Pick one from the menu, or pitch your own with our approval before Day 2 of the assignment.

Use case

Possible agent roles

Supply-chain stockout response

demand  ·  inventory  ·  supplier  ·  pricing  ·  human approver

Smart-grid coordination

household  ·  grid  ·  storage  ·  price signal  ·  regulator

Healthcare triage team

intake  ·  risk  ·  specialist  ·  scheduler  ·  human clinician

Portfolio committee

macro  ·  risk  ·  sector  ·  compliance  ·  portfolio manager

Disaster response

scout  ·  logistics  ·  medical  ·  routing  ·  command center

Content moderation

classifier  ·  policy  ·  escalation  ·  appeal  ·  auditor

Campus advising system

student advisor  ·  degree auditor  ·  scheduler  ·  escalation

Autonomous retail pop-up

demand  ·  labor  ·  inventory  ·  pricing  ·  customer experience

What your deliverable must cover

Why MAS — why a single agent is not enough for this use case.
Emergence — expected and unwanted emergent behavior, named explicitly.
Communication — message schema, routing, escalation, shared state.
Coordination — supervisor, market, contract net, consensus, blackboard, or hybrid. Defend the choice.
Incentives — cooperation, competition, local vs global objectives.
Interoperability — where A2A or MCP-style boundaries would matter.
Operations — observability, evaluation, rollback, human-in-the-loop controls.
MARL bridge — is multi-agent RL appropriate here, and why or why not?
What to submit

A working code project with a great README.md — even when much of the system is mocked, the repo is the artifact we grade against. See What we expect in your code and README.
System brief — use case, stakeholders, objective, failure stakes.
Agent roster — roles, responsibilities, tools, memory, permissions.
Architecture diagram — Mermaid or equivalent.
Communication contract — message schema, routing, escalation.
Coordination mechanism — with reasoning for the choice.
Incentive analysis.
Prototype or simulation — lightweight mocked run, scripted interaction, or minimal working demo.
Evaluation plan — metrics at agent, interaction, system, and human levels.
Safety / governance plan — HITL, audit logs, rollback, abuse and failure cases.
How you will be graded — 35 points

Category

Points

Use-case quality and stakeholder framing

4

Agent role design and boundaries

5

Communication protocol and architecture

5

Coordination and incentive design

6

Prototype, simulation, or worked scenario

5

Evaluation, observability, and safety

6

Presentation and clarity

4

Team policy

Assignments 1 and 2 are individual. Assignment 3 may be individual or in teams of 2–3. If you work in a team, include a short contribution statement — a few honest lines per teammate is enough.