# Проектные Agent Skills Hydro 2.0

**Статус:** `guide` · **Обновлено:** 2026-11-06.

Skills содержат рабочие процедуры для существующего проекта. Правила агентов
остаются в `AGENTS.md`, защищённые контракты — в `doc_ai/`, runtime — в коде.
Адаптация внешнего skill не разрешает новую подсистему, публикацию или действия
вне запроса пользователя.

## Каталог

| Skill | Сценарий | Исходный файл проекта |
|---|---|---|
| `hydro2-doc-sot` | Документация, источники истины, drift | [SKILL.md](../../.grok/skills/hydro2-doc-sot/SKILL.md) |
| `hydro2-command-flow` | Трассировка и изменение командного пути | [SKILL.md](../../.grok/skills/hydro2-command-flow/SKILL.md) |
| `hydro2-mqtt-security` | Namespace, подписи, ACL, telemetry | [SKILL.md](../../.grok/skills/hydro2-mqtt-security/SKILL.md) |
| `hydro2-ae3-automation` | Intents, leases, recovery, chemistry | [SKILL.md](../../.grok/skills/hydro2-ae3-automation/SKILL.md) |
| `hydro2-firmware-nodes` | ESP-IDF, NodeConfig, portal, E-Stop | [SKILL.md](../../.grok/skills/hydro2-firmware-nodes/SKILL.md) |
| `hydro2-frontend-dashboard` | Inertia/Vue, dashboard, роли, UI tests | [SKILL.md](../../.grok/skills/hydro2-frontend-dashboard/SKILL.md) |
| `two-tank-debug` | Read-only диагностика two-tank по текущей схеме | [SKILL.md](../../.claude/skills/two-tank-debug/SKILL.md) |
| `hydro2-laravel-backend` | Laravel API, Eloquent, миграции, read-model | [SKILL.md](../../.grok/skills/hydro2-laravel-backend/SKILL.md) |
| `hydro2-postgres-recovery` | PostgreSQL/TimescaleDB, dump, PITR, RPO/RTO | [SKILL.md](../../.grok/skills/hydro2-postgres-recovery/SKILL.md) |
| `hydro2-docker-dev` | Core и профили, конфигурация и readiness | [SKILL.md](../../.grok/skills/hydro2-docker-dev/SKILL.md) |
| `hydro2-systematic-debugging` | Доказательства, гипотеза, точечная проверка | [SKILL.md](../../.grok/skills/hydro2-systematic-debugging/SKILL.md) |
| `hydro2-skill-maintenance` | Создание/адаптация skills и сценарии оценки | [SKILL.md](../../.grok/skills/hydro2-skill-maintenance/SKILL.md) |

Выбирайте skill по сценарию задачи и читайте его ссылки по необходимости.
Не загружайте все skills и весь `doc_ai/` перед каждой правкой.

## Установка и проверка

Из корня репозитория, Python 3.10+ и GNU Make:

```bash
make skills-install
make skills-check
make skills-list
```

Установка локальная и идемпотентная: создаёт относительные symlinks внутри
репозитория для discovery в `.agents/skills/`, `.claude/skills/`, `.grok/skills/`.
Существующие чужие файлы не перезаписываются. Исходные тела хранятся один раз
по путям из манифеста; правки через alias изменяют тот же файл.
Codex использует `.agents/skills/`, Claude/Cursor могут читать `.claude/skills/`,
Grok — `.grok/skills/`; изменение каталога может потребовать обновления сессии
соответствующего клиента.

`skills-check` проверяет name/description и metadata, CHANGELOG, JSON-сценарии,
относительные ссылки, aliases, закреплённые источники и наличие лицензий.
В проекте используется ограниченный YAML-формат: однострочные строки, описания
в JSON-кавычках и `metadata` со строковыми значениями. Дополнительные type,
lifecycle, version находятся в metadata по [Agent Skills specification](https://agentskills.io/specification).

Проверка работает без сети, Docker, подключения MCP или запуска приложения.
Она **не исполняет eval prompts**, не измеряет качество срабатывания модели и
не подтверждает приёмку прошивки/стенда. Модельный benchmark запускается отдельно;
сохраняются фактические baseline/with-skill результаты, а не выдуманный pass rate.

## Первичные источники и переработка

Использованы следующие открытые skills. Ссылки закреплены на исследованных commit:

| Источник | Лицензия | Что изменено для Hydro |
|---|---|---|
| [Jeffallan: Laravel Specialist](https://github.com/Jeffallan/claude-skills/blob/078a25cc5bfd8011459be7b91d004e900c1d02d3/skills/laravel-specialist/SKILL.md) | MIT | Laravel 12/Inertia, Docker, владельцы команд/схемы; нет автоматического добавления Livewire/Horizon |
| [Jeffallan: PostgreSQL Pro](https://github.com/Jeffallan/claude-skills/blob/078a25cc5bfd8011459be7b91d004e900c1d02d3/skills/postgres-pro/SKILL.md) | MIT | Миграции вместо ручного DDL; диагностика и восстановление по правилам PostgreSQL 16/TimescaleDB |
| [Docker Local Development](https://github.com/thienanblog/awesome-ai-agent-skills/blob/ac929caec7e5313e5a53033db68673c47a84c42c/skills/docker-local-dev/SKILL.md) | Apache-2.0 | Существующий core и профили Hydro; без генерации нового стека и автоматического reset |
| [obra: Systematic Debugging](https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging/SKILL.md) | MIT | Трассировка intent/task/command/response, fail-closed, соразмерные проверки |
| [Anthropic: Skill Creator](https://github.com/anthropics/skills/blob/ca45fc496a3436251f191354091d557da31c15b5/skills/skill-creator/SKILL.md) | Apache-2.0 | Формат, краткие workflows, provenance и eval-сценарии без обязательной внешней оркестрации |

Commit, blob SHA, лицензии и описание переработки хранятся в
[`tools/skills/project-skills.json`](../../tools/skills/project-skills.json).
Тексты лицензий сохранены в [`tools/skills/licenses/`](../../tools/skills/licenses/).
Скачанные upstream-скрипты не устанавливаются и не выполняются этими адаптациями.

## Обновление

1. Найдите подходящий первичный источник и прочитайте его; проверьте лицензию и
   связанные notices. Зафиксируйте неизменяемый commit и blob SHA.
2. Обновите одну исходную версию skill и проверьте актуальные маршруты/таблицы/команды
   Hydro. Не наследуйте upstream auto-ship, ручной DDL и глобальные требования coverage.
3. Добавьте/исправьте реальные eval-сценарии, включая границы применения; обновите
   CHANGELOG и metadata.version. Сценарий должен учитывать уже данное разрешение
   пользователя: явный запрос нового task_type не равен его самовольному добавлению.
4. Обновите манифест и выполните `make skills-install`, `make skills-check`,
   `git diff --check`. Для модельной оценки отдельно запишите реальные результаты.

## Optional upstream и MCP

Legacy [`skills-lock.json`](../../skills-lock.json) относится к generic upstream,
а не к переработанным Hydro skills. Его computedHash нельзя заменять хешем
собственной адаптации. Наличие записи в lock-файле не означает установленный skill.

`make skills-install-external` отдельно загружает generic upstream через npx;
для проектных адаптаций это не требуется. `make skills-check-all` дополнительно
проверяет optional upstream и MCP prerequisites и может требовать Docker/uvx.
MCP управляется отдельными `make mcp-*`; обычная установка skills конфигурацию MCP
не меняет. Внешние инструкции применяются только с учётом `AGENTS.md` и задачи.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
