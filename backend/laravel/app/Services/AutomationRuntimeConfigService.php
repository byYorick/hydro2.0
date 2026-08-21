<?php

namespace App\Services;

use App\Services\AutomationScheduler\SchedulerMetricsStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Arr;
use Illuminate\Validation\ValidationException;

class AutomationRuntimeConfigService
{
    public function __construct(
        private readonly SchedulerMetricsStore $schedulerMetricsStore,
    ) {}

    private const KNOWN_CATCHUP_POLICIES = ['replay_limited', 'skip'];

    private const DEFAULT_AUTOMATION_ENGINE_API_URL = 'http://automation-engine:9405';

    /**
     * @var array<string, array<string, mixed>>
     */
    private const DEFINITIONS = [
        'automation_engine.api_url' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'api_url',
            'label' => 'Адрес движка автоматики',
            'description' => 'Базовый URL AE runtime API, куда Laravel отправляет команды запуска циклов.',
            'config_path' => 'services.automation_engine.api_url',
            'default' => self::DEFAULT_AUTOMATION_ENGINE_API_URL,
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
            'advanced' => true,
        ],
        'automation_engine.timeout' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'timeout_sec',
            'label' => 'Таймаут запроса к движку',
            'description' => 'Сколько Laravel ждёт ответ от automation-engine, прежде чем считать запрос неудачным.',
            'config_path' => 'services.automation_engine.timeout',
            'default' => 2.0,
            'type' => 'float',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1.0,
            'step' => 0.1,
            'unit' => 'сек',
            'advanced' => true,
        ],
        'automation_engine.laravel_scheduler_enabled' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'laravel_scheduler_enabled',
            'label' => 'Планировщик включён',
            'description' => 'Главный выключатель: без него Laravel не отправляет расписания полива и света в движок автоматики.',
            'config_path' => 'services.automation_engine.laravel_scheduler_enabled',
            'default' => false,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
            'advanced' => false,
        ],
        'automation_engine.scheduler_id' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'scheduler_id',
            'label' => 'Идентификатор планировщика',
            'description' => 'Название источника команд в заголовках запросов — видно в логах движка.',
            'config_path' => 'services.automation_engine.scheduler_id',
            'default' => 'laravel-scheduler',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
            'advanced' => true,
        ],
        'automation_engine.scheduler_version' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'scheduler_version',
            'label' => 'Версия планировщика',
            'description' => 'Версия отправителя, передаётся движку для диагностики совместимости.',
            'config_path' => 'services.automation_engine.scheduler_version',
            'default' => '3.0.0',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
            'advanced' => true,
        ],
        'automation_engine.scheduler_protocol_version' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'scheduler_protocol_version',
            'label' => 'Версия протокола',
            'description' => 'Версия протокола обмена между планировщиком и движком автоматики.',
            'config_path' => 'services.automation_engine.scheduler_protocol_version',
            'default' => '2.0',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
            'advanced' => true,
        ],
        'automation_engine.scheduler_api_token' => [
            'section_key' => 'transport',
            'section_title' => 'Подключение к движку автоматики',
            'item_key' => 'scheduler_api_token_configured',
            'label' => 'Токен доступа задан',
            'description' => 'Показывается только факт наличия токена — само значение не отображается в интерфейсе.',
            'config_path' => 'services.automation_engine.scheduler_api_token',
            'default' => '',
            'type' => 'token_presence',
            'input_type' => 'readonly',
            'editable' => false,
            'advanced' => true,
        ],
        'automation_engine.grow_cycle_start_dispatch_enabled' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'grow_cycle_start_dispatch_enabled',
            'label' => 'Автозапуск цикла выращивания',
            'description' => 'Запускать автоматику сразу при старте цикла выращивания, не дожидаясь ручной команды.',
            'config_path' => 'services.automation_engine.grow_cycle_start_dispatch_enabled',
            'default' => true,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
            'advanced' => false,
        ],
        'automation_engine.scheduler_due_grace_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_due_grace_sec',
            'label' => 'Допуск опоздания задачи',
            'description' => 'Насколько раньше срока задачу уже можно отправлять в работу.',
            'config_path' => 'services.automation_engine.scheduler_due_grace_sec',
            'default' => 15,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'сек',
            'advanced' => false,
        ],
        'automation_engine.scheduler_expires_after_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_expires_after_sec',
            'label' => 'Срок жизни задачи',
            'description' => 'Через сколько незавершённая задача считается просроченной и больше не выполняется.',
            'config_path' => 'services.automation_engine.scheduler_expires_after_sec',
            'default' => 600,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 2,
            'unit' => 'сек',
            'advanced' => false,
        ],
        'automation_engine.scheduler_hard_stale_after_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_hard_stale_after_sec',
            'label' => 'Порог зависания задачи',
            'description' => 'После этого времени планировщик закрывает зависшую задачу самостоятельно.',
            'config_path' => 'services.automation_engine.scheduler_hard_stale_after_sec',
            'default' => 1200,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 2,
            'unit' => 'сек',
            'advanced' => false,
        ],
        'automation_engine.scheduler_catchup_policy' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_catchup_policy',
            'label' => 'Что делать с пропусками',
            'description' => 'replay_limited — досылать пропущенные окна с ограничением, skip — пропускать их без досылки.',
            'config_path' => 'services.automation_engine.scheduler_catchup_policy',
            'default' => 'replay_limited',
            'type' => 'enum',
            'input_type' => 'select',
            'editable' => true,
            'options' => ['replay_limited', 'skip'],
            'option_labels' => [
                'replay_limited' => 'Досылать пропущенные (с лимитом)',
                'skip' => 'Пропускать без досылки',
            ],
            'advanced' => false,
        ],
        'automation_engine.scheduler_catchup_max_windows' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_catchup_max_windows',
            'label' => 'Максимум досылаемых окон',
            'description' => 'Сколько пропущенных окон расписания досылается за один проход.',
            'config_path' => 'services.automation_engine.scheduler_catchup_max_windows',
            'default' => 3,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'advanced' => true,
        ],
        'automation_engine.scheduler_catchup_rate_limit_per_cycle' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_catchup_rate_limit_per_cycle',
            'label' => 'Лимит досылок за цикл',
            'description' => 'Ограничение числа отправленных догоняющих команд за один цикл планировщика.',
            'config_path' => 'services.automation_engine.scheduler_catchup_rate_limit_per_cycle',
            'default' => 20,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'advanced' => true,
        ],
        'automation_engine.scheduler_dispatch_interval_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_dispatch_interval_sec',
            'label' => 'Как часто проверять расписания',
            'description' => 'Период запуска планировщика: чем меньше, тем точнее время полива и света.',
            'config_path' => 'services.automation_engine.scheduler_dispatch_interval_sec',
            'default' => 60,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 10,
            'unit' => 'сек',
            'advanced' => false,
        ],
        'automation_engine.scheduler_dispatch_parallelism' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_dispatch_parallelism',
            'label' => 'Одновременных отправок',
            'description' => 'Сколько команд планировщик отправляет параллельно за один проход.',
            'config_path' => 'services.automation_engine.scheduler_dispatch_parallelism',
            'default' => 8,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'max' => 100,
            'advanced' => true,
        ],
        'automation_engine.scheduler_lock_key' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_lock_key',
            'label' => 'Ключ блокировки',
            'description' => 'Имя общей блокировки, которая не даёт двум планировщикам работать одновременно.',
            'config_path' => 'services.automation_engine.scheduler_lock_key',
            'default' => 'automation:dispatch-schedules',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
            'advanced' => true,
        ],
        'automation_engine.scheduler_lock_ttl_sec' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_lock_ttl_sec',
            'label' => 'Время жизни блокировки',
            'description' => 'Сколько держится блокировка планировщика, если проход завершился аварийно.',
            'config_path' => 'services.automation_engine.scheduler_lock_ttl_sec',
            'default' => 55,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 10,
            'unit' => 'сек',
            'advanced' => true,
        ],
        'automation_engine.scheduler_lock_ttl_margin_sec' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_lock_ttl_margin_sec',
            'label' => 'Запас времени блокировки',
            'description' => 'Дополнительный запас к типовой длительности прохода при расчёте времени блокировки.',
            'config_path' => 'services.automation_engine.scheduler_lock_ttl_margin_sec',
            'default' => 10,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'сек',
            'advanced' => true,
        ],
        'automation_engine.scheduler_active_task_ttl_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_active_task_ttl_sec',
            'label' => 'Время жизни активной задачи',
            'description' => 'Сколько задача хранится как активная, пока планировщик ждёт её завершения.',
            'config_path' => 'services.automation_engine.scheduler_active_task_ttl_sec',
            'default' => 180,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 30,
            'unit' => 'сек',
            'advanced' => true,
        ],
        'automation_engine.scheduler_active_task_retention_days' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_active_task_retention_days',
            'label' => 'Хранить историю задач',
            'description' => 'Сколько дней завершённые задачи остаются в базе для разбора инцидентов.',
            'config_path' => 'services.automation_engine.scheduler_active_task_retention_days',
            'default' => 60,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'дней',
            'advanced' => true,
        ],
        'automation_engine.scheduler_active_task_cleanup_batch' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_active_task_cleanup_batch',
            'label' => 'Размер пачки очистки',
            'description' => 'Сколько завершённых задач удаляется за один проход очистки.',
            'config_path' => 'services.automation_engine.scheduler_active_task_cleanup_batch',
            'default' => 500,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'advanced' => true,
        ],
        'automation_engine.scheduler_active_task_poll_batch' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Планировщик задач',
            'item_key' => 'scheduler_active_task_poll_batch',
            'label' => 'Размер пачки опроса',
            'description' => 'Сколько активных задач планировщик проверяет за один проход.',
            'config_path' => 'services.automation_engine.scheduler_active_task_poll_batch',
            'default' => 500,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'advanced' => true,
        ],
        'automation_engine.scheduler_cursor_persist_enabled' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Пропуски расписания и блокировки',
            'item_key' => 'scheduler_cursor_persist_enabled',
            'label' => 'Запоминать позицию планировщика',
            'description' => 'Сохранять место, на котором остановился планировщик, чтобы продолжить после перезапуска.',
            'config_path' => 'services.automation_engine.scheduler_cursor_persist_enabled',
            'default' => true,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
            'advanced' => true,
        ],
        'python_bridge.timeout' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Связь с Python-сервисами',
            'item_key' => 'python_timeout_sec',
            'label' => 'Таймаут запроса',
            'description' => 'Сколько Laravel ждёт ответ от Python-сервисов, прежде чем считать запрос неудачным.',
            'config_path' => 'services.python_bridge.timeout',
            'default' => 10,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'сек',
            'advanced' => true,
        ],
        'python_bridge.retry_attempts' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Связь с Python-сервисами',
            'item_key' => 'python_retry_attempts',
            'label' => 'Число повторов',
            'description' => 'Сколько раз повторить запрос к Python-сервису после ошибки связи.',
            'config_path' => 'services.python_bridge.retry_attempts',
            'default' => 2,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 0,
            'advanced' => true,
        ],
        'python_bridge.retry_delay' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Связь с Python-сервисами',
            'item_key' => 'python_retry_delay_sec',
            'label' => 'Пауза между повторами',
            'description' => 'Задержка перед повторной попыткой запроса к Python-сервису.',
            'config_path' => 'services.python_bridge.retry_delay',
            'default' => 1,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 0,
            'unit' => 'сек',
            'advanced' => true,
        ],
    ];

    /**
     * @var array<string, mixed>|null
     */
    private ?array $overrides = null;

    /**
     * @return array<string, mixed>
     */
    public static function defaultSettingsMapStatic(): array
    {
        $result = [];
        foreach (self::DEFINITIONS as $key => $definition) {
            if (! (bool) ($definition['editable'] ?? false)) {
                continue;
            }

            $result[$key] = $definition['default'];
        }

        return $result;
    }

    public function schedulerEnabled(): bool
    {
        return $this->boolValue('automation_engine.laravel_scheduler_enabled', false);
    }

    public function automationEngineValue(string $field, mixed $fallback = null): mixed
    {
        return $this->value("automation_engine.{$field}", $fallback);
    }

    public function pythonBridgeValue(string $field, mixed $fallback = null): mixed
    {
        return $this->value("python_bridge.{$field}", $fallback);
    }

    /**
     * @return array<string, mixed>
     */
    public function schedulerConfig(): array
    {
        $dueGraceSec = max(1, $this->intValue('automation_engine.scheduler_due_grace_sec', 15));
        $expiresAfterSec = max($dueGraceSec + 1, $this->intValue('automation_engine.scheduler_expires_after_sec', 600));
        $defaultHardStaleAfterSec = max(900, $expiresAfterSec * 2);
        $configuredHardStaleAfterSec = $this->intValue(
            'automation_engine.scheduler_hard_stale_after_sec',
            $defaultHardStaleAfterSec
        );
        $usesLegacyDefaultHardStale = ! $this->hasOverride('automation_engine.scheduler_hard_stale_after_sec')
            && $configuredHardStaleAfterSec === 1200;
        $hardStaleAfterSec = max(
            $expiresAfterSec + 1,
            $usesLegacyDefaultHardStale ? $defaultHardStaleAfterSec : $configuredHardStaleAfterSec
        );

        $catchupPolicy = strtolower($this->stringValue('automation_engine.scheduler_catchup_policy', 'replay_limited'));
        if (! in_array($catchupPolicy, self::KNOWN_CATCHUP_POLICIES, true)) {
            $catchupPolicy = 'replay_limited';
        }
        $configuredLockTtlSec = max(10, $this->intValue('automation_engine.scheduler_lock_ttl_sec', 55));
        $lockTtlMarginSec = max(1, $this->intValue('automation_engine.scheduler_lock_ttl_margin_sec', 10));
        $p99CycleDurationSec = $this->schedulerMetricsStore->estimateCycleDurationP99('start_cycle');
        $lockTtlFromP99 = $p99CycleDurationSec === null
            ? 0
            : (int) ceil(max(0.0, $p99CycleDurationSec) + $lockTtlMarginSec);

        return [
            'api_url' => rtrim($this->stringValue('automation_engine.api_url', self::DEFAULT_AUTOMATION_ENGINE_API_URL), '/'),
            'timeout_sec' => max(1.0, $this->floatValue('automation_engine.timeout', 2.0)),
            'scheduler_id' => $this->stringValue('automation_engine.scheduler_id', 'laravel-scheduler'),
            'scheduler_version' => $this->stringValue('automation_engine.scheduler_version', '3.0.0'),
            'protocol_version' => $this->stringValue('automation_engine.scheduler_protocol_version', '2.0'),
            'token' => trim($this->stringValue('automation_engine.scheduler_api_token', '')),
            'due_grace_sec' => $dueGraceSec,
            'expires_after_sec' => $expiresAfterSec,
            'hard_stale_after_sec' => $hardStaleAfterSec,
            'catchup_policy' => $catchupPolicy,
            'catchup_max_windows' => max(1, $this->intValue('automation_engine.scheduler_catchup_max_windows', 3)),
            'catchup_rate_limit_per_cycle' => max(1, $this->intValue('automation_engine.scheduler_catchup_rate_limit_per_cycle', 20)),
            'dispatch_interval_sec' => max(10, $this->intValue('automation_engine.scheduler_dispatch_interval_sec', 60)),
            'dispatch_parallelism' => max(1, $this->intValue('automation_engine.scheduler_dispatch_parallelism', 8)),
            'lock_key' => $this->stringValue('automation_engine.scheduler_lock_key', 'automation:dispatch-schedules'),
            'lock_ttl_sec' => max(10, $configuredLockTtlSec, $lockTtlFromP99),
            'lock_ttl_margin_sec' => $lockTtlMarginSec,
            'active_task_ttl_sec' => max(30, $this->intValue('automation_engine.scheduler_active_task_ttl_sec', $expiresAfterSec)),
            'active_task_retention_days' => max(1, $this->intValue('automation_engine.scheduler_active_task_retention_days', 60)),
            'active_task_cleanup_batch' => max(1, $this->intValue('automation_engine.scheduler_active_task_cleanup_batch', 500)),
            'active_task_poll_batch' => max(1, $this->intValue('automation_engine.scheduler_active_task_poll_batch', 500)),
            'cursor_persist_enabled' => $this->boolValue('automation_engine.scheduler_cursor_persist_enabled', true),
        ];
    }

    /**
     * TTL mutex для {@see \Illuminate\Console\Scheduling\Event::withoutOverlapping()} (минуты).
     * Должен быть не меньше ceil(effective lock_ttl_sec из {@see self::schedulerConfig()} / 60), иначе
     * следующий tick расписания может стартовать до истечения Cache-lock dispatch.
     */
    public function schedulerMutexExpiryMinutes(): int
    {
        $ttlSec = (int) ($this->schedulerConfig()['lock_ttl_sec'] ?? 60);

        return max(1, (int) ceil($ttlSec / 60));
    }

    /**
     * @return array{generated_at: string, sections: array<int, array<string, mixed>>}
     */
    public function settingsSnapshot(): array
    {
        $schedulerConfig = $this->schedulerConfig();
        $sections = [];

        foreach (self::DEFINITIONS as $key => $definition) {
            $sectionKey = (string) $definition['section_key'];
            $sectionTitle = (string) $definition['section_title'];
            if (! isset($sections[$sectionKey])) {
                $sections[$sectionKey] = [
                    'key' => $sectionKey,
                    'title' => $sectionTitle,
                    'items' => [],
                ];
            }

            $value = $this->value($key, $definition['default']);
            if ($key === 'automation_engine.scheduler_api_token') {
                $value = trim((string) $value) !== '';
            }

            $effectiveValue = $this->resolveEffectiveValue($key, $value, $schedulerConfig);
            $source = $this->hasOverride($key) ? 'override' : 'default';
            $item = [
                'key' => $key,
                'item_key' => (string) $definition['item_key'],
                'label' => (string) $definition['label'],
                'description' => (string) ($definition['description'] ?? ''),
                'value' => $effectiveValue,
                'default_value' => $definition['default'],
                'source' => $source,
                'editable' => (bool) ($definition['editable'] ?? false),
                'advanced' => (bool) ($definition['advanced'] ?? false),
                'type' => (string) $definition['type'],
                'input_type' => (string) ($definition['input_type'] ?? 'text'),
            ];

            if (array_key_exists('min', $definition)) {
                $item['min'] = $definition['min'];
            }
            if (array_key_exists('max', $definition)) {
                $item['max'] = $definition['max'];
            }
            if (array_key_exists('step', $definition)) {
                $item['step'] = $definition['step'];
            }
            if (array_key_exists('unit', $definition)) {
                $item['unit'] = $definition['unit'];
            }
            if (array_key_exists('options', $definition)) {
                $item['options'] = $definition['options'];
            }
            if (array_key_exists('option_labels', $definition)) {
                $item['option_labels'] = $definition['option_labels'];
            }

            $sections[$sectionKey]['items'][] = $item;
        }

        return [
            'generated_at' => CarbonImmutable::now('UTC')->toIso8601String(),
            'sections' => array_values($sections),
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public function editableSettingsMap(): array
    {
        $result = [];
        foreach (self::DEFINITIONS as $key => $definition) {
            if (! (bool) ($definition['editable'] ?? false)) {
                continue;
            }
            $result[$key] = $this->value($key, $definition['default']);
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $settings
     */
    public function applyOverrides(array $settings, ?int $userId = null): void
    {
        $errors = [];
        $mergedPayload = $this->loadOverrides();

        foreach ($settings as $key => $value) {
            $key = trim((string) $key);
            $definition = self::DEFINITIONS[$key] ?? null;
            if (! is_array($definition) || ! (bool) ($definition['editable'] ?? false)) {
                $errors["settings.{$key}"] = "Unknown or read-only setting key: {$key}";

                continue;
            }

            try {
                $normalized = $this->normalizeIncomingValue($key, $value, $definition);
            } catch (\InvalidArgumentException $e) {
                $errors["settings.{$key}"] = $e->getMessage();

                continue;
            }

            $mergedPayload[$key] = $normalized;
        }

        if (! empty($errors)) {
            throw ValidationException::withMessages($errors);
        }

        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            $mergedPayload,
            $userId,
            'runtime_settings'
        );
        $this->overrides = null;
    }

    public function resetOverrides(): void
    {
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            self::defaultSettingsMapStatic(),
            null,
            'runtime_settings_reset'
        );
        $this->overrides = null;
    }

    /**
     * @return array<string, mixed>
     */
    private function loadOverrides(): array
    {
        if ($this->overrides !== null) {
            return $this->overrides;
        }

        $document = app(AutomationConfigDocumentService::class)->getDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_RUNTIME,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            true
        );
        $payload = $document?->payload;
        $overrides = is_array($payload) && ! array_is_list($payload) ? $payload : [];

        if ($this->matchesDefaultOverrideMap($overrides)) {
            $overrides = [];
        }

        $this->overrides = $overrides;

        return $this->overrides;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function matchesDefaultOverrideMap(array $payload): bool
    {
        if ($payload === []) {
            return false;
        }

        $defaults = self::defaultSettingsMapStatic();
        if (count($payload) !== count($defaults)) {
            return false;
        }

        foreach ($defaults as $key => $defaultValue) {
            if (! array_key_exists($key, $payload)) {
                return false;
            }

            $definition = self::DEFINITIONS[$key] ?? null;
            if (! is_array($definition)) {
                return false;
            }

            $normalizedPayloadValue = $this->normalizeStoredValue($key, $payload[$key], $definition, $defaultValue, true);
            $normalizedDefaultValue = $this->normalizeStoredValue($key, $defaultValue, $definition, $defaultValue, true);

            if ($normalizedPayloadValue !== $normalizedDefaultValue) {
                return false;
            }
        }

        return true;
    }

    private function hasOverride(string $key): bool
    {
        $overrides = $this->loadOverrides();

        return array_key_exists($key, $overrides);
    }

    private function value(string $key, mixed $fallback = null): mixed
    {
        $definition = self::DEFINITIONS[$key] ?? null;
        if (! is_array($definition)) {
            return $fallback;
        }

        $default = array_key_exists('default', $definition) ? $definition['default'] : $fallback;
        $base = config((string) $definition['config_path'], $default);
        $overrides = $this->loadOverrides();

        if (! array_key_exists($key, $overrides)) {
            return $this->normalizeStoredValue($key, $base, $definition, $default);
        }

        return $this->normalizeStoredValue($key, $overrides[$key], $definition, $default, true);
    }

    private function stringValue(string $key, string $fallback): string
    {
        return (string) $this->value($key, $fallback);
    }

    private function intValue(string $key, int $fallback): int
    {
        return (int) $this->value($key, $fallback);
    }

    private function floatValue(string $key, float $fallback): float
    {
        return (float) $this->value($key, $fallback);
    }

    private function boolValue(string $key, bool $fallback): bool
    {
        return (bool) $this->value($key, $fallback);
    }

    private function resolveEffectiveValue(string $key, mixed $value, array $schedulerConfig): mixed
    {
        return match ($key) {
            'automation_engine.scheduler_due_grace_sec' => $schedulerConfig['due_grace_sec'],
            'automation_engine.scheduler_expires_after_sec' => $schedulerConfig['expires_after_sec'],
            'automation_engine.scheduler_hard_stale_after_sec' => $schedulerConfig['hard_stale_after_sec'],
            'automation_engine.scheduler_catchup_policy' => $schedulerConfig['catchup_policy'],
            'automation_engine.scheduler_catchup_max_windows' => $schedulerConfig['catchup_max_windows'],
            'automation_engine.scheduler_catchup_rate_limit_per_cycle' => $schedulerConfig['catchup_rate_limit_per_cycle'],
            'automation_engine.scheduler_dispatch_interval_sec' => $schedulerConfig['dispatch_interval_sec'],
            'automation_engine.scheduler_dispatch_parallelism' => $schedulerConfig['dispatch_parallelism'],
            'automation_engine.scheduler_lock_ttl_sec' => $schedulerConfig['lock_ttl_sec'],
            'automation_engine.scheduler_lock_ttl_margin_sec' => $schedulerConfig['lock_ttl_margin_sec'],
            'automation_engine.scheduler_active_task_ttl_sec' => $schedulerConfig['active_task_ttl_sec'],
            'automation_engine.scheduler_active_task_retention_days' => $schedulerConfig['active_task_retention_days'],
            'automation_engine.scheduler_active_task_cleanup_batch' => $schedulerConfig['active_task_cleanup_batch'],
            'automation_engine.scheduler_active_task_poll_batch' => $schedulerConfig['active_task_poll_batch'],
            default => $value,
        };
    }

    private function normalizeStoredValue(
        string $key,
        mixed $value,
        array $definition,
        mixed $fallback,
        bool $fromOverride = false
    ): mixed {
        $type = (string) ($definition['type'] ?? 'string');
        if ($type === 'token_presence') {
            return trim((string) $value);
        }

        if ($type === 'bool') {
            if (is_bool($value)) {
                return $value;
            }
            $string = strtolower(trim((string) $value));
            if (in_array($string, ['1', 'true', 'yes', 'on'], true)) {
                return true;
            }
            if (in_array($string, ['0', 'false', 'no', 'off'], true)) {
                return false;
            }

            return (bool) $fallback;
        }

        if ($type === 'int') {
            if (is_int($value)) {
                return $value;
            }
            if (is_numeric($value)) {
                return (int) $value;
            }

            return (int) $fallback;
        }

        if ($type === 'float') {
            if (is_float($value) || is_int($value)) {
                return (float) $value;
            }
            if (is_numeric($value)) {
                return (float) $value;
            }

            return (float) $fallback;
        }

        if ($type === 'enum') {
            $candidate = strtolower(trim((string) $value));
            $options = Arr::wrap($definition['options'] ?? []);
            if (in_array($candidate, $options, true)) {
                return $candidate;
            }

            return (string) $fallback;
        }

        $string = trim((string) $value);
        if ($key === 'automation_engine.api_url') {
            return rtrim($string, '/');
        }

        return $string !== '' || $fromOverride ? $string : (string) $fallback;
    }

    private function normalizeIncomingValue(string $key, mixed $value, array $definition): mixed
    {
        $normalized = $this->normalizeStoredValue($key, $value, $definition, $definition['default'], true);
        $type = (string) ($definition['type'] ?? 'string');

        if ($type === 'int' || $type === 'float') {
            if (array_key_exists('min', $definition) && $normalized < $definition['min']) {
                throw new \InvalidArgumentException('Value must be greater or equal to '.$definition['min']);
            }
            if (array_key_exists('max', $definition) && $normalized > $definition['max']) {
                throw new \InvalidArgumentException('Value must be less or equal to '.$definition['max']);
            }
        }

        if ($type === 'string' && $normalized === '') {
            throw new \InvalidArgumentException('Value cannot be empty');
        }

        if ($type === 'enum') {
            $options = Arr::wrap($definition['options'] ?? []);
            if (! in_array($normalized, $options, true)) {
                throw new \InvalidArgumentException('Unsupported enum value');
            }
        }

        return $normalized;
    }

    private function serializeStoredValue(string $key, mixed $value): string
    {
        $definition = self::DEFINITIONS[$key] ?? null;
        $type = is_array($definition) ? (string) ($definition['type'] ?? 'string') : 'string';

        return match ($type) {
            'bool' => $value ? '1' : '0',
            'int' => (string) (int) $value,
            'float' => (string) (float) $value,
            default => trim((string) $value),
        };
    }
}
