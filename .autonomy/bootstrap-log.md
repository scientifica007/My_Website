# Bootstrap commissioning log

This file records infrastructure events before the valid experimental START boundary.

## 2026-08-26 — failed launch commissioning attempt

GitHub Actions run `32986670081` reached the following sequence:

1. Governance validation passed.
2. Groq provider probe passed.
3. `start.py` printed an in-run START timestamp.
4. The first real collector request failed before producing `collection.json` because Qwen JSON generation exhausted the completion budget while reasoning was enabled.
5. A workflow pathspec bug then prevented the ephemeral state/evidence changes from being committed.

Under `EXPERIMENT_PROTOCOL.md`, this is **not the valid experiment START** because the required pre-START technical dry run had not yet been implemented or passed, and no durable `ACTIVE` state was recorded. No product-development decision or product file change occurred. The repository therefore remains in `BOOTSTRAP`, with HDIC=0 and HIIC=0.

Corrective bootstrap actions:

- disable Qwen reasoning for compact JSON roles;
- reduce GPT-OSS reasoning to `low` for free-tier reliability;
- add a synthetic technical PDSA dry run that must pass before START;
- make `start.py` refuse START without that recorded dry-run pass;
- repair failure-state staging so `.autonomy` and cycle evidence are persisted independently when directories are absent.

The valid experimental START will be the first subsequent run that satisfies every condition in Section 3 of `EXPERIMENT_PROTOCOL.md` and durably records `armed=true`, `experiment_state=ACTIVE`, and `started_at` on `main`.
