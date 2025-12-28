# LEGACY / NOT USED

**⚠️ ВНИМАНИЕ: Этот сервис больше не используется!**

Device Registry — реестр устройств, хранение и выдача NodeConfig.

**Статус:** **LEGACY / NOT USED** — функционал полностью реализован в Laravel.

**Текущая реализация:**
Функционал device-registry полностью реализован в Laravel:
- Модели `DeviceNode` хранят информацию о нодах
- Конфигурация нод хранится в БД через Laravel
- NodeConfig может быть сгенерирован из данных БД
- **NodeRegistryService** (`app/Services/NodeRegistryService.php`) — регистрация нод
- API `/api/nodes/register` — регистрация новых нод
- Поля `validated`, `first_seen_at`, `hardware_revision` в таблице `nodes`

**Реализация:**
- `backend/laravel/app/Services/NodeRegistryService.php` — сервис регистрации
- `backend/laravel/app/Http/Controllers/NodeController.php::register()` — API endpoint
- Миграция: `2025_01_27_000002_add_node_registry_fields.php`

**Документация:**
- Структура проекта: `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- Backend архитектура: `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`

**Примечание:**
Эта папка оставлена как placeholder для исторических целей. Функционал Device Registry полностью реализован в Laravel.

