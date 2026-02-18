# MEGA_PLAN_PLANT_AND_FORGET.md
# Мега-план доработки системы до концепции "Посадил и забыл"
# Hydro 2.0 — Автономная система управления гидропонной теплицей

**Дата создания:** 2026-02-16
**Статус:** План развития
**Версия:** 1.0

---

## 0. Введение: Концепция "Посадил и забыл"

### 0.1. Видение

**"Посадил и забыл"** — это когда пользователь:
1. Создаёт цикл выращивания (выбирает зону, растение, рецепт)
2. Система **автономно** управляет всем процессом до harvest
3. Пользователь получает уведомления только о критических событиях или для подтверждения harvest

### 0.2. Текущее состояние vs Целевое

| Аспект | Текущее (2026-02-16) | Целевое ("Посадил и забыл") |
|--------|---------------------|----------------------------|
| pH/EC коррекция | ✅ Автоматическая | ✅ Автоматическая |
| Климат-контроль | ✅ Автоматический | ✅ Автоматический + predictive |
| Освещение | ✅ По расписанию | ✅ Адаптивное + DLI tracking |
| Полив | ✅ По расписанию/субстрату | ✅ Адаптивный + AI-оптимизация |
| AI рекомендации | ⚠️ Только рекомендации | ✅ **Авто-применение** (с ограничениями) |
| Digital Twin | ⚠️ Симуляция offline | ✅ **Online prediction** + proactive |
| Прогнозирование | ❌ Нет | ✅ Прогноз отклонений за 1-3 часа |
| Авто-адаптация рецептов | ❌ Нет | ✅ ML-based адаптация |
| Обнаружение болезней | ❌ Нет | ✅ Computer Vision (камеры) |
| Интеграция погоды | ❌ Нет | ✅ Proactive climate adjustment |
| Autonomous mode | ⚠️ Частичный | ✅ Полный с graceful degradation |

### 0.3. Ключевые принципы

1. **Safety First** — система никогда не применяет изменения, которые могут навредить
2. **Graceful Degradation** — при ошибках система деградирует безопасно
3. **Human in the Loop** — критические решения требуют подтверждения
4. **Transparency** — все действия логируются и объяснимы
5. **Progressive Autonomy** — уровни автономности настраиваемые

---

## 1. Архитектура "Autonomous Greenhouse"

### 1.1. Слои автономности

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYER 5: ORCHESTRATION                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Autonomous Orchestrator                       │   │
│  │  • Управление циклом жизни растения от seedling до harvest      │   │
│  │  • Координация всех subsystems                                   │   │
│  │  • Decision making на основе агрегированных данных              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYER 4: AI INTELLIGENCE                             │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐        │
│  │  Prediction      │ │  Anomaly         │ │  Optimization    │        │
│  │  Engine          │ │  Detection       │ │  Engine          │        │
│  │  • pH/EC trends  │ │  • Sensor drift  │ │  • Irrigation    │        │
│  │  • Climate       │ │  • Equipment     │ │  • Energy        │        │
│  │  • Growth        │ │  • Disease risk  │ │  • Nutrients     │        │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYER 3: DIGITAL TWIN                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    Real-time Simulation                          │   │
│  │  • Mirror состояния зоны в реальном времени                      │   │
│  │  • What-if scenarios для предсказаний                            │   │
│  │  • Model calibration по историческим данным                      │   │
│  │  • Plant growth model (сухая масса, DLI, VPD)                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYER 2: CONTROL LOOPS (СУЩЕСТВУЕТ)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ pH Controller│ │ EC Controller│ │ Climate Ctrl │ │ Irrigation   │  │
│  │ (PID + SM)   │ │ (PID + SM)   │ │ (PID + SM)   │ │ Controller   │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAYER 1: HARDWARE (СУЩЕСТВУЕТ)                       │
│  ESP32 Nodes → MQTT → Python Services → PostgreSQL → Laravel → Vue     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Фаза 1: Predictive Analytics (Приоритет: ВЫСОКИЙ)

### 2.1. Prediction Engine

**Цель:** Предсказывать отклонения параметров за 1-3 часа.

**Компоненты:**

#### 2.1.1. Trend Analysis Service

```
Файл: backend/services/automation-engine/services/prediction/
├── trend_analyzer.py
├── ph_predictor.py
├── ec_predictor.py
├── climate_predictor.py
└── prediction_models.py
```

**Алгоритмы:**
- Exponential Weighted Moving Average (EWMA)
- Linear/Polynomial Regression для трендов
- Seasonal decomposition (суточные циклы)
- LSTM/Transformer для сложных паттернов (опционально)

**API:**
```python
class PredictionEngine:
    async def predict_ph(zone_id: int, horizon_hours: float = 3.0) -> Prediction:
        """
        Предсказать pH на horizon_hours вперёд.
        
        Returns:
            Prediction(
                current_value=5.9,
                predicted_value=6.3,
                predicted_at=datetime(...),
                confidence=0.85,
                trend="increasing",
                slope=0.15,  # pH/hour
                will_exceed_target=True,
                time_to_target_violation=timedelta(hours=2.1)
            )
        """
        
    async def predict_ec(zone_id: int, horizon_hours: float = 3.0) -> Prediction: ...
    async def predict_temp_air(zone_id: int, horizon_hours: float = 3.0) -> Prediction: ...
    async def predict_vpd(zone_id: int, horizon_hours: float = 3.0) -> Prediction: ...
```

**Интеграция с automation-engine:**
```python
# В ZoneAutomationService.process_zone()
async def process_zone(self, zone_id: int):
    # 1. Получить текущую телеметрию
    telemetry = await self.telemetry_repo.get_last_telemetry(zone_id)
    
    # 2. Получить предсказания
    predictions = await self.prediction_engine.get_predictions(zone_id)
    
    # 3. Proactive actions
    if predictions.ph.will_exceed_target:
        # Предотвратить отклонение ДО того, как оно произойдёт
        await self.proactive_ph_correction(zone_id, predictions.ph)
```

### 2.1.2. Proactive Correction Policy

**Новая политика в domain/policies/:**

```python
class ProactiveCorrectionPolicy:
    """
    Политика proactive коррекции на основе предсказаний.
    
    Логика:
    - Если predicted_value выйдет за target через < 30 мин → корректировать сейчас
    - Если confidence < 0.7 → ждать и наблюдать
    - Если предыдущие предсказания были неточны → увеличить threshold
    """
    
    def should_correct_proactively(
        self,
        prediction: Prediction,
        target: TargetRange,
        history: PredictionHistory
    ) -> ProactiveDecision:
        
        # Time-based decision
        if prediction.time_to_violation > timedelta(minutes=30):
            return ProactiveDecision(action="wait", reason="violation_too_far")
        
        # Confidence-based decision
        if prediction.confidence < 0.7:
            return ProactiveDecision(action="wait", reason="low_confidence")
        
        # Historical accuracy check
        accuracy = history.get_accuracy_for_horizon(prediction.horizon_hours)
        if accuracy < 0.6:
            return ProactiveDecision(action="wait", reason="historical_inaccuracy")
        
        # Proactive correction approved
        dose = self.calculate_proactive_dose(prediction, target)
        return ProactiveDecision(
            action="correct",
            dose_ml=dose,
            reason=f"predicted_{prediction.trend}",
            confidence=prediction.confidence
        )
```

### 2.1.3. Модели Digital Twin

**Расширение models.py:**

```python
class EnhancedPHModel(PHModel):
    """
    Расширенная модель pH с поддержкой:
    - Калибровки по историческим данным
    - Учёта внешних факторов (температура, CO2)
    - Plant uptake dynamics
    """
    
    def __init__(self, params: Optional[Dict] = None):
        super().__init__(params)
        self.plant_uptake_rate = params.get("plant_uptake_rate", 0.005)
        self.temp_coefficient = params.get("temp_coefficient", 0.015)
        
    def predict(self, current_state: ZoneState, horizon_hours: float) -> float:
        """
        Предсказать pH через horizon_hours.
        
        Учитывает:
        - Естественный дрифт
        - Plant uptake (растения потребляют нитраты → pH растёт)
        - Температуру (влияет на буферность)
        - Историю коррекций
        """
        # ...

class PlantGrowthModel:
    """
    Модель роста растения.
    
    Предсказывает:
    - Сухую массу растения
    - Потребление питательных веществ
    - Потребление воды
    - DLI requirements
    """
    
    def predict_daily_nutrient_uptake(
        self,
        plant_age_days: int,
        current_biomass_g: float,
        conditions: EnvironmentalConditions
    ) -> NutrientUptake:
        """
        Предсказать суточное потребление N-P-K-Ca-Mg.
        
        Returns:
            NutrientUptake(
                nitrogen_mg=150.0,
                phosphorus_mg=30.0,
                potassium_mg=200.0,
                calcium_mg=80.0,
                magnesium_mg=40.0,
                water_ml=1200.0
            )
        """
```

---

## 3. Фаза 2: Autonomous Decision Making (Приоритет: ВЫСОКИЙ)

### 3.1. Autonomous Action Framework

**Новый сервис: autonomous-agent**

```
backend/services/autonomous-agent/
├── main.py
├── decision_engine.py
├── action_executor.py
├── safety_guard.py
├── constraint_checker.py
├── approval_manager.py
└── models.py
```

### 3.2. Уровни автономности

```typescript
interface AutonomyLevel {
  level: 0 | 1 | 2 | 3 | 4 | 5;
  name: string;
  description: string;
  actions_allowed: string[];
  requires_approval: boolean;
}

const AUTONOMY_LEVELS: AutonomyLevel[] = [
  {
    level: 0,
    name: "MANUAL",
    description: "Все действия требуют ручного подтверждения",
    actions_allowed: [],
    requires_approval: true
  },
  {
    level: 1,
    name: "ASSISTED",
    description: "Автоматические коррекции pH/EC, остальное вручную",
    actions_allowed: ["ph_correction", "ec_correction"],
    requires_approval: false
  },
  {
    level: 2,
    name: "SEMIAUTONOMOUS",
    description: "Автоматические коррекции + адаптивный полив",
    actions_allowed: ["ph_correction", "ec_correction", "irrigation_adjustment", "lighting_adjustment"],
    requires_approval: false
  },
  {
    level: 3,
    name: "AUTONOMOUS",
    description: "Полная автоматизация, критические изменения требуют подтверждения",
    actions_allowed: ["ph_correction", "ec_correction", "irrigation_adjustment", 
                      "lighting_adjustment", "climate_adjustment", "recipe_minor_tweak"],
    requires_approval: false  // кроме критических
  },
  {
    level: 4,
    name: "HIGHLY_AUTONOMOUS",
    description: "Полная автоматизация включая recipe adaptations",
    actions_allowed: ["ph_correction", "ec_correction", "irrigation_adjustment",
                      "lighting_adjustment", "climate_adjustment", "recipe_adaptation",
                      "phase_transition"],
    requires_approval: false  // кроме harvest
  },
  {
    level: 5,
    name: "FULLY_AUTONOMOUS",
    description: "Полная автономность включая harvest",
    actions_allowed: ["*"],
    requires_approval: false
  }
];
```

### 3.3. Decision Engine

```python
class AutonomousDecisionEngine:
    """
    Центральный движок принятия автономных решений.
    
    Интегрирует:
    - Predictions (что произойдёт)
    - Current State (текущее состояние)
    - Constraints (ограничения)
    - Safety Rules (правила безопасности)
    - User Preferences (предпочтения пользователя)
    """
    
    def __init__(self):
        self.prediction_engine = PredictionEngine()
        self.safety_guard = SafetyGuard()
        self.constraint_checker = ConstraintChecker()
        self.approval_manager = ApprovalManager()
        
    async def evaluate_and_act(self, zone_id: int) -> AutonomousDecision:
        """
        Оценить состояние зоны и выполнить автономные действия.
        """
        # 1. Собрать контекст
        context = await self.gather_context(zone_id)
        
        # 2. Получить предсказания
        predictions = await self.prediction_engine.get_all_predictions(zone_id)
        
        # 3. Оценить риски
        risks = await self.assess_risks(context, predictions)
        
        # 4. Сгенерировать возможные действия
        actions = await self.generate_actions(context, predictions, risks)
        
        # 5. Отфильтровать по безопасности
        safe_actions = await self.safety_guard.filter_safe_actions(
            actions, 
            context,
            zone_constraints=context.constraints
        )
        
        # 6. Отфильтровать по уровню автономности
        allowed_actions = self.filter_by_autonomy_level(
            safe_actions, 
            context.autonomy_level
        )
        
        # 7. Выполнить действия или запросить подтверждение
        results = []
        for action in allowed_actions:
            if action.requires_approval:
                result = await self.request_approval(action, context)
            else:
                result = await self.execute_action(action, context)
            results.append(result)
            
        return AutonomousDecision(
            zone_id=zone_id,
            actions=results,
            pending_approvals=self.approval_manager.get_pending(zone_id)
        )
```

### 3.4. Safety Guard

```python
class SafetyGuard:
    """
    Предотвращает опасные автономные действия.
    
    Правила:
    - Never exceed max_dose_per_hour
    - Never dose if sensor is stale
    - Never dose if previous dose pending
    - Never apply major changes without human confirmation
    - Never continue if anomaly detected
    """
    
    HARD_LIMITS = {
        "ph": {
            "max_dose_ml_per_hour": 10.0,
            "min_interval_sec": 300,
            "max_change_per_hour": 0.5,
            "emergency_stop_threshold": 1.0,  # pH change in 1 hour
        },
        "ec": {
            "max_dose_ml_per_hour": 50.0,
            "min_interval_sec": 600,
            "max_change_per_hour": 0.5,
        },
        "irrigation": {
            "max_duration_sec": 3600,
            "min_interval_sec": 1800,
        }
    }
    
    async def filter_safe_actions(
        self,
        actions: List[Action],
        context: ZoneContext,
        zone_constraints: Dict
    ) -> List[Action]:
        """Отфильтровать действия по правилам безопасности."""
        safe = []
        
        for action in actions:
            # Проверка свежести телеметрии
            if not self._is_telemetry_fresh(context, action):
                logger.warning(f"Action {action} rejected: stale telemetry")
                continue
                
            # Проверка hard limits
            if not self._check_hard_limits(action, context):
                logger.warning(f"Action {action} rejected: hard limit violation")
                continue
                
            # Проверка предыдущих дозировок
            if not self._check_dose_history(action, context):
                logger.warning(f"Action {action} rejected: dose history violation")
                continue
                
            # Проверка на аномалии
            if context.has_anomalies:
                logger.warning(f"Action {action} rejected: anomalies detected")
                continue
            
            # Проверка constraint checker
            violations = await self.constraint_checker.check(action, zone_constraints)
            if violations:
                logger.warning(f"Action {action} rejected: constraint violations: {violations}")
                continue
                
            safe.append(action)
            
        return safe
```

### 3.5. Approval Manager

```python
class ApprovalManager:
    """
    Управление запросами на подтверждение автономных действий.
    
    Каналы уведомлений:
    - Push (WebSocket)
    - Mobile App (FCM/APNs)
    - Email (для критических)
    - Telegram (опционально)
    """
    
    async def request_approval(
        self,
        action: Action,
        context: ZoneContext,
        timeout_minutes: int = 30
    ) -> ApprovalResult:
        """
        Запросить подтверждение действия у пользователя.
        """
        request = ApprovalRequest(
            id=generate_uuid(),
            zone_id=context.zone_id,
            action=action,
            reason=action.reason,
            predicted_outcome=action.predicted_outcome,
            risk_level=action.risk_level,
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=timeout_minutes),
            status="pending"
        )
        
        # Сохранить в БД
        await self.save_request(request)
        
        # Отправить уведомление
        await self.notify_user(request)
        
        # Ждать подтверждения или timeout
        result = await self.wait_for_approval(request.id, timeout_minutes)
        
        return result
```

---

## 4. Фаза 3: Adaptive Recipe Optimization (Приоритет: СРЕДНИЙ)

### 4.1. Recipe Adaptation Engine

**Цель:** Автоматически адаптировать рецепт на основе наблюдений.

**Таблица для хранения адаптаций:**

```sql
CREATE TABLE recipe_adaptations (
    id BIGSERIAL PRIMARY KEY,
    grow_cycle_id BIGINT REFERENCES grow_cycles(id),
    phase_id BIGINT REFERENCES grow_cycle_phases(id),
    
    -- Что адаптируем
    adaptation_type VARCHAR NOT NULL,  -- ph_target, ec_target, irrigation_interval, etc.
    
    -- Изменения
    original_value DECIMAL,
    adapted_value DECIMAL,
    adaptation_reason TEXT,
    
    -- Контекст
    trigger_event VARCHAR,  -- prediction_violation, observation, user_request
    confidence DECIMAL(5,4),
    
    -- Результат
    outcome VARCHAR,  -- success, failure, reverted
    outcome_details JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    INDEX (grow_cycle_id, created_at)
);
```

### 4.2. Adaptation Rules

```python
class RecipeAdaptationEngine:
    """
    Автоматическая адаптация параметров рецепта.
    
    Принципы:
    - Малые изменения (incremental adaptation)
    - Откат при негативных результатах
    - Логирование всех изменений
    - Требует подтверждения для значительных изменений
    """
    
    ADAPTATION_RULES = {
        "ph_target": {
            "max_change_per_day": 0.2,
            "min_observation_period_hours": 24,
            "trigger_conditions": [
                "consistent_correction_needed",
                "plant_stress_detected",
            ],
            "requires_approval": False,  # малые изменения
        },
        "ec_target": {
            "max_change_per_day": 0.15,
            "min_observation_period_hours": 48,
            "trigger_conditions": [
                "nutrient_deficiency_symptoms",
                "nutrient_toxicity_symptoms",
            ],
            "requires_approval": True,  // требует подтверждения
        },
        "irrigation_interval": {
            "max_change_per_day": 0.2,  # 20% изменения
            "min_observation_period_hours": 12,
            "trigger_conditions": [
                "substrate_moisture_consistently_high",
                "substrate_moisture_consistently_low",
            ],
            "requires_approval": False,
        }
    }
    
    async def evaluate_adaptation_needs(
        self,
        zone_id: int,
        observation_period_hours: int = 24
    ) -> List[AdaptationSuggestion]:
        """
        Оценить необходимость адаптации параметров.
        """
        suggestions = []
        
        # Анализ pH
        ph_analysis = await self.analyze_ph_patterns(zone_id, observation_period_hours)
        if ph_analysis.consistent_correction_needed:
            suggestions.append(AdaptationSuggestion(
                parameter="ph_target",
                current_value=ph_analysis.current_target,
                suggested_value=ph_analysis.optimal_target,
                reason="consistent_ph_correction_pattern",
                confidence=ph_analysis.confidence,
                requires_approval=self.ADAPTATION_RULES["ph_target"]["requires_approval"]
            ))
        
        # Анализ irrigation
        irrigation_analysis = await self.analyze_irrigation_patterns(zone_id, observation_period_hours)
        if irrigation_analysis.overwatering_detected:
            suggestions.append(AdaptationSuggestion(
                parameter="irrigation_interval",
                current_value=irrigation_analysis.current_interval,
                suggested_value=irrigation_analysis.optimal_interval,
                reason="substrate_moisture_consistently_high",
                confidence=irrigation_analysis.confidence,
                requires_approval=False
            ))
        
        return suggestions
    
    async def apply_adaptation(
        self,
        adaptation: AdaptationSuggestion,
        zone_id: int
    ) -> AdaptationResult:
        """
        Применить адаптацию (автоматически или через подтверждение).
        """
        # Проверить правила
        rule = self.ADAPTATION_RULES[adaptation.parameter]
        
        # Проверить максимальное изменение
        max_change = rule["max_change_per_day"]
        relative_change = abs(adaptation.suggested_value - adaptation.current_value) / adaptation.current_value
        
        if relative_change > max_change:
            # Ограничить изменение
            adaptation.suggested_value = adaptation.current_value * (1 + max_change)
            logger.info(f"Adaptation limited to max_change_per_day: {adaptation}")
        
        # Проверить период наблюдения
        if not await self._has_sufficient_observation(zone_id, rule["min_observation_period_hours"]):
            logger.warning(f"Insufficient observation period for {adaptation.parameter}")
            return AdaptationResult(status="deferred", reason="insufficient_observation")
        
        # Применить или запросить подтверждение
        if adaptation.requires_approval:
            result = await self.approval_manager.request_approval(adaptation, zone_id)
        else:
            result = await self._apply_autonomous(adaptation, zone_id)
        
        return result
```

---

## 5. Фаза 4: Anomaly Detection & Diagnostics (Приоритет: ВЫСОКИЙ)

### 5.1. Anomaly Detection Service

**Новый сервис: anomaly-detector**

```
backend/services/anomaly-detector/
├── main.py
├── detectors/
│   ├── sensor_anomaly_detector.py
│   ├── equipment_anomaly_detector.py
│   ├── plant_stress_detector.py
│   └── systemic_anomaly_detector.py
├── models.py
└── alerting.py
```

### 5.2. Типы аномалий

```python
class AnomalyType(Enum):
    # Sensor anomalies
    SENSOR_STUCK = "sensor_stuck"           # Значение не меняется
    SENSOR_SPIKE = "sensor_spike"           # Резкий скачок
    SENSOR_DRIFT = "sensor_drift"           # Постепенный дрифт
    SENSOR_NOISE = "sensor_noise"           # Чрезмерный шум
    SENSOR_DISCONNECTED = "sensor_disconnected"
    
    # Equipment anomalies
    PUMP_NOT_FLOWING = "pump_not_flowing"   # Насос включён, потока нет
    PUMP_SLOW_RESPONSE = "pump_slow_response"
    VALVE_STUCK = "valve_stuck"
    LIGHT_OUTPUT_DROP = "light_output_drop"
    
    # Plant stress
    PLANT_STRESS_PH = "plant_stress_ph"
    PLANT_STRESS_EC = "plant_stress_ec"
    PLANT_STRESS_VPD = "plant_stress_vpd"
    PLANT_STRESS_TEMP = "plant_stress_temp"
    
    # Systemic
    CORRECTION_INEFFECTIVE = "correction_ineffective"
    CONTINUOUS_CORRECTION = "continuous_correction"
    TARGET_UNREACHABLE = "target_unreachable"

class AnomalyDetector:
    """
    Детекция аномалий в реальном времени.
    """
    
    async def detect_sensor_anomalies(
        self,
        zone_id: int,
        telemetry_history: List[TelemetrySample]
    ) -> List[Anomaly]:
        """Детекция аномалий сенсоров."""
        anomalies = []
        
        # Проверка stuck sensor
        if self._is_sensor_stuck(telemetry_history):
            anomalies.append(Anomaly(
                type=AnomalyType.SENSOR_STUCK,
                severity="warning",
                message="Sensor value has not changed in 30 minutes",
                recommended_action="check_sensor_or_calibration"
            ))
        
        # Проверка spike
        if self._detect_spike(telemetry_history):
            anomalies.append(Anomaly(
                type=AnomalyType.SENSOR_SPIKE,
                severity="warning",
                message="Sudden value spike detected",
                recommended_action="verify_reading"
            ))
        
        # Проверка noise
        noise_level = self._calculate_noise_level(telemetry_history)
        if noise_level > self.NOISE_THRESHOLD:
            anomalies.append(Anomaly(
                type=AnomalyType.SENSOR_NOISE,
                severity="info",
                message=f"High sensor noise: {noise_level}",
                recommended_action="check_cabling_or_emi"
            ))
        
        return anomalies
    
    async def detect_equipment_anomalies(
        self,
        zone_id: int,
        command_history: List[Command],
        telemetry: Telemetry
    ) -> List[Anomaly]:
        """Детекция аномалий оборудования."""
        anomalies = []
        
        # Проверка pump flow
        recent_pump_commands = [c for c in command_history if c.channel == "pump_in"]
        for cmd in recent_pump_commands:
            if cmd.status == "executed" and cmd.params.get("state") == "on":
                # Насос включён, проверяем поток
                flow = telemetry.get("flow_rate", 0)
                if flow == 0:
                    anomalies.append(Anomaly(
                        type=AnomalyType.PUMP_NOT_FLOWING,
                        severity="critical",
                        message="Pump is on but no flow detected",
                        recommended_action="check_pump_or_flow_sensor",
                        affected_node=cmd.node_uid
                    ))
        
        return anomalies
    
    async def detect_plant_stress(
        self,
        zone_id: int,
        context: ZoneContext
    ) -> List[Anomaly]:
        """Детекция стресса растений."""
        anomalies = []
        
        # VPD stress
        vpd = self._calculate_vpd(
            context.temp_air, 
            context.humidity,
            context.temp_leaf  # предполагаем leaf temp = air temp - 2°C
        )
        if vpd < 0.4 or vpd > 1.6:
            anomalies.append(Anomaly(
                type=AnomalyType.PLANT_STRESS_VPD,
                severity="warning" if vpd < 2.0 else "critical",
                message=f"VPD out of optimal range: {vpd:.2f} kPa",
                recommended_action="adjust_humidity_or_temperature"
            ))
        
        return anomalies
```

### 5.3. Automatic Response to Anomalies

```python
class AnomalyResponseEngine:
    """
    Автоматический ответ на аномалии.
    """
    
    RESPONSE_ACTIONS = {
        AnomalyType.SENSOR_STUCK: [
            {"action": "use_backup_sensor", "params": {}},
            {"action": "disable_automatic_control", "params": {"metric": "auto"}},
            {"action": "alert_user", "params": {"severity": "warning"}},
        ],
        AnomalyType.PUMP_NOT_FLOWING: [
            {"action": "stop_pump", "params": {}},
            {"action": "check_alternate_pump", "params": {}},
            {"action": "alert_user", "params": {"severity": "critical"}},
        ],
        AnomalyType.PLANT_STRESS_VPD: [
            {"action": "adjust_humidity", "params": {"mode": "auto"}},
            {"action": "adjust_temperature", "params": {"mode": "auto"}},
        ],
    }
    
    async def respond(self, anomaly: Anomaly, context: ZoneContext) -> ResponseResult:
        """Выполнить автоматический ответ на аномалию."""
        actions = self.RESPONSE_ACTIONS.get(anomaly.type, [])
        
        results = []
        for action_def in actions:
            action = Action(
                type=action_def["action"],
                params=action_def["params"],
                reason=f"anomaly_response:{anomaly.type.value}",
                priority=anomaly.severity
            )
            
            result = await self.execute_action(action, context)
            results.append(result)
            
            # Если действие успешно и аномалия устранена — остановиться
            if result.success and anomaly.resolved:
                break
        
        return ResponseResult(
            anomaly_id=anomaly.id,
            actions_executed=results,
            resolved=anomaly.resolved
        )
```

---

## 6. Фаза 5: External Data Integration (Приоритет: СРЕДНИЙ)

### 6.1. Weather Integration

**Цель:** Адаптировать климат-контроль на основе прогноза погоды.

```
backend/services/weather-integration/
├── main.py
├── providers/
│   ├── openweathermap_provider.py
│   ├── weatherapi_provider.py
│   └── local_weather_station.py
├── climate_adapter.py
└── models.py
```

### 6.2. Weather-Aware Climate Control

```python
class WeatherAwareClimateController:
    """
    Климат-контроль с учётом погоды.
    
    Использует:
    - Текущую погоду (температура, влажность, облачность)
    - Прогноз на 24-48 часов
    - Sunrise/sunset для адаптации освещения
    """
    
    async def adjust_for_weather(
        self,
        zone_id: int,
        weather: WeatherData,
        forecast: List[WeatherForecast]
    ) -> List[Action]:
        """Адаптировать климат-контроль под погоду."""
        actions = []
        
        # Предсказать влияние внешней температуры
        if weather.outside_temp > 30:
            # Жарко снаружи — prepare cooling
            actions.append(Action(
                type="pre_cool",
                params={"target_temp": 22.0},
                reason="hot_weather_forecast"
            ))
        
        if weather.humidity > 80:
            # Высокая влажность снаружи — подготовить dehumidification
            actions.append(Action(
                type="reduce_humidity",
                params={"target_rh": 55.0},
                reason="high_external_humidity"
            ))
        
        # Адаптировать освещение под облачность
        if weather.cloudiness > 70:
            # Пасмурно — увеличить искусственное освещение
            actions.append(Action(
                type="increase_light",
                params={"brightness": 100},
                reason="cloudy_weather"
            ))
        
        return actions
```

---

## 7. Фаза 6: Computer Vision (Приоритет: НИЗКИЙ, долгосрочная)

### 7.1. Plant Vision Service

**Цель:** Автоматическое обнаружение проблем через камеры.

```
backend/services/plant-vision/
├── main.py
├── detectors/
│   ├── disease_detector.py
│   ├── pest_detector.py
│   ├── growth_analyzer.py
│   └── nutrient_deficiency_detector.py
├── camera_integration.py
└── models.py
```

### 7.2. Capabilities

```python
class PlantVisionService:
    """
    Компьютерное зрение для анализа растений.
    
    Возможности:
    - Обнаружение болезней (мучнистая роса, плесень, etc.)
    - Обнаружение вредителей
    - Анализ роста (высота, площадь листьев)
    - Определение дефицита питательных веществ по цвету листьев
    """
    
    async def analyze_zone_images(
        self,
        zone_id: int,
        images: List[ImageData]
    ) -> VisionAnalysis:
        """Проанализировать изображения зоны."""
        
        results = []
        
        # Обнаружение болезней
        diseases = await self.disease_detector.detect(images)
        for disease in diseases:
            results.append(VisionResult(
                type="disease",
                name=disease.name,
                confidence=disease.confidence,
                severity=disease.severity,
                affected_area_pct=disease.affected_area_pct,
                recommended_action=disease.treatment
            ))
        
        # Анализ роста
        growth = await self.growth_analyzer.analyze(images)
        results.append(VisionResult(
            type="growth",
            plant_height_cm=growth.height,
            leaf_area_cm2=growth.leaf_area,
            growth_rate=growth.daily_growth_rate,
            comparison_to_expected=growth.vs_expected
        ))
        
        # Дефицит питательных веществ
        deficiencies = await self.nutrient_deficiency_detector.detect(images)
        for deficiency in deficiencies:
            results.append(VisionResult(
                type="nutrient_deficiency",
                nutrient=deficiency.nutrient,
                severity=deficiency.severity,
                recommended_action=deficiency.treatment
            ))
        
        return VisionAnalysis(
            zone_id=zone_id,
            timestamp=utcnow(),
            results=results,
            images_processed=len(images)
        )
```

---

## 8. Фаза 7: Full Autonomous Cycle Management (Приоритет: ВЫСОКИЙ)

### 8.1. Autonomous Cycle Orchestrator

**Цель:** Полное управление циклом выращивания от seedling до harvest.

```python
class AutonomousCycleOrchestrator:
    """
    Оркестратор автономного цикла выращивания.
    
    Управляет:
    - Startup (подготовка раствора, проверка оборудования)
    - Growth (все фазы вегетации)
    - Transition (переход между фазами)
    - Harvest (определение готовности, уведомление)
    """
    
    async def manage_cycle(self, grow_cycle_id: int) -> CycleStatus:
        """
        Управление полным циклом выращивания.
        """
        cycle = await self.get_cycle(grow_cycle_id)
        phase = cycle.current_phase
        
        # Startup phase
        if phase.name == "STARTUP":
            await self.execute_startup_sequence(cycle)
        
        # Growth phases
        elif phase.name in ["SEEDLING", "VEG", "FLOWER"]:
            await self.manage_growth_phase(cycle)
        
        # Transition check
        if await self.should_transition(cycle):
            await self.transition_phase(cycle)
        
        # Harvest check
        if await self.is_ready_for_harvest(cycle):
            await self.initiate_harvest(cycle)
        
        return cycle.status
    
    async def execute_startup_sequence(self, cycle: GrowCycle):
        """
        Последовательность запуска цикла.
        
        1. Проверить оборудование
        2. Подготовить раствор
        3. Проверить сенсоры
        4. Запустить полив
        5. Установить освещение
        """
        zone_id = cycle.zone_id
        
        # 1. Equipment check
        equipment_ok = await self.check_equipment(zone_id)
        if not equipment_ok:
            await self.alert_user("Equipment check failed", severity="critical")
            return
        
        # 2. Solution preparation
        solution_ok = await self.prepare_solution(zone_id, cycle.recipe_revision)
        if not solution_ok:
            await self.alert_user("Solution preparation failed", severity="critical")
            return
        
        # 3. Sensor calibration check
        sensors_ok = await self.verify_sensors(zone_id)
        if not sensors_ok:
            await self.alert_user("Sensor verification failed", severity="warning")
            # Continue with caution
        
        # 4. Start irrigation
        await self.start_irrigation(zone_id)
        
        # 5. Configure lighting
        await self.configure_lighting(zone_id, cycle.current_phase)
        
        # Mark startup complete
        await self.mark_startup_complete(cycle)
    
    async def is_ready_for_harvest(self, cycle: GrowCycle) -> bool:
        """
        Определить готовность к harvest.
        
        Критерии:
        - Достигнут конец фазы FLOWER по времени
        - ИЛИ достигнут target GDD
        - ИЛИ визуальные признаки зрелости (через CV)
        """
        phase = cycle.current_phase
        
        if phase.name != "FLOWER":
            return False
        
        # Time-based
        if phase.days_elapsed >= phase.duration_days:
            return True
        
        # GDD-based
        if phase.progress_model == "GDD":
            current_gdd = await self.calculate_gdd(cycle)
            if current_gdd >= phase.target_gdd:
                return True
        
        # CV-based (если доступно)
        if self.vision_service.available:
            maturity = await self.vision_service.assess_maturity(cycle.zone_id)
            if maturity.ready_for_harvest:
                return True
        
        return False
    
    async def initiate_harvest(self, cycle: GrowCycle):
        """
        Инициировать harvest.
        
        1. Уведомить пользователя
        2. Если autonomy_level >= 4 — автоматически остановить полив
        3. Подготовить отчёт о цикле
        """
        # Stop irrigation
        await self.stop_all_irrigation(cycle.zone_id)
        
        # Turn off lights (optional)
        await self.turn_off_lights(cycle.zone_id)
        
        # Generate cycle report
        report = await self.generate_cycle_report(cycle)
        
        # Notify user
        await self.notify_user(
            message="🌱 Your plants are ready for harvest!",
            details=report,
            actions=["confirm_harvest", "extend_cycle", "view_report"]
        )
```

---

## 9. Database Schema Extensions

### 9.1. Новые таблицы

```sql
-- Autonomy configuration per zone
CREATE TABLE zone_autonomy_config (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id) ON DELETE CASCADE UNIQUE,
    autonomy_level INT DEFAULT 1 CHECK (autonomy_level BETWEEN 0 AND 5),
    enabled_features JSONB DEFAULT '{}',
    constraints JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Autonomous actions log
CREATE TABLE autonomous_actions (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    grow_cycle_id BIGINT REFERENCES grow_cycles(id),
    
    action_type VARCHAR NOT NULL,
    action_params JSONB,
    reason VARCHAR,
    trigger VARCHAR,  -- prediction, anomaly, schedule, user_request
    
    -- Prediction context
    predicted_outcome JSONB,
    prediction_confidence DECIMAL(5,4),
    
    -- Execution
    status VARCHAR DEFAULT 'pending',  -- pending, executing, completed, failed, cancelled
    executed_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Result
    actual_outcome JSONB,
    success BOOLEAN,
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    INDEX (zone_id, created_at DESC),
    INDEX (grow_cycle_id, created_at DESC),
    INDEX (status, created_at)
);

-- Pending approvals
CREATE TABLE autonomous_approvals (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    action_id BIGINT REFERENCES autonomous_actions(id),
    
    -- Request
    request_type VARCHAR NOT NULL,
    request_details JSONB,
    risk_level VARCHAR,  -- low, medium, high, critical
    
    -- Status
    status VARCHAR DEFAULT 'pending',  -- pending, approved, rejected, expired
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    
    -- Response
    responded_at TIMESTAMP,
    responded_by BIGINT REFERENCES users(id),
    response_notes TEXT,
    
    INDEX (zone_id, status, created_at)
);

-- Anomaly records
CREATE TABLE anomalies (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    
    type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    message TEXT,
    
    -- Detection
    detected_at TIMESTAMP DEFAULT NOW(),
    detection_method VARCHAR,  -- rule_based, ml_model, threshold
    
    -- Context
    telemetry_snapshot JSONB,
    related_commands JSONB,
    
    -- Response
    status VARCHAR DEFAULT 'active',  -- active, acknowledged, resolved, false_positive
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    automatic_response_taken BOOLEAN DEFAULT FALSE,
    
    INDEX (zone_id, status, detected_at DESC),
    INDEX (type, severity, detected_at DESC)
);

-- Predictions log
CREATE TABLE predictions (
    id BIGSERIAL PRIMARY KEY,
    zone_id BIGINT REFERENCES zones(id),
    
    metric_type VARCHAR NOT NULL,  -- ph, ec, temp_air, vpd, etc.
    
    -- Prediction
    current_value DECIMAL,
    predicted_value DECIMAL,
    horizon_hours DECIMAL(5,2),
    predicted_at TIMESTAMP,
    
    -- Model info
    model_version VARCHAR,
    confidence DECIMAL(5,4),
    model_params JSONB,
    
    -- Validation (filled later)
    actual_value DECIMAL,
    actual_at TIMESTAMP,
    accuracy_error DECIMAL,
    
    created_at TIMESTAMP DEFAULT NOW(),
    
    INDEX (zone_id, metric_type, created_at DESC)
);

-- Weather data cache
CREATE TABLE weather_cache (
    id BIGSERIAL PRIMARY KEY,
    greenhouse_id BIGINT REFERENCES greenhouses(id),
    
    -- Current weather
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    pressure DECIMAL(7,2),
    wind_speed DECIMAL(5,2),
    wind_direction INT,
    cloudiness INT,
    precipitation DECIMAL(5,2),
    
    -- Metadata
    provider VARCHAR,
    location_lat DECIMAL(9,6),
    location_lon DECIMAL(9,6),
    observed_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    
    INDEX (greenhouse_id, observed_at DESC)
);

-- Weather forecasts
CREATE TABLE weather_forecasts (
    id BIGSERIAL PRIMARY KEY,
    greenhouse_id BIGINT REFERENCES greenhouses(id),
    
    forecast_for TIMESTAMP,
    temperature_min DECIMAL(5,2),
    temperature_max DECIMAL(5,2),
    humidity DECIMAL(5,2),
    precipitation_probability INT,
    cloudiness INT,
    
    provider VARCHAR,
    forecast_generated_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    
    INDEX (greenhouse_id, forecast_for)
);
```

---

## 10. API Extensions

### 10.1. New REST Endpoints

```yaml
# Autonomy Configuration
GET    /api/zones/{id}/autonomy           # Get autonomy config
PUT    /api/zones/{id}/autonomy           # Update autonomy config

# Autonomous Actions
GET    /api/zones/{id}/autonomous-actions # List actions
GET    /api/autonomous-actions/{id}       # Get action details
POST   /api/autonomous-actions/{id}/cancel # Cancel pending action

# Approvals
GET    /api/approvals/pending             # List pending approvals
POST   /api/approvals/{id}/approve        # Approve action
POST   /api/approvals/{id}/reject         # Reject action

# Predictions
GET    /api/zones/{id}/predictions        # Get current predictions
GET    /api/zones/{id}/predictions/history # Prediction history

# Anomalies
GET    /api/zones/{id}/anomalies          # List anomalies
POST   /api/anomalies/{id}/acknowledge    # Acknowledge anomaly
POST   /api/anomalies/{id}/resolve        # Mark as resolved

# Weather
GET    /api/greenhouses/{id}/weather      # Current weather
GET    /api/greenhouses/{id}/weather/forecast # Weather forecast

# Recipe Adaptations
GET    /api/grow-cycles/{id}/adaptations  # List adaptations
POST   /api/grow-cycles/{id}/adaptations  # Request adaptation
```

### 10.2. WebSocket Events

```typescript
// New WebSocket events for real-time updates
interface AutonomousActionEvent {
  type: "autonomous_action";
  action: AutonomousAction;
}

interface ApprovalRequestEvent {
  type: "approval_request";
  request: ApprovalRequest;
}

interface AnomalyEvent {
  type: "anomaly_detected" | "anomaly_resolved";
  anomaly: Anomaly;
}

interface PredictionUpdateEvent {
  type: "prediction_update";
  zone_id: number;
  predictions: Prediction[];
}
```

---

## 11. Frontend Extensions

### 11.1. New Components

```vue
<!-- Autonomy Dashboard -->
<AutonomyDashboard>
  <!-- Current autonomy level -->
  <AutonomyLevelSelector :zone="zone" />
  
  <!-- Pending approvals -->
  <PendingApprovalsList :zone="zone" />
  
  <!-- Recent autonomous actions -->
  <AutonomousActionsLog :zone="zone" />
  
  <!-- Predictions visualization -->
  <PredictionsChart :zone="zone" />
  
  <!-- Anomalies panel -->
  <AnomaliesPanel :zone="zone" />
</AutonomyDashboard>
```

### 11.2. Autonomy Level Selector

```vue
<template>
  <div class="autonomy-level-selector">
    <h3>Уровень автономности</h3>
    
    <div class="level-options">
      <button 
        v-for="level in LEVELS" 
        :key="level.level"
        :class="['level-btn', { active: currentLevel === level.level }]"
        @click="setLevel(level.level)"
      >
        <span class="level-number">{{ level.level }}</span>
        <span class="level-name">{{ level.name }}</span>
      </button>
    </div>
    
    <div class="level-description">
      {{ currentLevelDescription }}
    </div>
    
    <div class="enabled-features">
      <h4>Разрешённые действия:</h4>
      <ul>
        <li v-for="action in currentLevelActions" :key="action">
          {{ actionLabels[action] }}
        </li>
      </ul>
    </div>
  </div>
</template>
```

### 11.3. Approval Request Modal

```vue
<template>
  <Modal v-if="show" @close="close">
    <template #header>
      <span :class="['severity-badge', request.risk_level]">
        {{ request.risk_level }}
      </span>
      Требуется подтверждение
    </template>
    
    <div class="approval-content">
      <p class="action-description">
        {{ request.request_details.description }}
      </p>
      
      <div class="prediction-context" v-if="request.request_details.prediction">
        <h4>Прогноз:</h4>
        <div class="prediction-values">
          <span>Текущее: {{ request.request_details.prediction.current }}</span>
          <span>→</span>
          <span>Предсказанное: {{ request.request_details.prediction.predicted }}</span>
        </div>
      </div>
      
      <div class="risk-assessment">
        <h4>Оценка риска:</h4>
        <p>{{ request.request_details.risk_assessment }}</p>
      </div>
      
      <div class="recommended-action">
        <h4>Рекомендуемое действие:</h4>
        <p>{{ request.request_details.recommended_action }}</p>
      </div>
    </div>
    
    <template #footer>
      <button class="btn-reject" @click="reject">Отклонить</button>
      <button class="btn-approve" @click="approve">Подтвердить</button>
    </template>
  </Modal>
</template>
```

---

## 12. Implementation Roadmap

### 12.1. Phase 1: Predictive Analytics (4 недели)

**Неделя 1-2:**
- [ ] Создать Prediction Engine service skeleton
- [ ] Реализовать Trend Analyzer (EWMA, Linear Regression)
- [ ] Интегрировать с automation-engine

**Неделя 3-4:**
- [ ] Реализовать Proactive Correction Policy
- [ ] Добавить API endpoints для predictions
- [ ] Frontend: Predictions visualization
- [ ] Тестирование на historical data

### 12.2. Phase 2: Autonomous Decision Making (6 недель)

**Неделя 1-2:**
- [ ] Создать autonomous-agent service
- [ ] Реализовать Safety Guard
- [ ] Создать DB tables (autonomous_actions, autonomous_approvals)

**Неделя 3-4:**
- [ ] Реализовать Decision Engine
- [ ] Реализовать Approval Manager
- [ ] Интегрировать notifications (WebSocket, push)

**Неделя 5-6:**
- [ ] Frontend: Autonomy Dashboard
- [ ] Frontend: Approval Modal
- [ ] End-to-end testing

### 12.3. Phase 3: Adaptive Recipe Optimization (4 недели)

**Неделя 1-2:**
- [ ] Создать Recipe Adaptation Engine
- [ ] Реализовать adaptation analysis
- [ ] DB table: recipe_adaptations

**Неделя 3-4:**
- [ ] Интегрировать с autonomous-agent
- [ ] Frontend: Adaptations UI
- [ ] Testing

### 12.4. Phase 4: Anomaly Detection (4 недели)

**Неделя 1-2:**
- [ ] Создать anomaly-detector service
- [ ] Реализовать sensor anomaly detection
- [ ] Реализовать equipment anomaly detection

**Неделя 3-4:**
- [ ] Реализовать plant stress detection
- [ ] Реализовать automatic response
- [ ] Frontend: Anomalies Panel

### 12.5. Phase 5: Weather Integration (2 недели)

**Неделя 1:**
- [ ] Создать weather-integration service
- [ ] Интегрировать с OpenWeatherMap API

**Неделя 2:**
- [ ] Реализовать Weather-Aware Climate Controller
- [ ] Testing

### 12.6. Phase 6: Computer Vision (8+ недель, опционально)

**Исследование и прототипирование.**
**Зависит от наличия камер и инфраструктуры.**

### 12.7. Phase 7: Full Autonomous Cycle (4 недели)

**Неделя 1-2:**
- [ ] Создать Autonomous Cycle Orchestrator
- [ ] Реализовать startup sequence

**Неделя 3-4:**
- [ ] Реализовать harvest detection
- [ ] Интегрировать все компоненты
- [ ] End-to-end testing

---

## 13. Success Metrics

### 13.1. Technical Metrics

| Метрика | Target | Measurement |
|---------|--------|-------------|
| Prediction Accuracy | >80% (3h horizon) | Comparison predicted vs actual |
| False Positive Anomalies | <5% | User-marked false positives |
| Autonomous Action Success Rate | >95% | Completed vs failed actions |
| Mean Time to Detection (anomalies) | <5 min | Anomaly detection latency |
| System Uptime | >99.5% | Service availability |

### 13.2. User Experience Metrics

| Метрика | Target | Measurement |
|---------|--------|-------------|
| Approvals per day | <2 (level 3+) | Approval requests count |
| User interventions per cycle | <5 | Manual overrides count |
| Time saved per cycle | >80% | vs manual operation |
| User satisfaction | >4.5/5 | Survey |

### 13.3. Plant Health Metrics

| Метрика | Target | Measurement |
|---------|--------|-------------|
| pH in range time | >95% | Time within target range |
| EC in range time | >95% | Time within target range |
| VPD in optimal range | >90% | Time within optimal VPD |
| Yield vs expected | >90% | Actual yield vs recipe expected |

---

## 14. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Over-correction cascade | Medium | High | Hard limits, cooldown periods, human confirmation for significant changes |
| Sensor failure leads to bad decisions | Medium | High | Multi-sensor validation, anomaly detection, fallback to safe mode |
| AI model drift | Low | Medium | Continuous model validation, automatic recalibration |
| Network partition | Low | High | Local fail-safe on ESP32 nodes, graceful degradation |
| User loses trust in autonomy | Medium | High | Transparency, explainability, gradual autonomy increase |

---

## 15. Related Documents

- `doc_ai/SYSTEM_ARCH_FULL.md` — системная архитектура
- `doc_ai/ARCHITECTURE_FLOWS.md` — потоки данных
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация targets
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — state machine коррекции
- `doc_ai/09_AI_AND_DIGITAL_TWIN/AI_ARCH_FULL.md` — архитектура AI-слоя

---

**Документ создан:** 2026-02-16
**Последнее обновление:** 2026-02-16
**Автор:** AI Assistant (на основе анализа проекта Hydro 2.0)
