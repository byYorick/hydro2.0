# Опциональные AI / Digital Twin компоненты

**Статус:** `guide` текущего состава репозитория.

- `digital-twin` и `node-sim-manager` находятся в профиле `sim`; обычный `make up` их не запускает.
- `feature-builder` — frozen skeleton в профиле `ml`, не непрерывный writer runtime-витрин.
- Наличие кода симулятора и таблиц ML не означает готовый ML pipeline или принятую на железе оптимизацию.
- Новые Python-сервисы и подсистемы создаются только по явному запросу.

Реализация и текущие интерфейсы:

- [digital-twin README](../../backend/services/digital-twin/README.md)
- [feature-builder README](../../backend/services/feature-builder/README.md)
- [Архитектура Python-сервисов](../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md)
- [Сводка реализации](../IMPLEMENTATION_STATUS.md)

[Главный индекс](../INDEX.md).
