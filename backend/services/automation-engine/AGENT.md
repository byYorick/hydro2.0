# AGENT.md — automation-engine (AE 1.0.0)

**Канон поведения:** `doc_ai/04_BACKEND_CORE/ae4.md`.
**Каталог runtime:** `ae4/`.
**Версия сервиса:** `1.0.0`.

Пакета `ae3lite` нет. Диспетчера Laravel нет. Команды к узлам — только через history-logger.
Один воркер, claim зон без явного `automation_runtime=ae3`. Тик сам будит полив/химию/свет и один climate-tick на теплицу.

Тесты AE: `make test-ae PYTEST_ARGS="-q tests/unit/ae4"`.
