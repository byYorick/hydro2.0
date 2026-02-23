# legacy_inventory.md
# AE2-Lite Legacy Inventory

**Дата:** 2026-02-22  
**Статус:** актуально для текущего cutover

Источник: `doc_ai/10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md` (Stage 0).

---

## 1. Endpoint inventory

### 1.1 Keep (canonical runtime)
- `POST /zones/{id}/start-cycle`
- `GET /zones/{id}/state`
- `GET /zones/{id}/control-mode`
- `POST /zones/{id}/control-mode`
- `POST /zones/{id}/manual-step`
- `GET /health/live`
- `GET /health/ready`

### 1.2 Delete (legacy runtime endpoints)
- `POST /scheduler/task`
- `GET /scheduler/task/{task_id}`
- `POST /scheduler/bootstrap`
- `POST /scheduler/bootstrap/heartbeat`
- `GET /scheduler/cutover/state`
- `GET /scheduler/integration/contracts`
- `GET /scheduler/observability/contracts`
- `POST /scheduler/internal/enqueue`
- `POST /zones/{id}/automation/manual-resume`
- `/test/hook*`
- `/zones/{id}/automation-state`
- `/zones/{id}/automation/control-mode`
- `/zones/{id}/automation/manual-step`

---

## 2. Module inventory

### 2.1 Keep
- `backend/services/automation-engine/application/api_start_cycle.py`
- `backend/services/automation-engine/application/api_scheduler_execution.py`
- `backend/services/automation-engine/application/api_scheduler_helpers.py`
- `backend/services/automation-engine/application/api_zone_state_payload.py`

### 2.2 Delete
- `backend/services/automation-engine/application/api_scheduler_bootstrap.py`
- `backend/services/automation-engine/application/api_scheduler_cutover.py`
- `backend/services/automation-engine/application/api_scheduler_integration.py`
- `backend/services/automation-engine/application/api_scheduler_observability.py`
- `backend/services/automation-engine/application/api_internal_enqueue.py`

---

## 3. Test inventory

### 3.1 Keep (новый smoke набор)
- `backend/services/automation-engine/test_actuator_registry.py`
- `backend/services/automation-engine/test_alerts_manager_phase2.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/services/automation-engine/test_scheduler_idempotency_replay.py`
- `backend/services/automation-engine/test_start_cycle_contract.py`
- `backend/services/automation-engine/test_api_start_cycle.py`

### 3.2 Delete
- legacy suite `backend/services/automation-engine/tests/*`

---

## 4. CI inventory

### 4.1 Keep
- `.github/workflows/ci.yml`:
  - job `automation-engine-smoke` (новые pytest smoke)
  - job `laravel-scheduler-smoke` (scheduler + zone automation feature smoke)

### 4.2 Delete
- любые CI ссылки на удаленные legacy pytest модули и `/scheduler/task` runtime flow.

---

## 5. E2E inventory

### 5.1 Keep (AE2-Lite compatible automation scenarios)
- `tests/e2e/scenarios/automation_engine/E61_fail_closed_corrections.yaml`
- `tests/e2e/scenarios/automation_engine/E64_effective_targets_only.yaml`
- `tests/e2e/scenarios/automation_engine/E65_phase_transition_api.yaml`
- `tests/e2e/scenarios/automation_engine/E74_node_zone_mismatch_guard.yaml`

### 5.2 Delete (legacy scenarios removed from active tree)
- `tests/e2e/scenarios/automation_engine/E60_climate_control_happy.yaml`
- `tests/e2e/scenarios/automation_engine/E62_controller_fault_isolation.yaml`
- `tests/e2e/scenarios/automation_engine/E63_backoff_on_errors.yaml`
- `tests/e2e/scenarios/automation_engine/E66_fail_closed_corrections.yaml`
- `tests/e2e/scenarios/automation_engine/E68_dose_ml_l_only_incomplete_profile.yaml`
- `tests/e2e/scenarios/automation_engine/E69_ec_batch_early_stop_tolerance.yaml`
- `tests/e2e/scenarios/automation_engine/E73_backoff_skip_signals.yaml`
- `tests/e2e/scenarios/automation_engine/E75_two_tank_fill_contract.yaml`

### 5.3 Delete (legacy docs/artifacts)
- `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME.md`
- `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME.mmd`
- `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME_V2.mmd`
- `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME.svg`
- `tests/e2e/scenarios/automation_engine/AUTOMATION_ENGINE_ALGORITHM_SCHEME.png`
- tracked generated reports:
  - `tests/e2e/reports/junit.xml`
  - `tests/e2e/reports/summary.json`
  - `tests/e2e/reports/timeline.json`
  - `tests/e2e/reports/smoke/summary.json`
