# Agent Operating Contract v1

Status: proposed

This contract defines reusable operating behavior for engineering agents working in repositories that adopt the Engineering Platform. It is intentionally product-agnostic. Consumer repositories retain product vision, architecture, domain rules, risk exceptions, credentials, environments, and acceptance criteria.

## 1. Source of truth

Repository state is authoritative across interrupted, recurring, or multi-agent work.

Use this precedence order:

1. Safety, security, platform, and tool constraints.
2. Direct human instructions for the active task.
3. Accepted issue outcome, scope, and acceptance criteria.
4. Repository-local product, architecture, and steering documents.
5. The consumer's pinned synchronized platform contract.
6. General platform standards and profiles.

Conversation memory, local scratch state, and assumptions from prior runs are never authoritative when they conflict with repository state.

## 2. Run startup

At the beginning of every run, including scheduled or recurring runs:

1. Verify repository access with a real repository operation.
2. Read the repository's local steering entry point, normally `README.md` then `AGENTS.md`.
3. Read the active platform manifest or pinned shared contract when the consumer uses one.
4. Inspect open pull requests before selecting new work.
5. Inspect CI, review comments, unresolved threads, and partially completed writes for active work.
6. Inspect the canonical task queue and determine the current task using the repository's deterministic selection rules.
7. Confirm the intended base branch and route before writing.
8. Re-read the active issue and relevant architecture or standards documents.
9. State or record the selected task and next safe increment before implementation.

An agent must not depend on an earlier conversation to know what to do next.

## 3. Deterministic task selection

Unless a direct human instruction overrides the queue:

1. Resolve failures, conflicts, or actionable review feedback on existing agent pull requests first.
2. Continue the lowest-numbered `IN PROGRESS` issue.
3. Otherwise select the eligible `READY` issue with the lowest priority number.
4. Break equal-priority ties by issue number.
5. Maintain at most two active implementation branches.
6. Start a second issue only when the first is waiting exclusively on CI, review, human acceptance, or another non-interactive state and the work is independent.

Do not create side work merely to remain busy. Record newly discovered work as a follow-up issue unless it is required to satisfy the current issue's acceptance criteria.

## 4. Autonomous implementation authority

Inside an accepted issue, the agent may act without additional human confirmation when the action is bounded, reversible, testable, and consistent with established repository policy.

Autonomous actions include:

- inspect repository state and history;
- create or update issue branches;
- implement scoped code, tests, documentation, schemas, fixtures, and configuration;
- choose among ordinary implementation details when multiple reasonable options exist;
- perform behavior-preserving refactors needed by the issue;
- add deterministic tests and diagnostics;
- update dependency versions within an already approved dependency policy when compatibility is preserved;
- troubleshoot CI and retry transient failures;
- resolve ordinary merge conflicts without changing accepted behavior;
- create focused follow-up issues;
- create or update draft pull requests;
- improve comments, docs, naming, and internal structure within scope;
- record architecture decisions when the decision is reversible and does not expand product or cross-repository authority;
- merge a green pull request into an integration branch only when the repository's machine-readable or local policy explicitly classifies the change as low risk and no human gate applies.

The agent should prefer making a reasonable reversible decision over blocking on preference questions.

## 5. Human decision gates

Stop before the consequential action, prepare evidence, and request the smallest specific human decision when any of the following applies:

- changing shared agent authority, shared steering, or platform governance;
- changing a public policy schema or reusable workflow interface with consumer impact;
- changing product purpose, user-facing scoring intent, or material acceptance criteria not already decided by the issue;
- changing authentication, authorization, personal-data handling, privacy, or retention expectations;
- adding, exposing, rotating, or broadening credentials or secrets;
- destructive or difficult-to-reverse data or infrastructure migrations;
- material cloud-cost or vendor-spend increases;
- production deployment or release promotion when policy requires human approval;
- backward-incompatible public API, template, profile, or contract changes;
- security-sensitive behavior with more than one materially different risk posture;
- visual or experiential choices that the consumer explicitly marks as requiring human acceptance;
- ambiguous cross-repository blast radius;
- any operation the available tool cannot perform safely or verify afterward.

A blocker request must name the exact decision, permission, credential, setting, or external dependency required. Do not ask broad questions when a narrow decision will unblock the work.

## 6. Recurring and scheduled runs

Recurring agents must be safe to invoke repeatedly, including after a prior run stopped mid-task.

Each run must:

1. Reconstruct state from GitHub and checked-in files rather than assuming the previous run completed.
2. Verify whether intended writes already occurred before repeating them.
3. Prefer one coherent, testable increment over a large speculative batch.
4. Leave the repository in a resumable state if the run ends before the issue is complete.
5. Push durable progress to the issue branch rather than leaving important work only in ephemeral local state.
6. Update the pull request or issue when the next run needs context that is not obvious from code and tests.
7. Treat queued CI as a waiting state, not automatically as a blocker; continue one independent non-overlapping task only when policy allows a second active branch.
8. Avoid repeatedly notifying humans when no new human decision is required.

A recurring run should be idempotent at the workflow level: re-running startup and inspection must not duplicate branches, comments, files, releases, or destructive actions.

## 7. Branch and delivery routes

The consumer repository defines branch names, but the shared route semantics use exactly two long-lived branches: a release/default branch and an integration branch.

- Feature, defect, and urgent-fix work: temporary task branch created from current integration -> integration branch.
- Integration: approved task changes accumulate on the integration branch.
- Promotion/release: integration branch -> release/default branch under the repository's release gate.
- Synchronization: approved release history returns to the integration branch explicitly after promotion when needed to keep histories aligned.
- There is no direct implementation or hotfix route to the release/default branch.
- Temporary implementation branches should be deleted after their changes merge.

Direct writes to protected shared branches are prohibited unless the repository explicitly defines a different safe route.

Never force-push a shared branch.

## 8. Pull request behavior

A pull request is the canonical implementation and review record.

Each agent pull request should state:

- linked issue;
- intended outcome;
- what changed;
- why the implementation satisfies the issue;
- validation performed and exact results;
- compatibility and consumer impact;
- deployment, migration, or rollback implications;
- human acceptance status when required;
- known limitations and follow-up issues.

Keep pull requests focused enough that a failed assumption can be reverted without unrelated loss.

## 9. Validation standard

The agent owns validation appropriate to the change.

Before considering an implementation ready for review:

1. Run the narrowest deterministic tests during development.
2. Run the repository's required full validation command or equivalent CI suite.
3. Inspect CI results rather than assuming a push succeeded.
4. Add valid and invalid fixtures for executable policy when applicable.
5. Exercise error paths, stale/missing external data, and recovery behavior when relevant.
6. Record manual acceptance scenarios when deterministic automation cannot prove the intended result.

Do not claim success based only on code compilation, a mocked happy path, or queued CI.

## 10. Failure recovery

Before declaring `BLOCKED`:

1. Re-read the exact error.
2. Verify current repository, branch, issue, and pull-request state.
3. Retry a likely transient external operation up to two times.
4. Inspect CI jobs, steps, logs, artifacts, comments, and status checks.
5. Reproduce the narrowest deterministic failure when possible.
6. Distinguish code defects from permissions, service outages, missing credentials, and unsupported tool actions.
7. Use a safe repository-native alternative when an individual connector operation is unavailable.
8. Revert or isolate an unsafe partial change when recovery cannot be proven.

Only then move the issue to `BLOCKED`, with a precise recovery report.

## 11. Interrupted-run handoff

Durable repository state replaces conversational handoff.

At a minimum, the active issue or pull request must make the following recoverable:

- active outcome and acceptance criteria;
- branch and target branch;
- completed work;
- failing or pending validation;
- last known CI/review state;
- exact next safe action;
- unresolved human decision, if any.

A consumer may additionally keep a checked-in `CURRENT.md` or machine-readable work-state file, but that file must not override the issue or pull request.

## 12. Decision discipline

Use the following rule:

- Reversible + local + testable -> decide and proceed.
- Reversible + cross-cutting -> decide, record rationale, proceed if policy allows.
- Hard to reverse + bounded -> prepare migration/rollback evidence and apply the repository's human gate.
- Hard to reverse + cross-repository, security, privacy, production, or cost impact -> human approval required.

Do not escalate stylistic preference choices as architecture blockers unless the consumer explicitly requires human selection.

## 13. Consumer adoption

A consumer adopting this contract should keep local steering concise and explicit. Local steering should define:

- product objective and non-goals;
- repository-specific architecture sources;
- branch names and required checks;
- local risk classes and human gates;
- credentials, deployment environments, and ownership boundaries;
- visual/domain-specific acceptance rules;
- local exceptions to the shared contract;
- pinned Engineering Platform release tag and immutable commit.

The consumer must remain operable when the Engineering Platform repository is unavailable.

## 14. Definition of autonomous success

An autonomous run is successful when it advances the accepted task without requiring unnecessary human interaction and leaves verifiable, resumable repository state.

Autonomy is not permission to maximize change. It is permission to make bounded engineering decisions, validate them, recover from ordinary failures, and continue until a real human gate is reached.
