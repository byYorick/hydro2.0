# Критические проблемы и исправления

## 🐛 Критические баги

### 1. Использование неинициализированной переменной (main.py:215)

**Проблема:**
```python
# Строка 213-224
if capabilities.get("light_control", False):
    light_cmd = await check_and_control_lighting(zone_id, targets, datetime.now())
if light_cmd:  # ❌ light_cmd может быть не определен, если light_control = False
    # ...
```

**Исправление:**
```python
light_cmd = None
if capabilities.get("light_control", False):
    light_cmd = await check_and_control_lighting(zone_id, targets, datetime.now())
if light_cmd:
    # ...
```

### 2. Неправильный вызов функции (main.py:271)

**Проблема:**
```python
# Строка 270-271
if capabilities.get("recirculation", False):
    recirculation_cmd = await check_and_control_recirculation(zone_id, targets, telemetry)
    # ❌ Функция ожидает (zone_id, targets, mqtt_client, gh_uid)
    # Но вызывается с (zone_id, targets, telemetry)
```

**Исправление:**
```python
if capabilities.get("recirculation", False):
    recirculation_cmd = await check_and_control_recirculation(
        zone_id, targets, mqtt, gh_uid
    )
```

**Или изменить сигнатуру функции:**
```python
# В irrigation_controller.py
async def check_and_control_recirculation(
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]]  # Убрать mqtt_client и gh_uid
) -> Optional[Dict[str, Any]]:
    # Убрать использование mqtt_client и gh_uid из функции
```

### 3. Потенциальные None значения

**Проблема:**
```python
# main.py:288-292
ph_target = targets.get("ph")
ph_current = telemetry.get("ph")
if ph_target is not None and ph_current is not None:
    ph_target_val = float(ph_target) if isinstance(ph_target, (int, float, str)) else None
    ph_current_val = float(ph_current) if isinstance(ph_current, (int, float)) else None
    # ❌ ph_target_val или ph_current_val могут быть None после конвертации
    if ph_target_val is not None and ph_current_val is not None:
```

**Исправление:**
```python
ph_target = targets.get("ph")
ph_current = telemetry.get("ph")
if ph_target is not None and ph_current is not None:
    try:
        ph_target_val = float(ph_target)
        ph_current_val = float(ph_current)
    except (ValueError, TypeError):
        logger.warning(f"Zone {zone_id}: Invalid pH values - target={ph_target}, current={ph_current}")
        ph_target_val = None
        ph_current_val = None
    
    if ph_target_val is not None and ph_current_val is not None:
        # ...
```

## 🔒 Проблемы безопасности

### 4. Отсутствие валидации конфигурации

**Проблема:**
```python
# main.py:574-578
gh_uid = _extract_gh_uid_from_config(cfg)
if not gh_uid:
    logger.warning("No greenhouse UID found in config, sleeping before retry")
    await asyncio.sleep(15)
    continue
# ❌ Нет валидации структуры cfg
```

**Исправление:**
```python
def validate_config(cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Валидация конфигурации. Возвращает (is_valid, error_message)."""
    if not isinstance(cfg, dict):
        return False, "Config must be a dictionary"
    
    if "greenhouses" not in cfg:
        return False, "Config missing 'greenhouses' key"
    
    if not isinstance(cfg["greenhouses"], list):
        return False, "'greenhouses' must be a list"
    
    if len(cfg["greenhouses"]) == 0:
        return False, "'greenhouses' list is empty"
    
    gh = cfg["greenhouses"][0]
    if not isinstance(gh, dict):
        return False, "Greenhouse must be a dictionary"
    
    if "uid" not in gh or not isinstance(gh["uid"], str):
        return False, "Greenhouse must have 'uid' string field"
    
    return True, None

# В main loop:
cfg = await fetch_full_config(client, s.laravel_api_url, s.laravel_api_token)
if not cfg:
    logger.warning("Config fetch returned None, sleeping before retry")
    await asyncio.sleep(15)
    continue

is_valid, error_msg = validate_config(cfg)
if not is_valid:
    logger.error(f"Invalid config structure: {error_msg}")
    await asyncio.sleep(15)
    continue
```

### 5. SQL Injection (защищено, но можно улучшить)

**Текущее состояние:** Используются параметризованные запросы ✅

**Улучшение:** Добавить валидацию типов параметров:
```python
def validate_zone_id(zone_id: Any) -> int:
    """Валидация zone_id."""
    if not isinstance(zone_id, int):
        raise ValueError(f"zone_id must be int, got {type(zone_id)}")
    if zone_id <= 0:
        raise ValueError(f"zone_id must be positive, got {zone_id}")
    return zone_id

# Использование:
zone_id = validate_zone_id(zone_id)
rows = await fetch("SELECT ... WHERE zone_id = $1", zone_id)
```

## ⚡ Проблемы производительности

### 6. Последовательная обработка зон

**Проблема:**
```python
# main.py:590-597
for zone_row in zones:
    zone_id = zone_row["id"]
    try:
        await check_and_correct_zone(zone_id, mqtt, gh_uid, cfg)
    except Exception as e:
        # ...
```

**Исправление:**
```python
async def process_zones_parallel(
    zones: List[Dict[str, Any]],
    mqtt: MqttClient,
    gh_uid: str,
    cfg: Dict[str, Any],
    max_concurrent: int = 5
) -> None:
    """Обработка зон параллельно с ограничением."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_zone(zone_row: Dict[str, Any]) -> None:
        async with semaphore:
            zone_id = zone_row["id"]
            try:
                await check_and_correct_zone(zone_id, mqtt, gh_uid, cfg)
            except Exception as e:
                error_type = type(e).__name__
                LOOP_ERRORS.labels(error_type=error_type).inc()
                logger.error(f"Error checking zone {zone_id}: {e}", exc_info=True)
    
    tasks = [process_zone(zone_row) for zone_row in zones]
    await asyncio.gather(*tasks, return_exceptions=True)

# В main loop:
zones = await fetch("SELECT DISTINCT z.id, z.status FROM zones z ...")
if zones:
    await process_zones_parallel(zones, mqtt, gh_uid, cfg)
```

### 7. Множественные запросы к БД

**Проблема:**
```python
# В check_and_correct_zone делается 4+ отдельных запроса:
recipe_info = await get_zone_recipe_and_targets(zone_id)
telemetry = await get_zone_telemetry_last(zone_id)
nodes = await get_zone_nodes(zone_id)
capabilities = await get_zone_capabilities(zone_id)
```

**Исправление:**
```python
async def get_zone_data_batch(zone_id: int) -> Dict[str, Any]:
    """Получить все данные зоны одним запросом."""
    # Использовать CTE или JOIN для объединения запросов
    rows = await fetch("""
        WITH zone_info AS (
            SELECT 
                z.id as zone_id,
                z.capabilities,
                zri.current_phase_index,
                rp.targets,
                rp.name as phase_name
            FROM zones z
            LEFT JOIN zone_recipe_instances zri ON zri.zone_id = z.id
            LEFT JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id 
                AND rp.phase_index = zri.current_phase_index
            WHERE z.id = $1
        ),
        telemetry_data AS (
            SELECT metric_type, value
            FROM telemetry_last
            WHERE zone_id = $1
        ),
        nodes_data AS (
            SELECT n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1 AND n.status = 'online'
        )
        SELECT 
            (SELECT row_to_json(zone_info) FROM zone_info) as zone_info,
            (SELECT json_object_agg(metric_type, value) FROM telemetry_data) as telemetry,
            (SELECT json_agg(row_to_json(nodes_data)) FROM nodes_data) as nodes
    """, zone_id)
    
    if not rows or not rows[0]:
        return {}
    
    result = rows[0]
    return {
        "recipe_info": result.get("zone_info"),
        "telemetry": result.get("telemetry") or {},
        "nodes": result.get("nodes") or [],
        "capabilities": result.get("zone_info", {}).get("capabilities") or {}
    }
```

## 🏗️ Архитектурные проблемы

### 8. Дублирование логики pH/EC корректировки

**Проблема:** Почти идентичный код для pH и EC (строки 285-393 и 394-480)

**Исправление:** Создать общий контроллер:

```python
# correction_controller.py
from typing import Optional, Dict, Any
from enum import Enum

class CorrectionType(Enum):
    PH = "ph"
    EC = "ec"

class CorrectionController:
    def __init__(self, correction_type: CorrectionType):
        self.correction_type = correction_type
        self.metric_name = correction_type.value.upper()
        self.event_prefix = correction_type.value.upper()
    
    async def check_and_correct(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        nodes: Dict[str, Dict[str, Any]],
        water_level_ok: bool
    ) -> Optional[Dict[str, Any]]:
        """Универсальная логика корректировки."""
        target_key = self.correction_type.value
        current = telemetry.get(self.metric_name) or telemetry.get(target_key)
        target = targets.get(target_key)
        
        if target is None or current is None:
            return None
        
        try:
            target_val = float(target)
            current_val = float(current)
        except (ValueError, TypeError):
            return None
        
        diff = current_val - target_val
        
        if abs(diff) <= 0.2:
            return None
        
        # Проверка cooldown
        should_correct, reason = await should_apply_correction(
            zone_id, target_key, current_val, target_val, diff
        )
        
        if not should_correct:
            await create_zone_event(
                zone_id,
                f'{self.event_prefix}_CORRECTION_SKIPPED',
                {
                    f'current_{target_key}': current_val,
                    f'target_{target_key}': target_val,
                    'diff': diff,
                    'reason': reason
                }
            )
            return None
        
        if not water_level_ok:
            return None
        
        # Найти узел для корректировки
        irrig_node = self._find_irrigation_node(nodes)
        if not irrig_node:
            return None
        
        # Определить тип корректировки
        correction_type = self._determine_correction_type(diff)
        amount = self._calculate_amount(abs(diff))
        
        return {
            'node_uid': irrig_node['node_uid'],
            'channel': irrig_node['channel'],
            'cmd': f'adjust_{target_key}',
            'params': {
                'amount': amount,
                'type': correction_type
            },
            'event_type': f'{self.event_prefix}_CORRECTED',
            'event_details': {
                'correction_type': correction_type,
                f'current_{target_key}': current_val,
                f'target_{target_key}': target_val,
                'diff': diff,
                'dose_ml': amount
            }
        }
    
    def _find_irrigation_node(self, nodes: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Найти узел для полива."""
        for key, node_info in nodes.items():
            if node_info["type"] == "irrig":
                return node_info
        return None
    
    def _determine_correction_type(self, diff: float) -> str:
        """Определить тип корректировки."""
        if self.correction_type == CorrectionType.PH:
            return "add_base" if diff < -0.2 else "add_acid"
        else:  # EC
            return "add_nutrients" if diff < -0.2 else "dilute"
    
    def _calculate_amount(self, diff: float) -> float:
        """Рассчитать количество для дозирования."""
        if self.correction_type == CorrectionType.PH:
            return abs(diff) * 10
        else:  # EC
            return abs(diff) * 100

# Использование в main.py:
ph_controller = CorrectionController(CorrectionType.PH)
ec_controller = CorrectionController(CorrectionType.EC)

if capabilities.get("ph_control", False):
    ph_cmd = await ph_controller.check_and_correct(
        zone_id, targets, telemetry, nodes, water_level_ok
    )
    if ph_cmd:
        await publish_correction_command(...)
        await create_zone_event(...)

if capabilities.get("ec_control", False):
    ec_cmd = await ec_controller.check_and_correct(
        zone_id, targets, telemetry, nodes, water_level_ok
    )
    if ec_cmd:
        await publish_correction_command(...)
        await create_zone_event(...)
```

## 📝 Рекомендации по приоритетам

1. **Немедленно исправить:**
   - Баг с `light_cmd` (проблема #1)
   - Баг с `recirculation` (проблема #2)
   - Валидация конфигурации (проблема #4)

2. **В ближайшее время:**
   - Параллельная обработка зон (проблема #6)
   - Batch запросы к БД (проблема #7)
   - Выделение Correction Controller (проблема #8)

3. **В рамках рефакторинга:**
   - Остальные архитектурные улучшения
   - Полный переход на репозитории и сервисы

