# Анализ ошибок E2E тестов и план исправлений

**Дата анализа:** 2025-12-15  
**Статус:** Expert Mode Analysis

## 📊 Статистика выполнения

- **Всего сценариев:** 28
- **Провалено:** ~20+ сценариев
- **Основные категории ошибок:** 5

---

## 🔍 Категории ошибок

### 1. **КРИТИЧЕСКАЯ: Пустые значения zone_id/node_id в SQL запросах**

**Симптомы:**
```
ERROR: invalid input syntax for type bigint: ""
CONTEXT: unnamed portal parameter $1 = ''
```

**Причина:**
- Функция `_resolve_variables()` в `e2e_runner.py` возвращает пустую строку `""` если переменная не найдена (строка 571)
- Когда API не возвращает данные или переменная не установлена, `zone_id` становится `""`
- Пустая строка передается в SQL запрос как параметр для `bigint`, что вызывает ошибку

**Затронутые сценарии:**
- `core/E01_bootstrap` - `telemetry_in_db` assertion
- `infrastructure/E42_bindings_role_resolution` - `zone_exists` assertion
- `grow_cycle/E50_create_cycle_planned` - `cycle_status_planned` assertion
- `grow_cycle/E51_start_cycle_running` - `zone_status_updated` assertion
- `grow_cycle/E52_stage_progress_timeline` - `recipe_instance_active` assertion
- `grow_cycle/E53_manual_advance_stage` - `zone_exists` assertion
- `grow_cycle/E54_pause_resume_harvest` - `zone_exists` assertion
- `automation_engine/E60_climate_control_happy` - `telemetry_saved` assertion
- И другие...

**Корневая причина:**
1. Отсутствие валидации переменных перед использованием в SQL
2. Нет механизма проверки наличия данных в API ответах
3. Нет fallback механизмов для получения zone_id/node_id

---

### 2. **Проблемы с WebSocket авторизацией (403 Forbidden)**

**Симптомы:**
```
ERROR: Failed to authorize channel 'private-hydro.zones.': Unauthorized. (status 403)
```

**Причина:**
- WebSocket подписка требует авторизации через `/broadcasting/auth`
- Токен может быть невалидным или истекшим
- Формат канала может быть неправильным (пустой zone_id в имени канала)

**Затронутые сценарии:**
- `core/E02_auth_ws_api` - `subscribe_to_zone_channel`
- `automation_engine/E60_climate_control_happy` - `subscribe_zone_channel`

**Детали:**
- Канал формируется как `private-hydro.zones.${zone_id}`, но если `zone_id` пустой, получается `private-hydro.zones.`
- Laravel Reverb отклоняет такой канал

---

### 3. **Ошибки API endpoints (500 Internal Server Error)**

**Симптомы:**
```
Server error '500 Internal Server Error' for url 'http://localhost:8081/api/zones/attach-recipe'
Server error '500 Internal Server Error' for url 'http://localhost:8081/api/zones/bindings'
```

**Причина:**
- Backend endpoints не реализованы или имеют баги
- Отсутствующие таблицы в БД (например, `zone_bindings`)
- Ошибки в бизнес-логике Laravel

**Затронутые endpoints:**
- `/api/zones/attach-recipe` - прикрепление рецепта к зоне
- `/api/zones/detach-recipe` - открепление рецепта
- `/api/zones/bindings` - работа с bindings
- `/api/zones/{id}/snapshot` - получение snapshot
- `/api/zones/start` - запуск цикла
- `/api/zones/pause` - пауза цикла

**Затронутые сценарии:**
- `grow_cycle/E50_create_cycle_planned`
- `grow_cycle/E51_start_cycle_running`
- `grow_cycle/E54_pause_resume_harvest`
- `infrastructure/E42_bindings_role_resolution`

---

### 4. **Отсутствующие таблицы в БД**

**Симптомы:**
```
ERROR: relation "zone_bindings" does not exist
```

**Причина:**
- Миграции не выполнены или таблица не создана
- Таблица была удалена или переименована

**Затронутые сценарии:**
- `infrastructure/E42_bindings_role_resolution` - проверка таблицы `zone_bindings`

---

### 5. **Rate limiting на API токенах (429 Too Many Requests)**

**Симптомы:**
```
HTTP Request: POST http://localhost:8081/api/e2e/auth/token "HTTP/1.1 429 Too Many Requests"
```

**Причина:**
- Слишком частые запросы токенов
- Rate limiting в Laravel настроен слишком строго для E2E тестов

**Решение:**
- Runner уже использует fallback через Artisan команду
- Но можно увеличить лимиты для E2E окружения

---

## 🛠️ План исправлений

### Приоритет 1: КРИТИЧЕСКИЙ - Валидация переменных перед SQL запросами

**Файл:** `tests/e2e/runner/e2e_runner.py`

**Изменения:**

1. **Улучшить `_resolve_variables()` для валидации:**
```python
def _resolve_variables(self, value: Any) -> Any:
    # ... существующий код ...
    # Вместо возврата "" при отсутствии переменной, выбрасывать исключение
    if resolved is None:
        # Для критических переменных (zone_id, node_id) выбрасывать исключение
        if var_expr in ['zone_id', 'node_id']:
            raise ValueError(f"Required variable '{var_expr}' is not set in context")
        return None  # или raise ValueError для всех отсутствующих переменных
```

2. **Добавить валидацию параметров перед SQL запросами:**
```python
async def _execute_database_query_assertion(self, assertion: Dict[str, Any]):
    query = self._resolve_variables(assertion.get("query"))
    params = self._resolve_variables(assertion.get("params", {}))
    
    # Валидация критических параметров
    for param_name, param_value in params.items():
        if param_name in ['zone_id', 'node_id'] and (not param_value or param_value == ''):
            raise ValueError(f"Parameter '{param_name}' is empty or not set. "
                           f"Check if API returned data or variable is set correctly.")
    
    rows = await self.db.wait(query, params=params, ...)
```

3. **Добавить автоматическое извлечение zone_id/node_id из API ответов:**
```python
async def _run_actions_scenario(self, scenario, scenario_name):
    # После каждого API запроса, который возвращает zones/nodes, 
    # автоматически извлекать zone_id/node_id если они не установлены
    for action in actions:
        if action.get('type') in ['api_get', 'api_post']:
            endpoint = action.get('endpoint', '')
            if '/api/zones' in endpoint and 'save' in action:
                # После получения ответа, извлечь zone_id если не установлен
                response = self.context.get(action['save'])
                if response and not self.context.get('zone_id'):
                    # Извлечь первый zone_id из ответа
                    zone_id = self._extract_zone_id_from_response(response)
                    if zone_id:
                        self.context['zone_id'] = zone_id
                        logger.info(f"Auto-extracted zone_id={zone_id} from {action['save']}")
```

**Ожидаемый результат:**
- Все SQL запросы будут получать валидные zone_id/node_id
- Ошибки "invalid input syntax" исчезнут
- Тесты будут падать с понятными сообщениями о недостающих переменных

---

### Приоритет 2: ВЫСОКИЙ - Исправление WebSocket авторизации

**Файлы:**
- `tests/e2e/runner/ws_client.py`
- `tests/e2e/runner/e2e_runner.py`

**Изменения:**

1. **Валидация zone_id перед подпиской:**
```python
async def subscribe(self, channel: str):
    # Проверить, что zone_id не пустой в имени канала
    if 'zones.' in channel and channel.endswith('.'):
        raise ValueError(f"Invalid channel name: {channel}. zone_id is empty.")
    # ... остальной код
```

2. **Улучшить обработку ошибок авторизации:**
```python
async def subscribe(self, channel: str):
    try:
        # ... код подписки
    except RuntimeError as e:
        if "403" in str(e) or "Unauthorized" in str(e):
            # Проверить валидность токена
            if not self.auth_client or not await self.auth_client.is_token_valid():
                logger.warning("Token invalid, refreshing...")
                await self.auth_client.get_token()
                # Повторить подписку
                return await self.subscribe(channel)
        raise
```

**Ожидаемый результат:**
- WebSocket подписки будут работать корректно
- Автоматическое обновление токенов при истечении

---

### Приоритет 3: СРЕДНИЙ - Создание отсутствующих таблиц/endpoints

**Файлы:**
- Backend Laravel миграции
- Backend Laravel контроллеры

**Изменения:**

1. **Создать миграцию для `zone_bindings`:**
```php
// database/migrations/xxxx_create_zone_bindings_table.php
Schema::create('zone_bindings', function (Blueprint $table) {
    $table->id();
    $table->foreignId('zone_id')->constrained('zones');
    $table->string('role'); // main_pump, etc.
    $table->foreignId('node_id')->nullable()->constrained('nodes');
    $table->string('channel')->nullable();
    $table->timestamps();
    $table->unique(['zone_id', 'role']);
});
```

2. **Реализовать API endpoints:**
   - `POST /api/zones/{id}/bindings` - создание binding
   - `DELETE /api/zones/{id}/bindings/{role}` - удаление binding
   - `POST /api/zones/attach-recipe` - прикрепление рецепта
   - `POST /api/zones/detach-recipe` - открепление рецепта
   - `POST /api/zones/start` - запуск цикла
   - `POST /api/zones/pause` - пауза цикла
   - `GET /api/zones/{id}/snapshot` - получение snapshot

**Ожидаемый результат:**
- Все API endpoints будут работать
- Таблицы будут созданы в БД

---

### Приоритет 4: НИЗКИЙ - Улучшение обработки ошибок в сценариях

**Файлы:** Все YAML сценарии

**Изменения:**

1. **Добавить проверки наличия данных перед использованием:**
```yaml
actions:
  - step: get_zones
    type: api_get
    endpoint: /api/zones
    save: zones_response
    # Добавить валидацию ответа
    validate:
      - field: data.data
        operator: is_not_empty
        message: "No zones found in response"

  - step: set_zone_id
    type: set
    zone_id: ${zones_response.data.data[0].id}
    # Добавить fallback
    fallback:
      zone_id: ${zones_response.data[0].id}  # Альтернативный путь
```

2. **Добавить optional флаги для необязательных шагов:**
```yaml
  - step: create_binding
    type: api_post
    endpoint: /api/zones/${zone_id}/bindings
    optional: true  # Уже есть, но нужно использовать чаще
```

**Ожидаемый результат:**
- Тесты будут более устойчивыми к изменениям API
- Понятные сообщения об ошибках

---

## 📋 Чеклист исправлений

### Фаза 1: Критические исправления (1-2 дня)
- [ ] Исправить `_resolve_variables()` для валидации zone_id/node_id
- [ ] Добавить валидацию параметров перед SQL запросами
- [ ] Добавить автоматическое извлечение zone_id/node_id из API ответов
- [ ] Протестировать на сценарии `E01_bootstrap`

### Фаза 2: WebSocket и авторизация (1 день)
- [ ] Валидация zone_id перед WebSocket подпиской
- [ ] Улучшить обработку ошибок авторизации
- [ ] Автоматическое обновление токенов
- [ ] Протестировать на сценарии `E02_auth_ws_api`

### Фаза 3: Backend endpoints (2-3 дня)
- [ ] Создать миграцию для `zone_bindings`
- [ ] Реализовать API endpoints для bindings
- [ ] Реализовать API endpoints для grow cycle
- [ ] Реализовать API endpoint для snapshot
- [ ] Протестировать на соответствующих сценариях

### Фаза 4: Улучшение сценариев (1 день)
- [ ] Добавить валидацию ответов API в сценарии
- [ ] Добавить fallback механизмы
- [ ] Улучшить сообщения об ошибках
- [ ] Запустить полный набор тестов

---

## 🎯 Метрики успеха

После исправлений ожидается:
- **Успешность тестов:** >80% (сейчас ~30%)
- **Критические ошибки:** 0
- **Время выполнения:** без изменений или улучшение
- **Понятность ошибок:** улучшение на 50%

---

## 📝 Дополнительные рекомендации

1. **Добавить pre-flight проверки:**
   - Проверка наличия зон/узлов в БД перед запуском тестов
   - Проверка доступности всех сервисов

2. **Улучшить логирование:**
   - Логировать все значения переменных перед SQL запросами
   - Логировать полные API ответы при ошибках

3. **Добавить retry механизмы:**
   - Retry для API запросов с временными ошибками
   - Retry для WebSocket подключений

4. **Создать helper функции:**
   - `ensure_zone_exists()` - гарантировать наличие зоны
   - `ensure_node_exists()` - гарантировать наличие узла
   - `get_or_create_zone()` - получить или создать зону

---

## 🔗 Связанные файлы

- `tests/e2e/runner/e2e_runner.py` - основной runner
- `tests/e2e/runner/ws_client.py` - WebSocket клиент
- `tests/e2e/runner/db_probe.py` - работа с БД
- `tests/e2e/scenarios/**/*.yaml` - все сценарии
- `backend/laravel/app/Http/Controllers/**` - API контроллеры
- `backend/laravel/database/migrations/**` - миграции БД

---

**Автор анализа:** AI Assistant (Expert Mode)  
**Дата:** 2025-12-15



