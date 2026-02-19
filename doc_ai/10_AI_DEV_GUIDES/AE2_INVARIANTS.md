# AE2_INVARIANTS.md
# AE2 machine guard rails (CI/local)

**Версия:** v1.0  
**Дата:** 2026-02-19  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Артефакты
- `tools/testing/AE2_INVARIANTS.py`
- `tools/testing/check_ae2_invariants.sh`

## 2. Что проверяется
1. Команды к history-logger публикуются только через `backend/services/automation-engine/infrastructure/command_bus.py`.
2. В runtime-коде `automation-engine` нет прямого MQTT publish (`publish/publish_json`).
3. Для executor-модулей feature-flag env-access централизован в `application/executor_constants.py`.
4. В Python-сервисах отсутствует ручной SQL DDL (`CREATE/ALTER/DROP TABLE`).

## 3. Локальный запуск
```bash
./tools/testing/check_ae2_invariants.sh
```

## 4. CI-hook template (GitHub Actions)
```yaml
- name: AE2 invariants
  run: ./tools/testing/check_ae2_invariants.sh
```

## 5. Ограничения
1. Проверки ориентированы на быстрый machine-gate и не заменяют code review.
2. Для расширения invariants добавлять новые checks в `AE2_INVARIANTS.py` без ослабления существующих.
