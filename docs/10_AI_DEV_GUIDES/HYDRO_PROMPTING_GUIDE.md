# Prompting Guide for hydro2.0

A practical checklist for crafting clear, project-aware prompts when working on hydro2.0 tasks.

## Pre-flight checks before you prompt
- Start with the repo-root `AGENTS.md`, then read any relevant `AGENTS.md` and conventions in the target folder; note framework versions and dependencies.
- Confirm the expected deliverable (file, screen, service, tests) and runtime environment (local/CI, available tokens).
- Gather constraints: forbidden files/dirs, no new deps/migrations, rollback expectations.
- List required checks: unit/integration/e2e, static analysis, simulators/emulators, and manual scenarios.
- Collect links to source files, DB/protocol schemas, and the ticket/discussion to avoid guesswork.

## Must-have details in your prompt
- **Goal and deliverable.** State what should exist after the task (files, API endpoint, screen, script) and how acceptance will be judged.
- **Subsystem and context.** Call out the area: backend (Laravel 12, PHP 8.2), Android (Kotlin, Clean Architecture), MQTT/transport, firmware, infrastructure. Link to relevant files/dirs, schemas, and existing conventions.
- **Constraints and no-gos.** Examples: do not touch migrations, avoid production configs, no new dependencies, stay within the specified module.
- **Tools and checks.** List commands/tests to run (phpunit, linters, simulators), available data/tokens, and what counts as a successful run.
- **Response format.** Request structure (Summary/Changes/Tests), JSON schemas, file lists, and application steps.
- **Risks and gaps.** Ask the assistant to flag missing inputs (URLs, secrets, DB schemas) instead of inventing values.

## Quick checklists by task type
- **Backend (Laravel 12, PHP 8.2):** specify controller/service/model, Laravel version and packages; request PHPUnit tests and Pint; spell out migrations/seeders, seed data, and rollback expectations.
- **Android (Kotlin, Clean Architecture):** pin the layer (data/domain/presentation), integrations (repository/use-case/viewmodel), DI via Koin, Retrofit, Reverb WebSocket; request unit/instrumentation tests for critical flows and threading/coroutines expectations.
- **MQTT/transport and integrations:** enumerate topics, payload, QoS, and idempotency; clarify serialization, retries/timeouts, and offline/redelivery handling.
- **Infrastructure and CI/CD:** name target environments, variables and secrets, Terraform/Ansible/Helm constraints, and commands to validate the pipeline; ask for rollback or mitigation steps.
- **Firmware and devices:** name the board/controller, memory/power limits, exchange protocol (UART/CAN/MQTT), flashing steps, and bench/emulator tests.
- **Documentation and specs:** define the target section, format (lists, tables, diagrams), language (RU/EN), and whether to mirror changes into `docs/`.

## Base prompt template
Adapt as needed:

```
You are GPT-5.1 Codex Max helping with hydro2.0.
Goal: <what must be built or fixed>.
Scope: <backend/android/mqtt/infra/firmware>.
Context: <key files and dirs, current implementation, dependencies, env/ports>.
Constraints: <what must not change, security/perf/UX requirements>.
Tests and checks: <which tests to add/run, any manual verifications>.
Response format: <Summary/Changes/Tests, file lists, schemas, or commands>.
Risks and gaps: <what needs clarification before execution>.
```

## Step-by-step flow
1) Briefly state the goal, scope, and prohibitions (no implementation yet).
2) Attach links to sources/schemas and list required checks/tests.
3) Ask the assistant for a plan with touched files and risks before code generation.
4) After the plan, close gaps (environment, tokens, ports, migrations, config).
5) Request a final self-check against acceptance criteria and output format.

## Micro-examples
- **Backend:** "Add a CSV export API for zones without DB schema changes; controller is ZoneExportController, service already exists; include PHPUnit tests for valid/empty data and list test commands."
- **Android:** "In the presentation layer, add an event history screen with pagination; data comes from `EventRepository`; Retrofit is configured; show how to update the Koin module and write a ViewModel unit test."

## How to prompt for bug finding and diagnosis
1. **State the symptom.** Describe what breaks: error message, wrong API response, lag, crash, MQTT duplicates, incorrect UI charts.
2. **Pin the environment.** Note branch/commit, configs/flags/env vars, tokens/data, device model/OS/firmware, and network (Wi‑Fi/cellular, VPN).
3. **Give repro steps.** A step-by-step scenario with inputs/topics/payloads, which services or emulators must run, and which ports are used.
4. **Attach observations.** Logs with timestamps, metrics/traces (CPU/RAM/latency), screenshots/video, SQL queries, payload dumps, expected vs actual behavior.
5. **Narrow the scope.** Name the subsystem (backend/Android/MQTT/infra/firmware), key files/modules/controllers/CI tasks, related tickets, or recent releases.
6. **Spell out constraints and risks.** What must not change (prod config, migrations, tokens), time/load limits, sensitive data, no new dependencies.
7. **Request the output format.** Ask for an investigation plan, hypotheses, checks, touched files, repro/log/test commands, and a self-check without unnecessary code generation.

### Quick bug-hunt template
```
We need to find and localize a bug.
Symptom: <error/wrong response/crash/lag>.
Environment: <branch, commit, config, device/OS/firmware, network>.
Repro: <step-by-step scenario, inputs/topics, what must be running>.
Observations: <logs with timestamps, metrics, screenshots/video, expected vs actual>.
Scope: <backend/android/mqtt/infra/firmware>, key files/modules <...>.
Constraints: <what must not change, limits, secrets>.
Requested output: investigation plan, hypotheses and checks, commands for repro/logs/tests, list of files, Summary/Changes/Tests format.
```

## Reminders
- Point to existing files and conventions instead of inventing new patterns.
- Ask for a step-by-step plan and list of touched files before code generation.
- Request a final self-check against acceptance criteria and output formats.
