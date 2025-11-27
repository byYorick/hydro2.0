# Рекомендуемые исправления найденных проблем

## Критические исправления (приоритет 1)

### 1. Исправить race condition в кешировании

**Файл:** `backend/services/automation-engine/services/pid_config_service.py`

**Текущий код:**
```python
if age.total_seconds() < _cache_ttl_seconds:
    # Обновляем setpoint в кешированном конфиге
    config.setpoint = setpoint
    return config
```

**Исправление:**
```python
if age.total_seconds() < _cache_ttl_seconds:
    # Проверяем, не обновился ли конфиг в БД
    # Читаем updated_at из БД для сравнения
    rows = await fetch(
        """
        SELECT updated_at
        FROM zone_pid_configs
        WHERE zone_id = $1 AND type = $2
        """,
        zone_id, correction_type
    )
    
    if rows:
        db_updated_at = rows[0]['updated_at']
        if isinstance(db_updated_at, str):
            db_updated_at = datetime.fromisoformat(db_updated_at.replace('Z', '+00:00'))
        
        # Если конфиг обновился в БД, инвалидируем кеш
        if db_updated_at > timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp:
            # Конфиг обновился - инвалидируем кеш и перезагружаем
            _config_cache[zone_id].pop(correction_type, None)
            # Продолжаем загрузку из БД ниже
        else:
            # Конфиг не обновился - используем кеш
            config.setpoint = setpoint
            return config
    else:
        # Конфиг удален из БД - инвалидируем кеш
        _config_cache[zone_id].pop(correction_type, None)
        # Продолжаем загрузку дефолтов ниже
```

**Альтернативное решение (проще):**
Уменьшить TTL кеша до 10-15 секунд:
```python
_cache_ttl_seconds = 10  # TTL кеша: 10 секунд
```

---

### 2. Сделать `enable_autotune` и `adaptation_rate` обязательными

**Файл:** `backend/laravel/app/Http/Requests/UpdateZonePidConfigRequest.php`

**Текущий код:**
```php
'config.enable_autotune' => ['sometimes', 'boolean'],
'config.adaptation_rate' => ['sometimes', 'numeric', 'min:0', 'max:1'],
```

**Исправление:**
```php
'config.enable_autotune' => ['required', 'boolean'],
'config.adaptation_rate' => ['required', 'numeric', 'min:0', 'max:1'],
```

---

## Важные исправления (приоритет 2)

### 3. Добавить валидацию порядка зон в форму

**Файл:** `backend/laravel/app/Http/Requests/UpdateZonePidConfigRequest.php`

**Добавить метод:**
```php
public function withValidator($validator)
{
    $validator->after(function ($validator) {
        $config = $this->input('config');
        
        if (isset($config['dead_zone']) && isset($config['close_zone']) && isset($config['far_zone'])) {
            if ($config['close_zone'] <= $config['dead_zone']) {
                $validator->errors()->add('config.close_zone', 'Ближняя зона должна быть больше мертвой зоны.');
            }
            
            if ($config['far_zone'] <= $config['close_zone']) {
                $validator->errors()->add('config.far_zone', 'Дальняя зона должна быть больше ближней зоны.');
            }
        }
    });
}
```

---

### 4. Добавить проверку типов в `_json_to_pid_config()`

**Файл:** `backend/services/automation-engine/services/pid_config_service.py`

**Текущий код:**
```python
if 'zone_coeffs' in config_json:
    coeffs = config_json['zone_coeffs']
    if 'close' in coeffs:
```

**Исправление:**
```python
if 'zone_coeffs' in config_json:
    coeffs = config_json['zone_coeffs']
    if not isinstance(coeffs, dict):
        logger.warning(f"Invalid zone_coeffs type: {type(coeffs)}, expected dict. Using defaults.")
        coeffs = {}
    
    if 'close' in coeffs and isinstance(coeffs['close'], dict):
        zone_coeffs[PidZone.CLOSE] = PidZoneCoeffs(
            kp=float(coeffs['close'].get('kp', 0.0)),
            ki=float(coeffs['close'].get('ki', 0.0)),
            kd=float(coeffs['close'].get('kd', 0.0)),
        )
    else:
        logger.warning(f"Missing or invalid 'close' zone_coeffs. Using defaults.")
    
    if 'far' in coeffs and isinstance(coeffs['far'], dict):
        zone_coeffs[PidZone.FAR] = PidZoneCoeffs(
            kp=float(coeffs['far'].get('kp', 0.0)),
            ki=float(coeffs['far'].get('ki', 0.0)),
            kd=float(coeffs['far'].get('kd', 0.0)),
        )
    else:
        logger.warning(f"Missing or invalid 'far' zone_coeffs. Using defaults.")
```

---

### 5. Добавить очистку PID инстансов при удалении зоны

**Файл:** `backend/services/automation-engine/services/zone_automation_service.py`

**Добавить метод:**
```python
async def _check_zone_deletion(self, zone_id: int) -> None:
    """Проверить, не была ли зона удалена, и очистить PID инстансы."""
    try:
        # Проверяем существование зоны
        zone = await self.zone_repo.get_zone(zone_id)
        if zone is None:
            # Зона удалена - очищаем PID инстансы
            if zone_id in self.ph_controller._pid_by_zone:
                del self.ph_controller._pid_by_zone[zone_id]
                self.ph_controller._last_pid_tick.pop(zone_id, None)
            if zone_id in self.ec_controller._pid_by_zone:
                del self.ec_controller._pid_by_zone[zone_id]
                self.ec_controller._last_pid_tick.pop(zone_id, None)
            invalidate_cache(zone_id)
            logger.info(f"Cleared PID instances for deleted zone {zone_id}")
    except Exception as e:
        logger.warning(f"Failed to check zone deletion for zone {zone_id}: {e}", exc_info=True)
```

**Вызывать в начале `process_zone()`:**
```python
async def process_zone(self, zone_id: int) -> None:
    # Проверка удаления зоны
    await self._check_zone_deletion(zone_id)
    
    # Проверка обновлений PID конфигов
    await self._check_pid_config_updates(zone_id)
    # ... остальной код
```

---

## Желательные исправления (приоритет 3)

### 6. Повысить уровень логирования для дефолтных конфигов

**Файл:** `backend/services/automation-engine/services/pid_config_service.py`

**Изменить:**
```python
logger.debug(f"Using default PID config: zone={zone_id}, type={correction_type}")
```

**На:**
```python
logger.info(f"Using default PID config: zone={zone_id}, type={correction_type}")
```

---

### 7. Добавить CHECK constraints в БД

**Создать новую миграцию:**
```php
Schema::table('zone_pid_configs', function (Blueprint $table) {
    // Проверка, что dead_zone < close_zone < far_zone
    DB::statement('
        ALTER TABLE zone_pid_configs 
        ADD CONSTRAINT zone_pid_configs_zones_order_check 
        CHECK (
            (config->>\'dead_zone\')::float < (config->>\'close_zone\')::float 
            AND (config->>\'close_zone\')::float < (config->>\'far_zone\')::float
        )
    ');
    
    // Проверка диапазонов для pH
    DB::statement('
        ALTER TABLE zone_pid_configs 
        ADD CONSTRAINT zone_pid_configs_ph_target_check 
        CHECK (
            type != \'ph\' OR ((config->>\'target\')::float >= 0 AND (config->>\'target\')::float <= 14)
        )
    ');
    
    // Проверка диапазонов для EC
    DB::statement('
        ALTER TABLE zone_pid_configs 
        ADD CONSTRAINT zone_pid_configs_ec_target_check 
        CHECK (
            type != \'ec\' OR ((config->>\'target\')::float >= 0 AND (config->>\'target\')::float <= 10)
        )
    ');
});
```

---

## Итог

**Критические исправления:** 2
**Важные исправления:** 3
**Желательные исправления:** 2

**Общая оценка:** Система работает корректно, но есть несколько мест для улучшения надежности и производительности.

