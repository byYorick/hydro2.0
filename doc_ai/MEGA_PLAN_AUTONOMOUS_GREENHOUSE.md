# MEGA_PLAN_AUTONOMOUS_GREENHOUSE.md
# Мега-план: Автономная теплица "Посадил и Забыл"
# Hydro 2.0 Autonomous Greenhouse Roadmap

**Версия:** 1.0  
**Дата создания:** 2026-02-16  
**Горизонт планирования:** 12 месяцев  
**Статус:** Концептуальный план

---

## Совместимость

```
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
```

---

# ЧАСТЬ 1: АНАЛИЗ ТЕКУЩЕГО СОСТОЯНИЯ

## 1.1. Что уже реализовано ✅

### Автоматизация (Automation-Engine)

| Компонент | Статус | Автономность |
|-----------|--------|--------------|
| pH/EC коррекция | ✅ Полностью | Автоматическая по targets |
| Климат-контроль | ✅ Полностью | Автоматический по targets |
| Освещение | ✅ Полностью | По расписанию + фотопериод |
| Полив | ✅ Полностью | По расписанию из рецепта |
| Events & Alerts | ✅ Полностью | Автоматическое обнаружение |
| Workflow Recovery | ✅ Частично | Восстановление после рестарта |
| Two-Tank Workflow | ✅ Частично | State machine для коррекции |

### Рецепты и циклы (Recipe Engine)

| Компонент | Статус | Описание |
|-----------|--------|----------|
| GrowCycle | ✅ Полностью | Центр истины для циклов |
| RecipeRevision | ✅ Полностью | Версионирование рецептов |
| Effective Targets | ✅ Полностью | Единый контракт для контроллеров |
| Фазы по времени | ✅ Полностью | Автопереход по duration |
| Overrides | ✅ Частично | Ручные перекрытия параметров |

### Мониторинг

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Prometheus metrics | ✅ Полностью | Все сервисы |
| Grafana dashboards | ✅ Полностью | Визуализация |
| Alertmanager | ✅ Полностью | Уведомления |
| Zone Health Monitor | ✅ Частично | Health score |

### Инфраструктура

| Компонент | Статус | Описание |
|-----------|--------|----------|
| MQTT Broker | ✅ Полностью | Mosquitto |
| PostgreSQL + TimescaleDB | ✅ Полностью | TSDB для телеметрии |
| Docker Compose | ✅ Полностью | Dev/Prod окружения |
| ESP32 прошивки | ⚠️ Частично | Базовый функционал |

---

## 1.2. Критические пробелы для "Посадил и забыл" ❌

### Уровень 1: Критично (блокирует автономность)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CRITICAL GAPS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. AI НЕ ПРИНИМАЕТ РЕШЕНИЯ АВТОМАТИЧЕСКИ                               │
│     └── Только рекомендации → требуется человек                         │
│                                                                          │
│  2. НЕТ АВТОМАТИЧЕСКОГО ВОССТАНОВЛЕНИЯ ПОСЛЕ СБОЕВ                      │
│     └── Node offline → только alert, нет auto-recovery                  │
│                                                                          │
│  3. ФАЗЫ ПЕРЕХОДЯТ ТОЛЬКО ПО ВРЕМЕНИ                                    │
│     └── Нет перехода по состоянию растений                              │
│                                                                          │
│  4. НЕТ АДАПТАЦИИ К ВНЕШНИМ УСЛОВИЯМ                                    │
│     └── Погода, сезон, внешняя температура игнорируются                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Уровень 2: Важно (снижает надёжность)

| Пробел | Влияние |
|--------|---------|
| Нет предиктивного обслуживания | Внезапные отказы оборудования |
| Нет адаптивного полива | Недолив/перелив |
| Нет обнаружения аномалий | Проблемы выявляются поздно |
| Нет определения дефицитов | Визуальные симптомы → поздно |
| Нет анализа роста | Неоптимальные условия |

### Уровень 3: Желательно (улучшает результат)

| Пробел | Влияние |
|--------|---------|
| Нет Computer Vision | Нет объективной оценки растений |
| Нет интеграции с погодой | Упущенные оптимизации |
| Нет самообучения | Система не улучшается |
| Нет прогноза урожая | Неизвестен ожидаемый результат |

---

## 1.3. Архитектурный анализ

### Текущий поток данных

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CURRENT DATA FLOW                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ESP32 ──► MQTT ──► History-Logger ──► PostgreSQL ──► Laravel         │
│                                               │                          │
│                                               ▼                          │
│                                         Frontend                         │
│                                                                          │
│   Scheduler ──► Automation-Engine ──► History-Logger ──► MQTT ──► ESP32 │
│                                                                          │
│   AI Layer (digital-twin):                                              │
│   └── Только симуляция и рекомендации (НИЧЕГО НЕ МЕНЯЕТ)                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Целевой поток данных для автономности

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TARGET AUTONOMOUS DATA FLOW                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ESP32 ──► MQTT ──► History-Logger ──► PostgreSQL                      │
│      │                           │              │                        │
│      │                           │              ▼                        │
│      │                           │      ┌──────────────────┐            │
│      │                           │      │ INTELLIGENCE     │            │
│      │                           │      │ LAYER            │            │
│      │                           │      │                  │            │
│      │                           │      │ • Anomaly Detect │            │
│      │                           │      │ • Predictive     │            │
│      │                           │      │ • Auto-Pilot     │            │
│      │                           │      │ • Auto-Recovery  │            │
│      │                           │      │ • Optimization   │            │
│      │                           │      └────────┬─────────┘            │
│      │                           │               │                       │
│      │                           ▼               ▼                       │
│      │                      ┌──────────────────────┐                    │
│      │                      │ AUTOMATION-ENGINE    │                    │
│      │                      │ + AI Decisions       │                    │
│      │                      └──────────┬───────────┘                    │
│      │                                 │                                │
│      ◄─────────────────────────────────┘                                │
│             (команды с auto-approval)                                    │
│                                                                          │
│   External Data:                                                        │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                  │
│   │ Weather API │   │ Camera/CV   │   │ External    │                  │
│   │             │   │             │   │ Sensors     │                  │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                  │
│          │                 │                 │                          │
│          └─────────────────┴─────────────────┘                          │
│                            │                                            │
│                            ▼                                            │
│                    INTELLIGENCE LAYER                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# ЧАСТЬ 2: ЦЕЛЕВАЯ АРХИТЕКТУРА

## 2.1. Слои автономной системы

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS GREENHOUSE ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LAYER 5: USER INTERFACE                        │   │
│  │  • Dashboard (real-time monitoring)                               │   │
│  │  • Mobile App (push notifications, remote control)                │   │
│  │  • AI Assistant (natural language interaction)                    │   │
│  │  • Reports & Analytics (historical insights)                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                   │                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LAYER 4: INTELLIGENCE (NEW)                    │   │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────────┐    │   │
│  │  │ Auto-Pilot     │ │ Auto-Recovery  │ │ Anomaly Detection  │    │   │
│  │  │ Manager        │ │ Manager        │ │ Engine             │    │   │
│  │  └────────────────┘ └────────────────┘ └────────────────────┘    │   │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────────┐    │   │
│  │  │ Predictive     │ │ Growth Stage   │ │ Optimization       │    │   │
│  │  │ Maintenance    │ │ Detector       │ │ Engine             │    │   │
│  │  └────────────────┘ └────────────────┘ └────────────────────┘    │   │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────────┐    │   │
│  │  │ Smart          │ │ Weather        │ │ Nutrient           │    │   │
│  │  │ Irrigation     │ │ Adapter        │ │ Analyzer           │    │   │
│  │  └────────────────┘ └────────────────┘ └────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                   │                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LAYER 3: AUTOMATION (EXISTING)                 │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │ pH/EC      │ │ Climate    │ │ Irrigation │ │ Light      │    │   │
│  │  │ Controller │ │ Controller │ │ Controller │ │ Controller │    │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐                    │   │
│  │  │ Scheduler  │ │ Health     │ │ Events &   │                    │   │
│  │  │            │ │ Monitor    │ │ Alerts     │                    │   │
│  │  └────────────┘ └────────────┘ └────────────┘                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                   │                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LAYER 2: DATA & STORAGE                        │   │
│  │  PostgreSQL + TimescaleDB │ Redis Cache │ Object Storage         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                   │                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    LAYER 1: HARDWARE & IOT                        │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐    │   │
│  │  │ ESP32 pH   │ │ ESP32 EC   │ │ ESP32 Pump │ │ ESP32      │    │   │
│  │  │ Node       │ │ Node       │ │ Node       │ │ Climate    │    │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘    │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐                    │   │
│  │  │ ESP32      │ │ ESP32      │ │ IP Cameras │                    │   │
│  │  │ Light      │ │ Relay      │ │ (optional) │                    │   │
│  │  └────────────┘ └────────────┘ └────────────┘                    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2.2. Режимы автономности

```python
class AutonomousMode(Enum):
    """Уровни автономности системы."""
    
    MANUAL = "manual"           # Полностью ручное управление
    ASSISTED = "assisted"       # AI рекомендует, человек решает
    SUPERVISED = "supervised"   # AI действует, уведомляет человека
    AUTONOMOUS = "autonomous"   # Полная автономность с limits
```

### Политика авто-утверждения (Auto-Approval Policy)

```python
AUTO_APPROVAL_POLICY = {
    # Тип решения → минимальный confidence → режимы, где разрешено
    "ph_correction": {
        "min_confidence": 0.85,
        "allowed_modes": ["supervised", "autonomous"],
        "safety_limits": {
            "max_dose_ml_per_hour": 5.0,
            "min_interval_sec": 300,
        }
    },
    "ec_correction": {
        "min_confidence": 0.80,
        "allowed_modes": ["supervised", "autonomous"],
        "safety_limits": {
            "max_dose_ml_per_hour": 20.0,
            "min_interval_sec": 600,
        }
    },
    "irrigation_adjustment": {
        "min_confidence": 0.75,
        "allowed_modes": ["supervised", "autonomous"],
        "safety_limits": {
            "max_adjustment_pct": 30,
        }
    },
    "phase_transition": {
        "min_confidence": 0.90,
        "allowed_modes": ["autonomous"],  # Только в полностью автономном режиме
        "requires_confirmation": True,     # Даже в autonomous требует подтверждения
    },
    "emergency_stop": {
        "min_confidence": 0.50,  # Низкий порог для безопасности
        "allowed_modes": ["assisted", "supervised", "autonomous"],
        "always_notify": True,
    },
}
```

---

# ЧАСТЬ 3: ДЕТАЛЬНЫЙ ПЛАН РЕАЛИЗАЦИИ

## Фаза 1: Фундамент автономности (Месяцы 1-2)

### Epic 1.1: Auto-Pilot Mode Manager 🔴 КРИТИЧНО

**Цель:** Реализовать инфраструктуру для автоматического принятия решений AI.

**Компоненты:**

```
backend/services/automation-engine/
├── domain/
│   ├── auto_pilot/
│   │   ├── __init__.py
│   │   ├── modes.py                    # AutonomousMode enum
│   │   ├── decision_engine.py          # DecisionEngine class
│   │   ├── approval_policy.py          # Auto-approval policies
│   │   └── safety_guardrails.py        # Safety limits enforcement
│   └── models/
│       └── ai_decision.py              # AIDecision model
├── infrastructure/
│   ├── ai_decision_store.py            # Persistence для AI решений
│   └── decision_audit.py               # Аудит AI решений
└── application/
    └── auto_pilot_manager.py           # Main manager
```

**API Endpoints:**

```
POST /api/zones/{zone_id}/auto-pilot/mode
GET  /api/zones/{zone_id}/auto-pilot/status
POST /api/zones/{zone_id}/auto-pilot/decisions
GET  /api/zones/{zone_id}/auto-pilot/decisions/{decision_id}
POST /api/zones/{zone_id}/auto-pilot/decisions/{decision_id}/approve
POST /api/zones/{zone_id}/auto-pilot/decisions/{decision_id}/reject
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 1.1.1 | Определить enum AutonomousMode | 2h | P0 |
| 1.1.2 | Реализовать DecisionEngine | 8h | P0 |
| 1.1.3 | Реализовать AutoApprovalPolicy | 6h | P0 |
| 1.1.4 | Реализовать SafetyGuardrails | 8h | P0 |
| 1.1.5 | Создать AIDecision model | 4h | P0 |
| 1.1.6 | Реализовать AIDecisionStore | 6h | P0 |
| 1.1.7 | Создать API endpoints | 8h | P0 |
| 1.1.8 | Написать тесты | 8h | P0 |
| **Итого** | | **50h** | |

---

### Epic 1.2: Auto-Recovery Manager 🔴 КРИТИЧНО

**Цель:** Автоматическое восстановление после сбоев оборудования.

**Компоненты:**

```
backend/services/automation-engine/
├── domain/
│   └── recovery/
│       ├── __init__.py
│       ├── recovery_procedures.py      # Библиотека процедур восстановления
│       ├── failure_classifier.py       # Классификация типов сбоев
│       └── recovery_state_machine.py   # State machine для восстановления
├── infrastructure/
│   └── recovery_executor.py            # Выполнение процедур восстановления
└── application/
    └── auto_recovery_manager.py        # Main manager
```

**Процедуры восстановления:**

```python
RECOVERY_PROCEDURES = {
    "NODE_OFFLINE": {
        "severity": "warning",
        "steps": [
            {"action": "wait", "params": {"duration_sec": 60}},
            {"action": "check_mqtt_connection", "params": {}},
            {"action": "request_status", "params": {"retry_count": 3}},
            {"action": "switch_to_backup", "params": {}, "optional": True},
            {"action": "alert_operator", "params": {"escalation": True}},
        ],
        "timeout_sec": 300,
    },
    "PH_SENSOR_STUCK": {
        "severity": "warning",
        "steps": [
            {"action": "deactivate_sensor", "params": {}},
            {"action": "request_calibration", "params": {}},
            {"action": "use_backup_sensor", "params": {}, "optional": True},
            {"action": "estimate_from_correlation", "params": {"metric": "ec"}},
        ],
        "timeout_sec": 180,
    },
    "PUMP_FAILURE": {
        "severity": "critical",
        "steps": [
            {"action": "stop_all_pumps", "params": {}},
            {"action": "disable_zone_irrigation", "params": {}},
            {"action": "switch_to_backup_pump", "params": {}, "optional": True},
            {"action": "alert_operator", "params": {"escalation": "immediate"}},
        ],
        "timeout_sec": 60,
    },
    "WATER_LEVEL_CRITICAL": {
        "severity": "critical",
        "steps": [
            {"action": "stop_irrigation", "params": {}},
            {"action": "disable_dosing", "params": {}},
            {"action": "emergency_refill", "params": {}, "optional": True},
            {"action": "alert_operator", "params": {"escalation": "immediate"}},
        ],
        "timeout_sec": 30,
    },
    "COMMUNICATION_LOSS": {
        "severity": "warning",
        "steps": [
            {"action": "use_last_known_state", "params": {}},
            {"action": "safe_mode", "params": {}},
            {"action": "periodic_reconnect_attempt", "params": {"interval_sec": 30}},
        ],
        "timeout_sec": 600,
    },
}
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 1.2.1 | Определить классификацию сбоев | 4h | P0 |
| 1.2.2 | Реализовать FailureClassifier | 6h | P0 |
| 1.2.3 | Создать библиотеку процедур | 8h | P0 |
| 1.2.4 | Реализовать RecoveryStateMachine | 8h | P0 |
| 1.2.5 | Реализовать RecoveryExecutor | 8h | P0 |
| 1.2.6 | Интегрировать с AlertManager | 6h | P0 |
| 1.2.7 | Создать API endpoints | 6h | P0 |
| 1.2.8 | Написать тесты | 8h | P0 |
| **Итого** | | **54h** | |

---

### Epic 1.3: Anomaly Detection Engine 🟠 ВАЖНО

**Цель:** Обнаружение аномалий в телеметрии в реальном времени.

**Компоненты:**

```
backend/services/automation-engine/
├── domain/
│   └── anomaly/
│       ├── __init__.py
│       ├── anomaly_types.py            # Типы аномалий
│       ├── detectors/
│       │   ├── statistical.py          # Статистические методы
│       │   ├── trend.py                # Анализ трендов
│       │   ├── correlation.py          # Корреляционный анализ
│       │   └── pattern.py              # Pattern detection
│       └── anomaly_score.py            # Scoring алгоритм
├── infrastructure/
│   └── anomaly_repository.py           # Хранение аномалий
└── application/
    └── anomaly_detector.py             # Main detector
```

**Типы аномалий:**

```python
class AnomalyType(Enum):
    # Sensor anomalies
    SENSOR_STUCK = "sensor_stuck"              # Застрявшее значение
    SENSOR_SPIKE = "sensor_spike"              # Резкий скачок
    SENSOR_DRIFT = "sensor_drift"              # Дрейф сенсора
    SENSOR_NOISE = "sensor_noise"              # Избыточный шум
    
    # Process anomalies
    UNUSUAL_CONSUMPTION = "unusual_consumption" # Аномалия потребления
    CORRELATION_BREAK = "correlation_break"    # Нарушение корреляции pH↔EC
    TREND_ANOMALY = "trend_anomaly"            # Необычный тренд
    
    # Equipment anomalies
    EQUIPMENT_DEGRADATION = "equipment_degradation"  # Деградация оборудования
    PERFORMANCE_DROP = "performance_drop"            # Снижение производительности
    
    # System anomalies
    COMMUNICATION_ISSUE = "communication_issue"  # Проблемы связи
    TIMING_ANOMALY = "timing_anomaly"            # Аномалия таймингов
```

**Алгоритмы обнаружения:**

```python
class AnomalyDetector:
    """
    Комплексный детектор аномалий с множественными алгоритмами.
    """
    
    def detect(self, zone_id: int, time_window_hours: int = 1) -> List[Anomaly]:
        telemetry = await self.get_telemetry(zone_id, time_window_hours)
        anomalies = []
        
        # 1. Stuck value detection
        anomalies.extend(self._detect_stuck_values(telemetry))
        
        # 2. Spike detection (z-score)
        anomalies.extend(self._detect_spikes(telemetry))
        
        # 3. Trend analysis
        anomalies.extend(self._detect_trend_anomalies(telemetry))
        
        # 4. Correlation analysis (pH ↔ EC)
        anomalies.extend(self._detect_correlation_breaks(telemetry))
        
        # 5. Pattern analysis
        anomalies.extend(self._detect_unusual_patterns(telemetry))
        
        # Aggregate scores
        return self._aggregate_anomalies(anomalies)
    
    def _detect_stuck_values(self, telemetry: DataFrame) -> List[Anomaly]:
        """Detect stuck sensor values (no change for extended period)."""
        for metric in ['ph', 'ec', 'temp_air', 'humidity']:
            values = telemetry[metric]
            if len(values) < 10:
                continue
            
            # Check if variance is too low
            variance = values.var()
            if variance < 0.0001:
                yield Anomaly(
                    type=AnomalyType.SENSOR_STUCK,
                    metric=metric,
                    severity="warning",
                    confidence=0.9,
                    message=f"{metric} sensor may be stuck - variance {variance:.6f}"
                )
    
    def _detect_spikes(self, telemetry: DataFrame) -> List[Anomaly]:
        """Detect sudden spikes using z-score."""
        for metric in ['ph', 'ec']:
            values = telemetry[metric]
            mean = values.mean()
            std = values.std()
            
            if std < 0.001:
                continue
            
            z_scores = np.abs((values - mean) / std)
            spike_indices = np.where(z_scores > 3)[0]
            
            for idx in spike_indices:
                yield Anomaly(
                    type=AnomalyType.SENSOR_SPIKE,
                    metric=metric,
                    severity="info",
                    confidence=0.7,
                    message=f"Unusual {metric} spike: {values.iloc[idx]:.2f} (z-score: {z_scores.iloc[idx]:.2f})"
                )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 1.3.1 | Определить типы аномалий | 3h | P1 |
| 1.3.2 | Реализовать статистический детектор | 6h | P1 |
| 1.3.3 | Реализовать детектор трендов | 6h | P1 |
| 1.3.4 | Реализовать корреляционный анализ | 6h | P1 |
| 1.3.5 | Реализовать pattern detection | 8h | P1 |
| 1.3.6 | Создать AnomalyScore aggregator | 4h | P1 |
| 1.3.7 | Интегрировать с Events/Alerts | 6h | P1 |
| 1.3.8 | Написать тесты | 8h | P1 |
| **Итого** | | **47h** | |

---

## Фаза 2: Интеллектуальная оптимизация (Месяцы 3-4)

### Epic 2.1: Smart Irrigation Engine 🟠 ВАЖНО

**Цель:** Адаптивный полив на основе множества факторов.

**Факторы для оптимизации:**

```python
class IrrigationFactors:
    """Факторы, влияющие на полив."""
    
    # Из рецепта (базовые)
    base_interval_sec: int          # Базовый интервал
    base_duration_sec: int          # Базовая длительность
    
    # Из телеметрии (реальные)
    current_temp: float             # Текущая температура
    current_humidity: float         # Текущая влажность
    water_uptake_rate: float        # Скорость потребления воды
    substrate_moisture: float       # Влажность субстрата (если есть датчик)
    
    # Из состояния (контекстные)
    growth_stage: GrowthStage       # Стадия роста
    days_since_start: int           # Дней от начала цикла
    
    # Внешние (опционально)
    weather_forecast: WeatherData   # Прогноз погоды
    time_of_day: int                # Время суток (час)
    
    # Исторические
    historical_consumption: List    # История потребления
    irrigation_success_rate: float  # Процент успешных поливов
```

**Алгоритм оптимизации:**

```python
class SmartIrrigationEngine:
    """
    Адаптивная оптимизация полива.
    """
    
    async def calculate_optimal_irrigation(
        self, 
        zone_id: int
    ) -> IrrigationPlan:
        factors = await self.gather_factors(zone_id)
        
        # Базовый интервал из рецепта
        base_interval = factors.base_interval_sec
        
        # Множители адаптации
        multipliers = []
        
        # 1. Температура (выше → чаще)
        if factors.current_temp > 25:
            temp_mult = 0.8  # -20% интервала
        elif factors.current_temp < 18:
            temp_mult = 1.2  # +20% интервала
        else:
            temp_mult = 1.0
        multipliers.append(("temperature", temp_mult))
        
        # 2. Влажность (ниже → чаще)
        if factors.current_humidity < 50:
            humidity_mult = 0.85
        elif factors.current_humidity > 70:
            humidity_mult = 1.1
        else:
            humidity_mult = 1.0
        multipliers.append(("humidity", humidity_mult))
        
        # 3. Тренд потребления
        if factors.water_uptake_trend > 1.1:  # Потребление растёт
            consumption_mult = 0.9
        elif factors.water_uptake_trend < 0.9:
            consumption_mult = 1.1
        else:
            consumption_mult = 1.0
        multipliers.append(("consumption_trend", consumption_mult))
        
        # 4. Время суток
        hour = factors.time_of_day
        if 10 <= hour <= 16:  # Пик фотосинтеза
            time_mult = 0.85
        elif 22 <= hour or hour <= 6:  # Ночь
            time_mult = 1.3
        else:
            time_mult = 1.0
        multipliers.append(("time_of_day", time_mult))
        
        # 5. Стадия роста
        stage_multipliers = {
            GrowthStage.GERMINATION: 1.5,
            GrowthStage.SEEDLING: 1.3,
            GrowthStage.VEGETATIVE: 1.0,
            GrowthStage.FLOWERING: 0.9,
            GrowthStage.FRUITING: 0.95,
        }
        stage_mult = stage_multipliers.get(factors.growth_stage, 1.0)
        multipliers.append(("growth_stage", stage_mult))
        
        # Вычисление итогового интервала
        final_multiplier = np.prod([m[1] for m in multipliers])
        optimal_interval = int(base_interval * final_multiplier)
        
        # Safety limits
        min_interval = int(base_interval * 0.5)  # Минимум 50% от базы
        max_interval = int(base_interval * 2.0)  # Максимум 200% от базы
        optimal_interval = max(min_interval, min(max_interval, optimal_interval))
        
        return IrrigationPlan(
            interval_sec=optimal_interval,
            duration_sec=factors.base_duration_sec,
            adjustment_reasons=[{
                "factor": name,
                "multiplier": mult,
                "reason": self._get_factor_reason(name, mult)
            } for name, mult in multipliers],
            confidence=self._calculate_confidence(factors),
        )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 2.1.1 | Создать модель IrrigationFactors | 3h | P1 |
| 2.1.2 | Реализовать сбор факторов | 6h | P1 |
| 2.1.3 | Реализовать алгоритм оптимизации | 8h | P1 |
| 2.1.4 | Добавить safety limits | 4h | P1 |
| 2.1.5 | Интегрировать с scheduler | 6h | P1 |
| 2.1.6 | Создать API endpoints | 4h | P1 |
| 2.1.7 | Написать тесты | 8h | P1 |
| **Итого** | | **39h** | |

---

### Epic 2.2: Growth Stage Detector 🟠 ВАЖНО

**Цель:** Автоматическое определение стадии роста растений.

**Косвенные признаки:**

```python
class GrowthStageSignatures:
    """
    Сигнатуры стадий роста по косвенным признакам.
    """
    
    SIGNATURES = {
        GrowthStage.GERMINATION: {
            "water_uptake_rate": (0.0, 0.3),     # L/day/m²
            "ec_demand_trend": "stable",
            "ph_variability": "low",
            "light_response": "minimal",
            "duration_hint_days": (0, 7),
        },
        GrowthStage.SEEDLING: {
            "water_uptake_rate": (0.3, 1.0),
            "ec_demand_trend": "increasing",
            "ph_variability": "low",
            "light_response": "moderate",
            "duration_hint_days": (7, 21),
        },
        GrowthStage.VEGETATIVE: {
            "water_uptake_rate": (1.0, 3.0),
            "ec_demand_trend": "high",
            "ph_variability": "moderate",
            "light_response": "high",
            "duration_hint_days": (21, 60),
        },
        GrowthStage.FLOWERING: {
            "water_uptake_rate": (2.0, 4.0),
            "ec_demand_trend": "stable_high",
            "ph_variability": "higher",
            "light_response": "peak",
            "duration_hint_days": (60, 90),
        },
        GrowthStage.FRUITING: {
            "water_uptake_rate": (2.5, 5.0),
            "ec_demand_trend": "decreasing",
            "ph_variability": "moderate",
            "light_response": "declining",
            "duration_hint_days": (90, 120),
        },
    }
```

**Алгоритм определения:**

```python
class GrowthStageDetector:
    """
    Определение стадии роста по телеметрии и паттернам потребления.
    """
    
    async def detect_stage(self, zone_id: int) -> GrowthStageAssessment:
        # Сбор данных за последние 7 дней
        telemetry = await self.get_telemetry_window(zone_id, days=7)
        cycle = await self.get_grow_cycle(zone_id)
        
        # Извлечение признаков
        features = {
            "water_uptake_rate": self._calculate_water_uptake(telemetry),
            "ec_demand_trend": self._analyze_ec_trend(telemetry),
            "ph_variability": self._calculate_ph_variability(telemetry),
            "light_response": self._analyze_light_response(telemetry),
            "days_since_start": cycle.days_since_start,
        }
        
        # Сопоставление с сигнатурами
        scores = {}
        for stage, signature in GrowthStageSignatures.SIGNATURES.items():
            score = self._match_signature(features, signature)
            scores[stage] = score
        
        # Выбор наиболее вероятной стадии
        best_stage = max(scores, key=scores.get)
        confidence = scores[best_stage]
        
        return GrowthStageAssessment(
            detected_stage=best_stage,
            confidence=confidence,
            scores=scores,
            features=features,
            recommendation=self._get_recommendation(best_stage, cycle),
        )
    
    def _match_signature(self, features: dict, signature: dict) -> float:
        """Calculate match score between features and signature."""
        score = 0.0
        total_weight = 0.0
        
        # Water uptake match
        if "water_uptake_rate" in signature:
            range_min, range_max = signature["water_uptake_rate"]
            uptake = features["water_uptake_rate"]
            if range_min <= uptake <= range_max:
                score += 1.0
            else:
                # Partial match based on distance
                distance = min(abs(uptake - range_min), abs(uptake - range_max))
                score += max(0, 1 - distance / range_max)
            total_weight += 1.0
        
        # EC trend match
        if "ec_demand_trend" in signature:
            expected = signature["ec_demand_trend"]
            actual = features["ec_demand_trend"]
            if expected == actual:
                score += 1.0
            elif expected == "stable_high" and actual in ["stable", "high"]:
                score += 0.7
            total_weight += 0.8
        
        # Duration hint
        if "duration_hint_days" in signature:
            range_min, range_max = signature["duration_hint_days"]
            days = features["days_since_start"]
            if range_min <= days <= range_max:
                score += 1.0
            total_weight += 0.5
        
        return score / total_weight if total_weight > 0 else 0.0
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 2.2.1 | Определить сигнатуры стадий | 4h | P1 |
| 2.2.2 | Реализовать извлечение признаков | 6h | P1 |
| 2.2.3 | Реализовать алгоритм matching | 8h | P1 |
| 2.2.4 | Создать GrowthStageAssessment model | 3h | P1 |
| 2.2.5 | Интегрировать с Recipe Engine | 6h | P1 |
| 2.2.6 | Создать API endpoints | 4h | P1 |
| 2.2.7 | Написать тесты | 6h | P1 |
| **Итого** | | **37h** | |

---

### Epic 2.3: Predictive Maintenance Engine 🟠 ВАЖНО

**Цель:** Прогнозирование отказов оборудования до их возникновения.

**Индикаторы здоровья оборудования:**

```python
class EquipmentHealthIndicators:
    """Индикаторы здоровья для разного типа оборудования."""
    
    PUMP_INDICATORS = {
        "current_draw_trend": {
            "healthy": "stable",
            "warning": "increasing_10pct",
            "critical": "increasing_20pct",
        },
        "flow_rate_efficiency": {
            "healthy": ">0.95",
            "warning": "0.85-0.95",
            "critical": "<0.85",
        },
        "vibration_pattern": {  # Если есть датчик
            "healthy": "normal",
            "warning": "elevated",
            "critical": "abnormal",
        },
        "operation_hours": {
            "healthy": "<1000",
            "warning": "1000-2000",
            "critical": ">2000",
        },
    }
    
    SENSOR_INDICATORS = {
        "calibration_drift": {
            "healthy": "<0.05/unit",
            "warning": "0.05-0.1/unit",
            "critical": ">0.1/unit",
        },
        "response_time": {
            "healthy": "<5s",
            "warning": "5-15s",
            "critical": ">15s",
        },
        "noise_level": {
            "healthy": "<0.02",
            "warning": "0.02-0.05",
            "critical": ">0.05",
        },
    }
    
    NODE_INDICATORS = {
        "rssi": {
            "healthy": ">-60dBm",
            "warning": "-60 to -75dBm",
            "critical": "<-75dBm",
        },
        "heap_memory": {
            "healthy": ">60KB",
            "warning": "40-60KB",
            "critical": "<40KB",
        },
        "uptime_stability": {
            "healthy": "stable",
            "warning": "frequent_reboots",
            "critical": "unstable",
        },
    }
```

**Прогнозирование отказов:**

```python
class PredictiveMaintenanceEngine:
    """
    Прогнозирование отказов оборудования.
    """
    
    async def analyze_node_health(
        self, 
        node_uid: str,
        analysis_window_days: int = 30
    ) -> HealthPrediction:
        # Сбор исторических данных
        telemetry = await self.get_node_telemetry(node_uid, analysis_window_days)
        commands = await self.get_command_history(node_uid, analysis_window_days)
        events = await self.get_event_history(node_uid, analysis_window_days)
        
        # Анализ по категориям
        health_score = 100.0
        predicted_failures = []
        recommendations = []
        
        # 1. Анализ насосов (если есть)
        pump_health = await self._analyze_pump_health(telemetry, commands)
        health_score -= (100 - pump_health.score)
        if pump_health.predicted_failure:
            predicted_failures.append(pump_health.predicted_failure)
        recommendations.extend(pump_health.recommendations)
        
        # 2. Анализ сенсоров
        sensor_health = await self._analyze_sensor_health(telemetry, events)
        health_score -= (100 - sensor_health.score)
        if sensor_health.predicted_failure:
            predicted_failures.append(sensor_health.predicted_failure)
        recommendations.extend(sensor_health.recommendations)
        
        # 3. Анализ коммуникаций
        comm_health = await self._analyze_communication_health(telemetry, events)
        health_score -= (100 - comm_health.score)
        recommendations.extend(comm_health.recommendations)
        
        # 4. Анализ питания/памяти
        system_health = await self._analyze_system_health(telemetry)
        health_score -= (100 - system_health.score)
        
        # Normalization
        health_score = max(0, min(100, health_score))
        
        return HealthPrediction(
            node_uid=node_uid,
            health_score=health_score,
            health_status=self._classify_health(health_score),
            predicted_failures=predicted_failures,
            recommendations=recommendations,
            next_maintenance=self._calculate_next_maintenance(health_score, predicted_failures),
        )
    
    async def _analyze_pump_health(
        self, 
        telemetry: DataFrame, 
        commands: List[Command]
    ) -> ComponentHealth:
        """Анализ здоровья насоса."""
        health = 100.0
        predictions = []
        recommendations = []
        
        # Тренд потребления тока
        current_values = telemetry[telemetry['metric'] == 'pump_current']['value']
        if len(current_values) > 10:
            trend = self._calculate_trend(current_values)
            if trend > 0.1:  # Растёт на >10%
                health -= 20
                predictions.append(PredictedFailure(
                    component="pump_motor",
                    probability=min(0.8, trend * 5),
                    estimated_days=30 / (trend * 10),
                    reason=f"Current draw increasing ({trend*100:.1f}% over {len(current_values)} samples)"
                ))
                recommendations.append("Monitor pump current closely")
        
        # Эффективность (расход vs время работы)
        efficiency = await self._calculate_pump_efficiency(commands)
        if efficiency < 0.85:
            health -= 15
            recommendations.append(f"Pump efficiency low ({efficiency:.1%}), check for wear")
        
        return ComponentHealth(
            score=health,
            predicted_failure=predictions[0] if predictions else None,
            recommendations=recommendations,
        )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 2.3.1 | Определить индикаторы здоровья | 4h | P1 |
| 2.3.2 | Реализовать анализ насосов | 8h | P1 |
| 2.3.3 | Реализовать анализ сенсоров | 6h | P1 |
| 2.3.4 | Реализовать анализ коммуникаций | 6h | P1 |
| 2.3.5 | Реализовать прогнозирование | 8h | P1 |
| 2.3.6 | Создать maintenance scheduler | 6h | P1 |
| 2.3.7 | Интегрировать с alerts | 4h | P1 |
| 2.3.8 | Написать тесты | 8h | P1 |
| **Итого** | | **50h** | |

---

## Фаза 3: Продвинутая автоматизация (Месяцы 5-6)

### Epic 3.1: Weather Integration 🟡 ЖЕЛАТЕЛЬНО

**Цель:** Адаптация параметров теплицы на основе погодных условий.

**Компоненты:**

```
backend/services/automation-engine/
├── infrastructure/
│   ├── weather_providers/
│   │   ├── __init__.py
│   │   ├── base.py                      # Абстрактный класс
│   │   ├── openweathermap.py            # OpenWeatherMap API
│   │   └── local_weather_station.py     # Локальная метеостанция
│   └── weather_cache.py                 # Кэширование данных
├── domain/
│   └── weather/
│       ├── __init__.py
│       ├── weather_data.py              # Модель данных погоды
│       └── weather_adjustment.py        # Расчёт корректировок
└── application/
    └── weather_adapter.py               # Main adapter
```

**Адаптации на основе погоды:**

```python
class WeatherAdjustments:
    """Корректировки параметров на основе погоды."""
    
    @staticmethod
    def calculate_adjustments(
        weather: WeatherData,
        forecast: List[WeatherData],
        zone_targets: Targets
    ) -> AdjustmentPlan:
        adjustments = {}
        
        # 1. Температура
        if weather.temperature > 30:
            # Жарко → увеличить вентиляцию и полив
            adjustments["ventilation"] = {
                "action": "increase",
                "value": 20,  # +20%
                "reason": "High outdoor temperature"
            }
            adjustments["irrigation"] = {
                "action": "increase",
                "value": 15,  # +15%
                "reason": "Higher evapotranspiration"
            }
        
        elif weather.temperature < 5:
            # Холодно → уменьшить полив, увеличить обогрев
            adjustments["irrigation"] = {
                "action": "decrease",
                "value": 10,
                "reason": "Low temperature, reduced plant activity"
            }
            adjustments["heating"] = {
                "action": "increase",
                "value": 15,
                "reason": "Cold outdoor temperature"
            }
        
        # 2. Влажность
        if weather.humidity > 80:
            # Высокая влажность → увеличить вентиляцию
            adjustments["ventilation"] = {
                "action": "increase",
                "value": 30,
                "reason": "High outdoor humidity, prevent fungal issues"
            }
        
        # 3. Освещение
        if weather.cloud_cover > 70:
            # Облачно → включить досветку
            adjustments["lighting"] = {
                "action": "increase",
                "value": 30,
                "reason": f"Cloud cover {weather.cloud_cover}%"
            }
        
        # 4. Осадки
        if weather.precipitation_probability > 60:
            # Дождь → снизить влажность target
            adjustments["humidity_target"] = {
                "action": "decrease",
                "value": 5,  # -5%
                "reason": "Rain expected, reduce humidity to prevent issues"
            }
        
        # 5. Прогноз (заблаговременная адаптация)
        for future_weather in forecast:
            if future_weather.temperature > 35 and future_weather.hours_ahead <= 6:
                # Жара через 6 часов → подготовиться заранее
                adjustments["preemptive_cooling"] = {
                    "action": "start",
                    "value": future_weather.hours_ahead,
                    "reason": f"Heat wave in {future_weather.hours_ahead} hours"
                }
                break
        
        return AdjustmentPlan(
            adjustments=adjustments,
            confidence=weather.confidence,
            valid_until=datetime.now() + timedelta(hours=3),
        )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 3.1.1 | Создать WeatherData model | 3h | P2 |
| 3.1.2 | Реализовать OpenWeatherMap provider | 6h | P2 |
| 3.1.3 | Реализовать weather caching | 4h | P2 |
| 3.1.4 | Реализовать алгоритм корректировок | 8h | P2 |
| 3.1.5 | Интегрировать с automation-engine | 6h | P2 |
| 3.1.6 | Создать конфигурацию для провайдеров | 3h | P2 |
| 3.1.7 | Написать тесты | 6h | P2 |
| **Итого** | | **36h** | |

---

### Epic 3.2: Nutrient Deficiency Detector 🟡 ЖЕЛАТЕЛЬНО

**Цель:** Определение дефицита питательных веществ по косвенным признакам.

**Сигнатуры дефицитов:**

```python
class NutrientDeficiencySignatures:
    """
    Сигнатуры дефицитов питательных веществ.
    Основано на анализе трендов pH, EC и паттернов потребления.
    """
    
    SIGNATURES = {
        "NITROGEN": {
            "ph_trend": "rising",           # pH растёт при дефиците N
            "ec_trend": "falling",          # EC падает
            "water_uptake": "decreased",    # Потребление воды снижается
            "ec_correction_frequency": "increased",
            "confidence_weight": 0.7,
        },
        "PHOSPHORUS": {
            "ph_trend": "unstable",
            "ec_trend": "stable",
            "water_uptake": "normal",
            "confidence_weight": 0.5,  # Менее надёжно
        },
        "POTASSIUM": {
            "ph_trend": "rising",
            "ec_trend": "rising",           # EC растёт но растение не потребляет
            "water_uptake": "normal",
            "confidence_weight": 0.6,
        },
        "CALCIUM": {
            "ph_trend": "unstable",
            "ec_trend": "stable",
            "correction_response": "poor",  # pH коррекции менее эффективны
            "confidence_weight": 0.5,
        },
        "MAGNESIUM": {
            "ph_trend": "falling",
            "ec_trend": "stable",
            "confidence_weight": 0.5,
        },
        "IRON": {
            "ph_trend": "high",             # Высокий pH блокирует Fe
            "ec_trend": "normal",
            "confidence_weight": 0.6,
        },
    }
    
    @staticmethod
    def get_recommendation(deficiency: str) -> str:
        recommendations = {
            "NITROGEN": "Increase NPK component ratio or frequency",
            "PHOSPHORUS": "Check phosphorus availability, adjust pH to 6.0-6.5",
            "POTASSIUM": "Increase potassium in nutrient mix",
            "CALCIUM": "Add calcium supplement, check pH stability",
            "MAGNESIUM": "Add Epsom salt (magnesium sulfate)",
            "IRON": "Lower pH or add iron chelate",
        }
        return recommendations.get(deficiency, "Consult agronomist")
```

**Алгоритм определения:**

```python
class NutrientDeficiencyDetector:
    """
    Определение дефицита питательных веществ по косвенным признакам.
    """
    
    async def analyze(self, zone_id: int) -> List[NutrientDeficiency]:
        # Анализ за последние 7 дней
        telemetry = await self.get_telemetry_window(zone_id, days=7)
        corrections = await self.get_correction_history(zone_id, days=7)
        
        # Вычисление трендов
        trends = {
            "ph_trend": self._calculate_trend(telemetry['ph']),
            "ec_trend": self._calculate_trend(telemetry['ec']),
            "water_uptake": self._calculate_water_uptake_trend(telemetry),
            "ec_correction_frequency": len(corrections['ec']) / 7,  # коррекций в день
        }
        
        # Сопоставление с сигнатурами
        deficiencies = []
        for nutrient, signature in NutrientDeficiencySignatures.SIGNATURES.items():
            match_score = self._match_signature(trends, signature)
            
            if match_score > 0.6:  # Порог уверенности
                deficiencies.append(NutrientDeficiency(
                    nutrient=nutrient,
                    probability=match_score * signature["confidence_weight"],
                    recommendation=NutrientDeficiencySignatures.get_recommendation(nutrient),
                    supporting_evidence=self._get_evidence(trends, signature),
                ))
        
        return sorted(deficiencies, key=lambda d: d.probability, reverse=True)
    
    def _match_signature(self, trends: dict, signature: dict) -> float:
        """Calculate match score between observed trends and deficiency signature."""
        matches = 0
        total = 0
        
        for key, expected in signature.items():
            if key == "confidence_weight":
                continue
            
            actual = trends.get(key)
            if actual is None:
                continue
            
            if self._trend_matches(actual, expected):
                matches += 1
            total += 1
        
        return matches / total if total > 0 else 0.0
    
    def _trend_matches(self, actual, expected) -> bool:
        """Check if actual trend matches expected pattern."""
        if expected == "rising":
            return actual > 0.01
        elif expected == "falling":
            return actual < -0.01
        elif expected == "stable":
            return abs(actual) <= 0.01
        elif expected == "unstable":
            return abs(actual) > 0.02
        elif expected == "high":
            return actual > 0.05
        elif expected == "decreased":
            return actual < -0.1
        elif expected == "increased":
            return actual > 0.1
        return False
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 3.2.1 | Определить сигнатуры дефицитов | 6h | P2 |
| 3.2.2 | Реализовать анализ трендов | 6h | P2 |
| 3.2.3 | Реализовать matching алгоритм | 8h | P2 |
| 3.2.4 | Создать модель NutrientDeficiency | 3h | P2 |
| 3.2.5 | Интегрировать с alerts | 4h | P2 |
| 3.2.6 | Создать API endpoints | 4h | P2 |
| 3.2.7 | Написать тесты | 6h | P2 |
| **Итого** | | **37h** | |

---

### Epic 3.3: State-Based Phase Transition 🟠 ВАЖНО

**Цель:** Переход между фазами рецепта на основе состояния растений, а не только времени.

**Модель прогресса:**

```python
class PhaseProgressModel(Enum):
    """Модели прогресса фазы."""
    
    TIME = "time"                                    # Только по времени
    TIME_WITH_TEMP_CORRECTION = "time_with_temp"     # Время с коррекцией по температуре
    GDD = "growing_degree_days"                      # Growing Degree Days
    DLI = "daily_light_integral"                     # Daily Light Integral
    PLANT_STATE = "plant_state"                      # По состоянию растений
    HYBRID = "hybrid"                                # Комбинация факторов
```

**Гибридная модель перехода:**

```python
class HybridPhaseTransition:
    """
    Гибридная модель перехода между фазами.
    Комбинирует несколько факторов для принятия решения.
    """
    
    async def evaluate_transition(
        self, 
        zone_id: int
    ) -> PhaseTransitionAssessment:
        cycle = await self.get_grow_cycle(zone_id)
        current_phase = cycle.current_phase
        
        # 1. Время (базовый фактор)
        time_progress = self._calculate_time_progress(current_phase)
        
        # 2. GDD (Growing Degree Days)
        gdd_progress = await self._calculate_gdd_progress(zone_id, current_phase)
        
        # 3. DLI (Daily Light Integral)
        dli_progress = await self._calculate_dli_progress(zone_id, current_phase)
        
        # 4. Состояние растений (через GrowthStageDetector)
        plant_state = await self.growth_stage_detector.detect_stage(zone_id)
        
        # 5. Состояние раствора
        solution_state = await self._evaluate_solution_state(zone_id)
        
        # Взвешенная оценка
        weights = {
            "time": 0.3,
            "gdd": 0.25,
            "dli": 0.15,
            "plant_state": 0.2,
            "solution_state": 0.1,
        }
        
        progress_scores = {
            "time": time_progress,
            "gdd": gdd_progress,
            "dli": dli_progress,
            "plant_state": plant_state.phase_alignment,
            "solution_state": solution_state.readiness,
        }
        
        overall_progress = sum(
            progress_scores[k] * weights[k] 
            for k in weights
        )
        
        # Решение о переходе
        ready_for_transition = overall_progress >= 0.85
        
        # Определение следующей фазы
        next_phase = self._determine_next_phase(
            current_phase, 
            plant_state.detected_stage
        )
        
        return PhaseTransitionAssessment(
            current_phase=current_phase,
            next_phase=next_phase,
            overall_progress=overall_progress,
            progress_breakdown=progress_scores,
            ready_for_transition=ready_for_transition,
            confidence=self._calculate_confidence(progress_scores),
            recommendation=self._get_recommendation(overall_progress, plant_state),
        )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 3.3.1 | Определить модели прогресса | 3h | P1 |
| 3.3.2 | Реализовать GDD калькулятор | 4h | P1 |
| 3.3.3 | Реализовать DLI калькулятор | 4h | P1 |
| 3.3.4 | Реализовать гибридную модель | 8h | P1 |
| 3.3.5 | Интегрировать с GrowthStageDetector | 4h | P1 |
| 3.3.6 | Создать API endpoints | 4h | P1 |
| 3.3.7 | Обновить Recipe Engine | 6h | P1 |
| 3.3.8 | Написать тесты | 8h | P1 |
| **Итого** | | **41h** | |

---

## Фаза 4: Computer Vision & AI (Месяцы 7-9)

### Epic 4.1: Computer Vision Pipeline 🟢 БУДУЩЕЕ

**Цель:** Анализ изображений для объективной оценки состояния растений.

**Архитектура:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    COMPUTER VISION PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐    │
│   │ IP Camera   │───►│ Frame       │───►│ Preprocessing           │    │
│   │ (RTSP)      │    │ Capture     │    │ • Resize                │    │
│   └─────────────┘    └─────────────┘    │ • Color correction      │    │
│                                         │ • Noise reduction       │    │
│                                         └───────────┬─────────────┘    │
│                                                     │                    │
│                                         ┌───────────▼─────────────┐    │
│                                         │ CV Models              │    │
│                                         │                        │    │
│                                         │ • Plant Detection      │    │
│                                         │ • Health Assessment    │    │
│                                         │ • Disease Detection    │    │
│                                         │ • Growth Stage         │    │
│                                         │ • Fruit Detection      │    │
│                                         └───────────┬─────────────┘    │
│                                                     │                    │
│                                         ┌───────────▼─────────────┐    │
│                                         │ Analysis Engine        │    │
│                                         │                        │    │
│                                         │ • Canopy coverage %    │    │
│                                         │ • Greenness index      │    │
│                                         │ • Leaf area estimate   │    │
│                                         │ • Anomaly regions      │    │
│                                         └───────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Возможности CV:**

```python
class ComputerVisionCapabilities(Enum):
    """Возможности Computer Vision."""
    
    # Детекция
    PLANT_DETECTION = "plant_detection"         # Обнаружение растений
    LEAF_DETECTION = "leaf_detection"           # Обнаружение листьев
    FRUIT_DETECTION = "fruit_detection"         # Обнаружение плодов
    FLOWER_DETECTION = "flower_detection"       # Обнаружение цветов
    
    # Здоровье
    HEALTH_ASSESSMENT = "health_assessment"     # Общая оценка здоровья
    DISEASE_DETECTION = "disease_detection"     # Обнаружение болезней
    PEST_DETECTION = "pest_detection"           # Обнаружение вредителей
    NUTRIENT_ISSUES = "nutrient_issues"         # Признаки дефицита
    
    # Рост
    GROWTH_STAGE = "growth_stage"               # Стадия роста
    CANOPY_COVERAGE = "canopy_coverage"         # Покрытие кроны
    PLANT_HEIGHT = "plant_height"               # Высота растения
    LEAF_AREA = "leaf_area"                     # Площадь листьев
    
    # Зрелость
    RIPENESS_ASSESSMENT = "ripeness"            # Оценка зрелости
    HARVEST_READINESS = "harvest_readiness"     # Готовность к сбору
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 4.1.1 | Проектирование архитектуры CV | 8h | P3 |
| 4.1.2 | Создать frame capture service | 12h | P3 |
| 4.1.3 | Интегрировать YOLO модель | 16h | P3 |
| 4.1.4 | Обучить на custom dataset | 40h | P3 |
| 4.1.5 | Реализовать health assessment | 16h | P3 |
| 4.1.6 | Реализовать disease detection | 20h | P3 |
| 4.1.7 | Создать API endpoints | 8h | P3 |
| 4.1.8 | Интегрировать с automation-engine | 12h | P3 |
| 4.1.9 | Написать тесты | 8h | P3 |
| **Итого** | | **140h** | |

---

### Epic 4.2: Self-Learning Engine 🟢 БУДУЩЕЕ

**Цель:** Самообучение системы на основе исторических данных.

**Механизмы обучения:**

```python
class SelfLearningEngine:
    """
    Движок самообучения системы.
    Анализирует успешные циклы выращивания и оптимизирует параметры.
    """
    
    async def learn_from_cycle(self, cycle_id: int) -> LearningResult:
        """Извлечение уроков из завершённого цикла."""
        cycle = await self.get_grow_cycle(cycle_id)
        
        # Сбор данных цикла
        telemetry = await self.get_cycle_telemetry(cycle_id)
        commands = await self.get_cycle_commands(cycle_id)
        events = await self.get_cycle_events(cycle_id)
        outcomes = await self.get_cycle_outcomes(cycle_id)
        
        # Метрики успеха
        success_metrics = {
            "yield_quality": outcomes.yield_quality,
            "yield_quantity": outcomes.yield_quantity,
            "resource_efficiency": outcomes.resource_efficiency,
            "error_rate": len(events.errors) / cycle.duration_days,
            "target_achievement": self._calculate_target_achievement(telemetry, cycle.targets),
        }
        
        # Определение successful patterns
        if success_metrics["yield_quality"] > 0.8:
            # Этот цикл был успешным - извлечь lessons
            optimal_params = self._extract_optimal_parameters(
                telemetry, commands, cycle
            )
            
            await self.save_lessons(
                plant_type=cycle.plant_type,
                lessons=LearningLessons(
                    optimal_ph_range=optimal_params["ph_range"],
                    optimal_ec_range=optimal_params["ec_range"],
                    optimal_irrigation_interval=optimal_params["irrigation_interval"],
                    effective_correction_strategies=optimal_params["strategies"],
                    success_metrics=success_metrics,
                )
            )
        
        return LearningResult(
            cycle_id=cycle_id,
            success_score=self._calculate_success_score(success_metrics),
            lessons_extracted=True,
            recommendations=self._generate_recommendations(success_metrics),
        )
    
    async def optimize_zone_parameters(
        self, 
        zone_id: int
    ) -> OptimizationResult:
        """Оптимизация параметров на основе накопленных уроков."""
        zone = await self.get_zone(zone_id)
        cycle = await self.get_active_cycle(zone_id)
        
        # Получить уроки для данного типа растения
        lessons = await self.get_lessons(cycle.plant_type)
        
        if not lessons:
            return OptimizationResult(
                status="no_data",
                message="Not enough historical data for optimization"
            )
        
        # ML оптимизация
        optimizer = ParameterOptimizer(lessons)
        optimal_params = optimizer.optimize(
            current_targets=cycle.targets,
            zone_characteristics=zone.settings,
            historical_performance=lessons,
        )
        
        return OptimizationResult(
            status="optimized",
            current_params=cycle.targets,
            suggested_params=optimal_params,
            confidence=optimizer.confidence,
            expected_improvement=optimizer.expected_improvement,
            based_on_cycles=len(lessons.source_cycles),
        )
```

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 4.2.1 | Проектирование модели обучения | 8h | P3 |
| 4.2.2 | Создать Lessons Store | 8h | P3 |
| 4.2.3 | Реализовать extraction алгоритм | 16h | P3 |
| 4.2.4 | Реализовать ParameterOptimizer | 20h | P3 |
| 4.2.5 | Создать feedback loop | 12h | P3 |
| 4.2.6 | Интегрировать с effective-targets | 8h | P3 |
| 4.2.7 | Написать тесты | 8h | P3 |
| **Итого** | | **80h** | |

---

## Фаза 5: Интеграция и оптимизация (Месяцы 10-12)

### Epic 5.1: AI Assistant UI 🟡 ЖЕЛАТЕЛЬНО

**Цель:** Natural language интерфейс для взаимодействия с системой.

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 5.1.1 | Проектирование UI чата | 8h | P2 |
| 5.1.2 | Интеграция с LLM API | 12h | P2 |
| 5.1.3 | Контекстная осведомлённость | 16h | P2 |
| 5.1.4 | Action execution | 16h | P2 |
| 5.1.5 | Обработка ambiguous queries | 12h | P2 |
| 5.1.6 | Написать тесты | 8h | P2 |
| **Итого** | | **72h** | |

---

### Epic 5.2: Mobile Push Notifications 🟡 ЖЕЛАТЕЛЬНО

**Цель:** Push-уведомления о критических событиях.

**Задачи:**

| ID | Задача | Оценка | Приоритет |
|----|--------|--------|-----------|
| 5.2.1 | Интеграция с FCM/APNs | 16h | P2 |
| 5.2.2 | Категоризация уведомлений | 8h | P2 |
| 5.2.3 | Настройка preferences | 8h | P2 |
| 5.2.4 | Silent push для sync | 12h | P2 |
| 5.2.5 | Написать тесты | 8h | P2 |
| **Итого** | | **52h** | |

---

# ЧАСТЬ 4: СВОДНАЯ ТАБЛИЦА РЕСУРСОВ

## 4.1. Общая оценка по фазам

| Фаза | Эпики | Оценка (часы) | Приоритет |
|------|-------|---------------|-----------|
| **Фаза 1: Фундамент** | Auto-Pilot, Auto-Recovery, Anomaly Detection | 151h | 🔴 Критично |
| **Фаза 2: Оптимизация** | Smart Irrigation, Growth Stage, Predictive Maintenance | 126h | 🟠 Важно |
| **Фаза 3: Продвинутая** | Weather, Nutrients, Phase Transition | 114h | 🟡/🟠 |
| **Фаза 4: CV & AI** | Computer Vision, Self-Learning | 220h | 🟢 Будущее |
| **Фаза 5: Интеграция** | AI Assistant, Push Notifications | 124h | 🟡 Желательно |
| **ИТОГО** | | **735h** | |

---

## 4.2. Распределение по приоритетам

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EFFORT vs IMPACT MATRIX                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   IMPACT                                                                │
│   HIGH  │                                                                 │
│         │  ┌────────────────────┐  ┌────────────────────┐              │
│         │  │ P0: Auto-Pilot     │  │ P1: Smart          │              │
│         │  │ Auto-Recovery      │  │ Irrigation         │              │
│         │  │                    │  │ Growth Stage       │              │
│         │  │ 151 hours          │  │ Predictive Maint.  │              │
│         │  └────────────────────┘  │ 126 hours          │              │
│         │                          └────────────────────┘              │
│   MEDIUM│  ┌────────────────────┐  ┌────────────────────┐              │
│         │  │ P2: Weather        │  │ P3: Computer       │              │
│         │  │ Nutrients          │  │ Vision             │              │
│         │  │ Phase Transition   │  │ Self-Learning      │              │
│         │  │ 114 hours          │  │ 220 hours          │              │
│         │  └────────────────────┘  └────────────────────┘              │
│         │                                                                 │
│         └─────────────────────────────────────────────────────────────│
│              LOW                          HIGH                          │
│                         EFFORT                                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# ЧАСТЬ 5: РОЛЛАУТ И РИСКИ

## 5.1. Стратегия роллаута

### Принципы

1. **Incremental Rollout** — каждый эпик разворачивается независимо
2. **Feature Flags** — все новые функции за фича-флагами
3. **Safety First** — критические функции требуют manual approval
4. **Observability** — метрики и логи для всех новых компонентов

### Порядок включения

```
Week 1-2:   Anomaly Detection (read-only, alerting)
Week 3-4:   Auto-Pilot Mode (ASSISTED only)
Week 5-6:   Auto-Recovery (low-severity failures only)
Week 7-8:   Smart Irrigation (with manual confirmation)
Week 9-10:  Growth Stage Detection (informational)
Week 11-12: Predictive Maintenance (alerting)
Week 13+:   Higher autonomy modes based on confidence
```

---

## 5.2. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|----------|
| AI принимает неверные решения | Средняя | Высокое | Safety guardrails, min confidence, human override |
| Ложные срабатывания аномалий | Высокая | Среднее | Tuning thresholds, ML feedback loop |
| Equipment failure during auto-recovery | Низкая | Высокое | Fallback procedures, manual escalation |
| Performance degradation | Средняя | Среднее | Profiling, optimization, resource limits |
| Integration bugs | Высокая | Среднее | Comprehensive testing, staged rollout |
| Data quality issues | Средняя | Высокое | Validation, anomaly detection on input |

---

# ЧАСТЬ 6: КРИТЕРИИ УСПЕХА

## 6.1. KPI для "Посадил и забыл"

### Операционные метрики

| Метрика | Текущее | Цель (6 мес) | Цель (12 мес) |
|---------|---------|--------------|---------------|
| Время без вмешательства человека | ~1 день | 1 неделя | 2 недели |
| Автоматическое восстановление после сбоев | 0% | 50% | 80% |
| Точность определения стадии роста | N/A | 70% | 85% |
| Предотвращённые отказы оборудования | 0 | 5+ | 20+ |
| Оптимизация потребления воды | Baseline | -10% | -20% |

### Качественные показатели

- ✅ Система автоматически корректирует pH/EC без вмешательства
- ✅ Автоматическое восстановление после offline нод
- ✅ Адаптивный полив на основе условий
- ✅ Заблаговременные уведомления о проблемах оборудования
- ✅ Рекомендации по оптимизации на основе истории

---

# ЧАСТЬ 7: ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ

## 7.1. Новые таблицы БД

```sql
-- AI решения
CREATE TABLE ai_decisions (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    decision_type VARCHAR(64) NOT NULL,
    decision_data JSONB NOT NULL,
    confidence DECIMAL(5,4),
    status VARCHAR(32) DEFAULT 'pending',  -- pending/approved/rejected/executed
    auto_approved BOOLEAN DEFAULT FALSE,
    approved_by BIGINT REFERENCES users(id),
    approved_at TIMESTAMP,
    executed_at TIMESTAMP,
    outcome JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Процедуры восстановления
CREATE TABLE recovery_events (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    node_uid VARCHAR(64),
    failure_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    recovery_procedure VARCHAR(64),
    recovery_status VARCHAR(32),
    recovery_steps JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Аномалии
CREATE TABLE detected_anomalies (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    anomaly_type VARCHAR(64) NOT NULL,
    metric VARCHAR(32),
    severity VARCHAR(32) NOT NULL,
    confidence DECIMAL(5,4),
    details JSONB,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Прогнозы оборудования
CREATE TABLE equipment_predictions (
    id BIGSERIAL PRIMARY KEY,
    node_uid VARCHAR(64) NOT NULL,
    component VARCHAR(64),
    health_score DECIMAL(5,2),
    predicted_failure_type VARCHAR(64),
    probability DECIMAL(5,4),
    estimated_days INT,
    recommended_action TEXT,
    valid_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Уроки обучения
CREATE TABLE learning_lessons (
    id BIGSERIAL PRIMARY KEY,
    plant_type VARCHAR(64),
    lesson_type VARCHAR(64),
    lesson_data JSONB NOT NULL,
    success_score DECIMAL(5,4),
    source_cycle_ids BIGINT[],
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- История оптимизаций
CREATE TABLE parameter_optimizations (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    cycle_id BIGINT REFERENCES grow_cycles(id),
    parameter VARCHAR(64) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    reason VARCHAR(255),
    confidence DECIMAL(5,4),
    outcome_score DECIMAL(5,4),
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 7.2. Новые переменные окружения

```bash
# Auto-Pilot
AUTO_PILOT_DEFAULT_MODE=assisted           # off|assisted|supervised|autonomous
AUTO_PILOT_MIN_CONFIDENCE=0.85
AUTO_PILOT_ENABLED=true

# Safety Limits
SAFETY_MAX_PH_DOSE_ML_PER_HOUR=5.0
SAFETY_MAX_EC_DOSE_ML_PER_HOUR=20.0
SAFETY_MAX_IRRIGATION_ADJUSTMENT_PCT=30

# Anomaly Detection
ANOMALY_DETECTION_ENABLED=true
ANOMALY_STUCK_VALUE_THRESHOLD=0.0001
ANOMALY_SPIKE_ZSCORE_THRESHOLD=3.0
ANOMALY_CHECK_INTERVAL_SEC=300

# Predictive Maintenance
PREDICTIVE_MAINTENANCE_ENABLED=true
PREDICTIVE_MAINTENANCE_WINDOW_DAYS=30
PREDICTIVE_MAINTENANCE_CHECK_INTERVAL_SEC=3600

# Weather Integration
WEATHER_PROVIDER=openweathermap
WEATHER_API_KEY=
WEATHER_CACHE_TTL_SEC=3600
WEATHER_ADAPTATION_ENABLED=true

# Computer Vision
CV_ENABLED=false
CV_CAPTURE_INTERVAL_SEC=300
CV_MODEL_PATH=/models/yolo_plants.pt

# Self-Learning
SELF_LEARNING_ENABLED=true
SELF_LEARNING_MIN_CYCLES=5
SELF_LEARNING_MIN_SUCCESS_RATE=0.7
```

---

## 7.3. Новые API endpoints

```
# Auto-Pilot
POST   /api/zones/{id}/auto-pilot/mode
GET    /api/zones/{id}/auto-pilot/status
POST   /api/zones/{id}/auto-pilot/decisions
GET    /api/zones/{id}/auto-pilot/decisions
POST   /api/zones/{id}/auto-pilot/decisions/{decision_id}/approve
POST   /api/zones/{id}/auto-pilot/decisions/{decision_id}/reject

# Anomaly Detection
GET    /api/zones/{id}/anomalies
GET    /api/zones/{id}/anomalies/active
POST   /api/zones/{id}/anomalies/{anomaly_id}/resolve

# Predictive Maintenance
GET    /api/nodes/{uid}/health-prediction
GET    /api/zones/{id}/equipment-health
POST   /api/nodes/{uid}/maintenance-schedule

# Growth Stage
GET    /api/zones/{id}/growth-stage
GET    /api/zones/{id}/phase-progress

# Smart Irrigation
GET    /api/zones/{id}/irrigation-optimization
POST   /api/zones/{id}/irrigation-optimization/apply

# Weather
GET    /api/weather/current
GET    /api/weather/forecast
GET    /api/zones/{id}/weather-adjustments

# Computer Vision
POST   /api/zones/{id}/cv/analyze
GET    /api/zones/{id}/cv/health-assessment
GET    /api/zones/{id}/cv/growth-analysis

# Self-Learning
GET    /api/zones/{id}/optimization-suggestions
POST   /api/zones/{id}/optimization-suggestions/{id}/apply
GET    /api/lessons/{plant_type}
```

---

# ЧАСТЬ 8: ЗАКЛЮЧЕНИЕ

## 8.1. Критический путь

```
Month 1-2:  [Auto-Pilot Mode] + [Auto-Recovery] + [Anomaly Detection]
                    ↓
Month 3-4:  [Smart Irrigation] + [Growth Stage] + [Predictive Maintenance]
                    ↓
Month 5-6:  [Weather Integration] + [Nutrient Detection] + [Phase Transition]
                    ↓
Month 7-9:  [Computer Vision] + [Self-Learning]
                    ↓
Month 10-12: [AI Assistant] + [Push Notifications] + [Integration]
```

## 8.2. Минимальный жизнеспособный продукт (MVP)

Для базовой автономности "посадил и забыл" на 1 неделю:

- ✅ Auto-Pilot Mode (ASSISTED/SUPERVISED)
- ✅ Auto-Recovery для NODE_OFFLINE и SENSOR_FAILURE
- ✅ Anomaly Detection для pH/EC
- ✅ Smart Irrigation с базовыми факторами

**Оценка MVP:** ~150 часов (Фаза 1)

## 8.3. Следующие шаги

1. **Review** — ревью плана с командой
2. **Prioritize** — выбор эпиков для первого спринта
3. **Setup** — создание веток, настройка CI/CD
4. **Implement** — реализация по эпикам
5. **Test** — интеграционное тестирование
6. **Deploy** — staged rollout с feature flags

---

**Документ создан:** 2026-02-16  
**Автор:** AI Assistant  
**Версия:** 1.0