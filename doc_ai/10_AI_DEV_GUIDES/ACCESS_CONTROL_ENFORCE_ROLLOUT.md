# ACCESS_CONTROL_ENFORCE_ROLLOUT.md
# Безопасный rollout режима `ACCESS_CONTROL_MODE=enforce`

**Дата:** 2026-02-06  
**Статус:** Руководство для staging/prod rollout

---

## 1. Цель

Перейти от исторической модели доступа (`legacy`) к явной изоляции (`enforce`) через:

- `user_greenhouses`
- `user_zones`

с минимальным риском регресса.

---

## 2. Предусловия

1. Применены миграции:
   - `2026_02_06_120000_create_user_greenhouses_table.php`
   - `2026_02_06_120100_create_user_zones_table.php`
2. В `config/logging.php` доступен канал `access_shadow`.
3. Для всех активных пользователей есть стартовые привязки к зонам/теплицам.

---

## 3. Пошаговый rollout

### Шаг A: Shadow в staging

1. Установить:
   - `ACCESS_CONTROL_MODE=shadow`
2. Очистить конфиг-кеш:
   - `php artisan config:clear`
   - `php artisan config:cache`
3. Мониторить `storage/logs/access-shadow-*.log`.

Критерий перехода:

- нет неожиданных `shadow mismatch` для основных пользовательских сценариев.

### Шаг B: Shadow в production

1. Перевести production в `shadow`.
2. Наблюдать минимум 24-72 часа:
   - API доступ к зонам/теплицам,
   - dashboard/sync/config endpoints,
   - operator сценарии управления.

Критерий перехода:

- все расхождения объяснены и исправлены данными привязок.

### Шаг C: Enforce в staging

1. Установить:
   - `ACCESS_CONTROL_MODE=enforce`
2. Повторить smoke/regression.

Критерий перехода:

- отсутствуют ложные `403` в целевых сценариях.

### Шаг D: Enforce в production (канареечно)

1. Включить `enforce` на части инстансов (если инфраструктура поддерживает).
2. Проверить метрики/логи ошибок авторизации.
3. Раскатить на весь production.

---

## 4. Rollback

Немедленный откат:

1. Вернуть `ACCESS_CONTROL_MODE=legacy`.
2. Очистить/пересобрать config cache.
3. Проверить восстановление API-доступа.

---

## 5. Операционный чек-лист

1. Есть резервная выгрузка таблиц пользователей и привязок.
2. Миграции применены во всех окружениях одинаково.
3. Smoke-тесты API пройдены после каждого шага.
4. Подготовлен контакт ответственного за on-call на окно раскатки.

