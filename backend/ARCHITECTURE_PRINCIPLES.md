# Архитектурные принципы проекта Hydro2.0

## Принцип тонких контроллеров (Thin Controllers)

### Определение
Контроллеры должны быть минималистичными и содержать только логику, связанную с HTTP-запросами и ответами. Вся бизнес-логика должна быть вынесена в сервисы.

### Правила для контроллеров

1. **Только HTTP-логика**:
   - Прием и валидация запросов
   - Проверка прав доступа
   - Вызов сервисов для выполнения бизнес-логики
   - Формирование и возврат HTTP-ответов

2. **НЕ должно быть в контроллерах**:
   - Прямых запросов к БД (использовать модели через сервисы)
   - Транзакций БД (DB::transaction в сервисах)
   - Сложной бизнес-логики
   - Прямого создания/обновления моделей (через сервисы)
   - Логики форматирования данных (в презентерах/DTO)

3. **Структура контроллера**:
   ```php
   public function action(Request $request, Model $model): JsonResponse
   {
       // 1. Аутентификация и авторизация
       $user = $request->user();
       if (!$user) {
           return response()->json(['error' => 'Unauthorized'], 401);
       }
       
       // 2. Валидация входных данных
       $data = $request->validate([...]);
       
       // 3. Вызов сервиса для бизнес-логики
       $result = $this->service->doSomething($model, $data, $user);
       
       // 4. Возврат ответа
       return response()->json(['status' => 'ok', 'data' => $result]);
   }
   ```

### Примеры правильной архитектуры

#### ✅ Правильно (тонкий контроллер)
```php
class GrowCycleController extends Controller
{
    public function __construct(
        private GrowCycleService $growCycleService
    ) {}
    
    public function store(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json(['error' => 'Unauthorized'], 401);
        }
        
        $data = $request->validate([...]);
        
        $cycle = $this->growCycleService->createCycle($zone, $data, $user);
        
        return response()->json(['status' => 'ok', 'data' => $cycle], 201);
    }
}
```

#### ❌ Неправильно (толстый контроллер)
```php
class GrowCycleController extends Controller
{
    public function store(Request $request, Zone $zone): JsonResponse
    {
        // Валидация
        $data = $request->validate([...]);
        
        // Прямая работа с БД в контроллере
        return DB::transaction(function () use ($zone, $data) {
            $cycle = GrowCycle::create([...]);
            GrowCycleTransition::create([...]);
            DB::table('zone_events')->insert([...]);
            broadcast(new GrowCycleUpdated($cycle));
            return response()->json(['status' => 'ok', 'data' => $cycle]);
        });
    }
}
```

### Сервисы

Сервисы содержат всю бизнес-логику:
- Создание/обновление/удаление сущностей
- Транзакции БД
- Валидация бизнес-правил
- Вызов событий
- Интеграции с внешними системами

### Презентеры/DTO

Для форматирования данных для API используются презентеры или DTO классы.

### Применение

При создании или изменении контроллеров всегда проверять:
1. Нет ли прямых запросов к БД?
2. Нет ли транзакций в контроллере?
3. Вся бизнес-логика вынесена в сервисы?
4. Контроллер только валидирует, вызывает сервис и возвращает ответ?

