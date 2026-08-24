Инфраструктура и деплой (docker, k8s, terraform, ansible).

**Not used (stubs):** `infra/k8s`, `ansible`, `terraform`, `infra/docker/influxdb` — не runtime. Deploy SoT = docker compose (`backend/docker-compose.prod.yml`). InfluxDB — placeholder; канон хранения телеметрии = PostgreSQL + TimescaleDB. Не поднимать k8s «по-настоящему» по этим манифестам.

Канонические описания стека и потоков данных: `../doc_ai/INDEX.md`, `../doc_ai/ARCHITECTURE_FLOWS.md`, `../doc_ai/04_BACKEND_CORE/FULL_STACK_DEPLOY_DOCKER.md`.

## Документация в этом каталоге

- `DEPLOYMENT.md` — развёртывание без Docker (базовые шаги)
- `UPDATE_SERVER.md` — обновление проекта на сервере
- `docker/` — образы и вспомогательные конфиги (Grafana, MQTT, Influx и т.д.)
- `k8s/` — Kubernetes манифесты
- `terraform/` — Terraform
- `ansible/` — Ansible playbooks

## Связанные документы в репозитории

- `../backend/README.md` — dev-сервисы, порты, мониторинг
- `../QUICK_START.md` — быстрый старт разработчика
