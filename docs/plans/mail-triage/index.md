---
intent: INT-001
feature: mail-triage
spec: docs/specs/mail-triage.md
---

# mail-triage

Overview of the plan: what is built, in which order and what can run in parallel. A builder reads only its own unit file (linked in the table) plus this index when it needs the dependencies.

## Units

| Unit | Name | Layer | Depends on | Parallel | Wave |
|---|---|---|---|---|---|
| [U-mail-triage-01](U-mail-triage-01.md) | Component skeleton and configuration | backend (scaffold from `/sdlc:component agent mail-triage`, then adapted) | — | no | 1 |
| [U-mail-triage-02](U-mail-triage-02.md) | Alert state machine | backend (pure core) | U-01 | yes | 1 |
| [U-mail-triage-03](U-mail-triage-03.md) | Time policy (quiet hours, snooze, overview time) | backend (pure core) | U-01 | yes | 1 |
| [U-mail-triage-04](U-mail-triage-04.md) | Judgement schema and category policy | backend (pure core) | U-01 | yes | 1 |
| [U-mail-triage-05](U-mail-triage-05.md) | Gmail read and label operations | backend (adapter) | U-01 | yes | 1 |
| [U-mail-triage-06](U-mail-triage-06.md) | Gmail send reply | backend (adapter) | U-01 | yes | 1 |
| [U-mail-triage-07](U-mail-triage-07.md) | Token store and one-time consent | backend (adapter and command-line tool) | U-01, U-09 | no | 1 |
| [U-mail-triage-08](U-mail-triage-08.md) | Model adapter (Anthropic) | backend (adapter) | U-01, U-04 | yes | 1 |
| [U-mail-triage-09](U-mail-triage-09.md) | Persistence | backend (adapter) | U-01 | yes | 1 |
| [U-mail-triage-10](U-mail-triage-10.md) | Triage pipeline | backend (use case) | U-02, U-03, U-04, U-05, U-08, U-09 | no | 1 |
| [U-mail-triage-11](U-mail-triage-11.md) | Telegram intake (long polling) | backend (adapter) | U-01 | yes | 1 |
| [U-mail-triage-12](U-mail-triage-12.md) | Alert text | backend (pure core) | U-04 | yes | 1 |
| [U-mail-triage-13](U-mail-triage-13.md) | Alert delivery | backend (use case) | U-02, U-03, U-09, U-11, U-12 | no | 1 |
| [U-mail-triage-14](U-mail-triage-14.md) | Reply flow with confirmation | backend (use case) | U-02, U-06, U-09, U-11 | no | 1 |
| [U-mail-triage-15](U-mail-triage-15.md) | Snooze and close commands | backend (use case) | U-02, U-03, U-09, U-11 | yes | 1 |
| [U-mail-triage-16](U-mail-triage-16.md) | Daily overview | backend (use case) | U-03, U-09, U-11, U-12 | yes | 1 |
| [U-mail-triage-17](U-mail-triage-17.md) | Log and error-report redaction | backend (cross-cutting) | U-01 | yes | 1 |
| [U-mail-triage-18](U-mail-triage-18.md) | Container and deployment | infra | U-01 | yes | 1 |
| [U-mail-triage-19](U-mail-triage-19.md) | End-to-end check (manual, with a test account) | e2e | U-10, U-13, U-14, U-15, U-16, U-17, U-18 | no | 1 |

## Build order

1. Wave 1 — in parallel: U-mail-triage-02, U-mail-triage-03, U-mail-triage-04, U-mail-triage-05, U-mail-triage-06, U-mail-triage-08, U-mail-triage-09, U-mail-triage-11, U-mail-triage-12, U-mail-triage-15, U-mail-triage-16, U-mail-triage-17, U-mail-triage-18; one at a time: U-mail-triage-01, U-mail-triage-07, U-mail-triage-10, U-mail-triage-13, U-mail-triage-14, U-mail-triage-19

All code lives in the new component `agents/mail-triage` (ADR-0019), Python, no UI. Each unit gets its own git worktree and branch (`feat/mail-triage-<nn>-<slug>`), is built test-first (a failing test is shown before any implementation) and is merged by a PR that Marco approves. Test names follow `test_given_x_when_y_then_z`. Ids AC-n refer to the spec.

Common guardrails for every unit: `guardrail-python`, `guardrail-pytest`. Others are listed per unit.

## Order and parallelism

```text
U-01 skeleton ──┬─ U-02 alert state machine ─┐
                ├─ U-03 time policy ──────────┤
                ├─ U-04 judgement schema ─────┤
                ├─ U-05 Gmail read/label ─────┤
                ├─ U-06 Gmail send ───────────┼─► U-10 pipeline ─► U-13 alert delivery ─┐
                ├─ U-07 token store ──────────┤                   U-14 reply flow ──────┤
                ├─ U-08 model adapter ────────┤                   U-15 snooze/close ─────┼─► U-19 end-to-end check
                ├─ U-09 persistence ──────────┤                   U-16 daily overview ───┤
                ├─ U-11 telegram intake ──────┘                   U-12 alert text ───────┤
                ├─ U-17 log redaction ─────────────────────────────────────────────────────┤
                └─ U-18 container & deploy ───────────────────────────────────────────────┘
```

Parallel groups: (U-02, U-03, U-04, U-05, U-06, U-07, U-08, U-09, U-11, U-17, U-18) after U-01; (U-12, U-13, U-14, U-15, U-16) after their dependencies. U-10 needs the group above it. U-19 is last.

## Units with a suffixed id (not split into files)

## Coverage of spec criteria

| AC | Unit(s) |
|---|---|
| AC-1 | U-04, U-05, U-10, U-19 |
| AC-2 | U-05, U-10, U-19 |
| AC-3 | U-10, U-12, U-13, U-19 |
| AC-4 | U-10, U-19 |
| AC-5 | U-02, U-13 |
| AC-6, AC-7 | U-02, U-06, U-14, U-19 |
| AC-8 | U-02, U-14 |
| AC-9 | U-02, U-03, U-15, U-19 |
| AC-10 | U-02, U-15 |
| AC-11, AC-15 | U-11 |
| AC-12 | U-05, U-08, U-09, U-10, U-13 |
| AC-13 | U-04 |
| AC-14, AC-24 | U-01, U-07, U-08, U-11, U-17, U-19 |
| AC-16 | U-06, U-12 |
| AC-17 | U-14 |
| AC-18 | U-04, U-08 |
| AC-19 | U-08, U-19 |
| AC-20 | U-09, U-14 |
| AC-21 | U-04, U-12 |
| AC-22 | U-09, U-13, U-14 |
| AC-23 | U-05, U-08, U-12 |
| AC-25 | U-07 |
| AC-26 | U-08, U-10, U-13 |
| AC-27 | U-10 |
| AC-28 | U-05, U-06 |
| AC-29 | U-05, U-06, U-14 |
| AC-30 | U-18 |
| AC-31 | U-03, U-16 |
| AC-32 | U-03, U-10, U-13, U-15 |

Every AC in the spec appears at least once. Self-check against the "too big" signals: the largest unit (U-08) has 8 criteria and U-14 has 8, both within 3–10; no unit lists more than about 4 files.

## Notes and risks for the builders

- U-07 depends on the `oauth_token` table from U-09; build U-09 first or together.
- The Gmail and Telegram adapters are tested against fakes and recorded responses; real accounts are used only in U-19 and never in CI.
- Marco provides the Anthropic API key, the Telegram bot token and a Google OAuth client before U-19, not before.
- The threat model is delivered by tests (security criteria); `red-team` and `code-reviewer` check them in phase 6.
