# Исправление ошибки сборки Laravel

## Проблема
Ошибка сборки Laravel: `[vite:vue] [@vue/compiler-sfc] different imports aliased to same local name` для ZoneEvent.

## Исправление
Исправлен импорт ZoneEvent в `backend/laravel/resources/js/Pages/Zones/Show.vue`:
- Убран ZoneEvent из общего импорта из `@/types`
- Добавлен отдельный импорт: `import type { ZoneEvent } from '@/types/ZoneEvent'`

## Файлы
- `backend/laravel/resources/js/Pages/Zones/Show.vue` - исправлен импорт ZoneEvent

## Статус
- ✅ Исправление применено в коде
- ⚠️ Требуется пересборка Laravel образа (проблема с кешем Docker)

## Команда для пересборки
```bash
cd backend
docker-compose -f docker-compose.dev.yml build --no-cache laravel
docker-compose -f docker-compose.dev.yml up -d laravel
```

## Примечание
Если проблема сохраняется, возможно, нужно:
1. Очистить кеш Docker: `docker builder prune`
2. Удалить старый образ: `docker rmi backend-laravel:latest`
3. Пересобрать заново

