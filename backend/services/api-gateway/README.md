API Gateway — роль выполняется Laravel.

**Статус:** Этот сервис не реализован как отдельный микросервис.

**Текущая реализация:**
Laravel (`backend/laravel/`) выполняет роль API Gateway:
- REST API для фронтенда и мобильного приложения (`/api/*`)
- WebSocket/Realtime обновления (Laravel Reverb)
- Управление конфигурацией, авторизация, пользователи

**Документация:**
- Архитектура backend: `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- API спецификация: `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- REST API reference: `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`

**Примечание:**
Эта папка оставлена как placeholder. Если в будущем потребуется отдельный микросервис API Gateway, его можно реализовать здесь согласно документации в `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`.


