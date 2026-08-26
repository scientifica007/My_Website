# AGENTS.md — Autonomous Product Development Contract

## Mission

Build the product described in `PRODUCT_GOAL.md` until the evidence satisfies `DEFINITION_OF_DONE.md`.

The product is an Arabic RTL web application for a vocational training and education inspector in Algeria. The repository is public; use synthetic data only.

## Operating method

Every product change MUST occur through the PDSA process defined in `PDSA_PROTOCOL.md`:

`Collect → Classify → SMART Objective → Plan → Review → Revise → Approve → Freeze → Do → Verify → Study → Act`

Do not invent a fixed roadmap. At the beginning of each cycle, choose the most relevant achievable next objective from the current evidence and the remaining gap to the final product goal.

## Frozen-plan rule

Before approval you may criticize and revise a plan.

After approval and SHA-256 freeze:

- do not change the cycle objective;
- do not change the frozen plan;
- do not silently add repairs or tasks that were not permitted by the frozen plan;
- record unexpected failures, deviations, and better ideas for Study/Act and the next cycle.

A failed Do is valid experimental evidence. Hiding or rewriting failure is not allowed.

## Protected experiment infrastructure

Do not modify the protected paths defined in `GOVERNANCE.md`.

Never weaken tests, governance, the product goal, or Definition of Done merely to declare success.

## Decision autonomy

After experiment START, do not ask a human to choose technology, architecture, features, priorities, repairs, or the next objective. Gather evidence, compare alternatives, decide, document the reasoning outcome, and continue.

If execution is impossible because external infrastructure is unavailable, record `INFRASTRUCTURE_BLOCKED`. Do not convert a product-development question into a human request.

## Product constraints

- Arabic is the primary UI language.
- RTL is a native design requirement.
- The legal/regulatory corpus is evidence; generated interpretation is not itself an official legal source.
- Legal explanations should preserve provenance and distinguish retrieved source material from interpretation.
- Never commit real inspection data, personal data, credentials, tokens, or unpublished administrative material.
- Use synthetic fixtures and examples.

## Quality

Prefer objectively verifiable results. Use tests/build/type checks/lint/schema checks or other deterministic evidence appropriate to the stack you choose.

Maintain enough product documentation and project memory for later autonomous cycles to understand the architecture without rereading the entire history.

## Completion

Do not declare the project complete directly. When evidence suggests all Definition of Done requirements are satisfied, request the state transition to `FINAL_AUDIT_PENDING`. Only an independent final-audit role may transition the project to `FINAL_CANDIDATE`.
