<?php

namespace App\Services;

use App\Models\AutomationRuntimeOverride;
use Carbon\CarbonImmutable;
use Illuminate\Support\Arr;
use Illuminate\Validation\ValidationException;

class AutomationRuntimeConfigService
{
    private const KNOWN_CATCHUP_POLICIES = ['replay_limited', 'skip'];

    /**
     * @var array<string, array<string, mixed>>
     */
    private const DEFINITIONS = [
        'automation_engine.api_url' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'api_url',
            'label' => 'Automation Engine API URL',
            'description' => 'Базовый URL AE runtime API.',
            'config_path' => 'services.automation_engine.api_url',
            'default' => 'http://automation-engine:9405',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
        ],
        'automation_engine.timeout' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'timeout_sec',
            'label' => 'HTTP timeout (sec)',
            'description' => 'Таймаут запросов Laravel -> AE.',
            'config_path' => 'services.automation_engine.timeout',
            'default' => 2.0,
            'type' => 'float',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1.0,
            'step' => 0.1,
            'unit' => 'sec',
        ],
        'automation_engine.laravel_scheduler_enabled' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'laravel_scheduler_enabled',
            'label' => 'Laravel scheduler enabled',
            'description' => 'Главный флаг запуска dispatcher.',
            'config_path' => 'services.automation_engine.laravel_scheduler_enabled',
            'default' => false,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
        ],
        'automation_engine.scheduler_id' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'scheduler_id',
            'label' => 'Scheduler ID',
            'description' => 'Идентификатор источника в заголовках.',
            'config_path' => 'services.automation_engine.scheduler_id',
            'default' => 'laravel-scheduler',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
        ],
        'automation_engine.scheduler_version' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'scheduler_version',
            'label' => 'Scheduler version',
            'description' => 'Версия отправителя scheduler.',
            'config_path' => 'services.automation_engine.scheduler_version',
            'default' => '3.0.0',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
        ],
        'automation_engine.scheduler_protocol_version' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'scheduler_protocol_version',
            'label' => 'Protocol version',
            'description' => 'Версия протокола scheduler -> AE.',
            'config_path' => 'services.automation_engine.scheduler_protocol_version',
            'default' => '2.0',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
        ],
        'automation_engine.scheduler_api_token' => [
            'section_key' => 'transport',
            'section_title' => 'Связь Laravel ↔ automation-engine',
            'item_key' => 'scheduler_api_token_configured',
            'label' => 'Scheduler API token configured',
            'description' => 'Показывается только факт наличия токена.',
            'config_path' => 'services.automation_engine.scheduler_api_token',
            'default' => '',
            'type' => 'token_presence',
            'input_type' => 'readonly',
            'editable' => false,
        ],
        'automation_engine.grow_cycle_start_dispatch_enabled' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'grow_cycle_start_dispatch_enabled',
            'label' => 'Grow-cycle auto dispatch enabled',
            'description' => 'Автозапуск start-cycle при старте grow-cycle.',
            'config_path' => 'services.automation_engine.grow_cycle_start_dispatch_enabled',
            'default' => false,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
        ],
        'automation_engine.scheduler_due_grace_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_due_grace_sec',
            'label' => 'due_grace_sec',
            'description' => 'Допуск до due_at.',
            'config_path' => 'services.automation_engine.scheduler_due_grace_sec',
            'default' => 15,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'sec',
        ],
        'automation_engine.scheduler_expires_after_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_expires_after_sec',
            'label' => 'expires_after_sec',
            'description' => 'Локальный expiry активной scheduler-task.',
            'config_path' => 'services.automation_engine.scheduler_expires_after_sec',
            'default' => 120,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 2,
            'unit' => 'sec',
        ],
        'automation_engine.scheduler_catchup_policy' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_catchup_policy',
            'label' => 'catchup_policy',
            'description' => 'Стратегия catchup при пропусках окон.',
            'config_path' => 'services.automation_engine.scheduler_catchup_policy',
            'default' => 'replay_limited',
            'type' => 'enum',
            'input_type' => 'select',
            'editable' => true,
            'options' => ['replay_limited', 'skip'],
        ],
        'automation_engine.scheduler_catchup_max_windows' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_catchup_max_windows',
            'label' => 'catchup_max_windows',
            'description' => 'Максимум окон catchup за итерацию.',
            'config_path' => 'services.automation_engine.scheduler_catchup_max_windows',
            'default' => 3,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
        ],
        'automation_engine.scheduler_catchup_rate_limit_per_cycle' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_catchup_rate_limit_per_cycle',
            'label' => 'catchup_rate_limit_per_cycle',
            'description' => 'Лимит dispatch событий catchup за цикл.',
            'config_path' => 'services.automation_engine.scheduler_catchup_rate_limit_per_cycle',
            'default' => 20,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
        ],
        'automation_engine.scheduler_dispatch_interval_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_dispatch_interval_sec',
            'label' => 'dispatch_interval_sec',
            'description' => 'Шаг циклического dispatcher.',
            'config_path' => 'services.automation_engine.scheduler_dispatch_interval_sec',
            'default' => 60,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 10,
            'unit' => 'sec',
        ],
        'automation_engine.scheduler_lock_key' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_lock_key',
            'label' => 'lock_key',
            'description' => 'Ключ distributed-lock dispatcher.',
            'config_path' => 'services.automation_engine.scheduler_lock_key',
            'default' => 'automation:dispatch-schedules',
            'type' => 'string',
            'input_type' => 'text',
            'editable' => true,
        ],
        'automation_engine.scheduler_lock_ttl_sec' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_lock_ttl_sec',
            'label' => 'lock_ttl_sec',
            'description' => 'TTL lock dispatcher.',
            'config_path' => 'services.automation_engine.scheduler_lock_ttl_sec',
            'default' => 55,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 10,
            'unit' => 'sec',
        ],
        'automation_engine.scheduler_active_task_ttl_sec' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_active_task_ttl_sec',
            'label' => 'active_task_ttl_sec',
            'description' => 'TTL active task в хранилище scheduler.',
            'config_path' => 'services.automation_engine.scheduler_active_task_ttl_sec',
            'default' => 180,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 30,
            'unit' => 'sec',
        ],
        'automation_engine.scheduler_active_task_retention_days' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_active_task_retention_days',
            'label' => 'active_task_retention_days',
            'description' => 'Сколько хранить terminal active task.',
            'config_path' => 'services.automation_engine.scheduler_active_task_retention_days',
            'default' => 60,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'days',
        ],
        'automation_engine.scheduler_active_task_cleanup_batch' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_active_task_cleanup_batch',
            'label' => 'active_task_cleanup_batch',
            'description' => 'Batch cleanup terminal active tasks.',
            'config_path' => 'services.automation_engine.scheduler_active_task_cleanup_batch',
            'default' => 500,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
        ],
        'automation_engine.scheduler_active_task_poll_batch' => [
            'section_key' => 'scheduler_runtime',
            'section_title' => 'Laravel scheduler runtime',
            'item_key' => 'scheduler_active_task_poll_batch',
            'label' => 'active_task_poll_batch',
            'description' => 'Batch polling active tasks.',
            'config_path' => 'services.automation_engine.scheduler_active_task_poll_batch',
            'default' => 500,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
        ],
        'automation_engine.scheduler_cursor_persist_enabled' => [
            'section_key' => 'scheduler_catchup_and_lock',
            'section_title' => 'Catchup, lock и cursor',
            'item_key' => 'scheduler_cursor_persist_enabled',
            'label' => 'cursor_persist_enabled',
            'description' => 'Persist scheduler cursor между итерациями.',
            'config_path' => 'services.automation_engine.scheduler_cursor_persist_enabled',
            'default' => true,
            'type' => 'bool',
            'input_type' => 'boolean',
            'editable' => true,
        ],
        'python_bridge.timeout' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Python bridge (related retries/timeouts)',
            'item_key' => 'python_timeout_sec',
            'label' => 'Python bridge timeout (sec)',
            'description' => 'Timeout Laravel -> python bridge.',
            'config_path' => 'services.python_bridge.timeout',
            'default' => 10,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 1,
            'unit' => 'sec',
        ],
        'python_bridge.retry_attempts' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Python bridge (related retries/timeouts)',
            'item_key' => 'python_retry_attempts',
            'label' => 'Python bridge retry attempts',
            'description' => 'Количество retry для bridge запросов.',
            'config_path' => 'services.python_bridge.retry_attempts',
            'default' => 2,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 0,
        ],
        'python_bridge.retry_delay' => [
            'section_key' => 'python_bridge',
            'section_title' => 'Python bridge (related retries/timeouts)',
            'item_key' => 'python_retry_delay_sec',
            'label' => 'Python bridge retry delay (sec)',
            'description' => 'Пауза между retry попытками bridge.',
            'config_path' => 'services.python_bridge.retry_delay',
            'default' => 1,
            'type' => 'int',
            'input_type' => 'number',
            'editable' => true,
            'min' => 0,
            'unit' => 'sec',
        ],
    ];

    /**
     * @var array<string, string>|null
     */
    private ?array $overrides = null;

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
        $expiresAfterSec = max($dueGraceSec + 1, $this->intValue('automation_engine.scheduler_expires_after_sec', 120));

        $catchupPolicy = strtolower($this->stringValue('automation_engine.scheduler_catchup_policy', 'replay_limited'));
        if (! in_array($catchupPolicy, self::KNOWN_CATCHUP_POLICIES, true)) {
            $catchupPolicy = 'replay_limited';
        }

        return [
            'api_url' => rtrim($this->stringValue('automation_engine.api_url', 'http://automation-engine:9405'), '/'),
            'timeout_sec' => max(1.0, $this->floatValue('automation_engine.timeout', 2.0)),
            'scheduler_id' => $this->stringValue('automation_engine.scheduler_id', 'laravel-scheduler'),
            'scheduler_version' => $this->stringValue('automation_engine.scheduler_version', '3.0.0'),
            'protocol_version' => $this->stringValue('automation_engine.scheduler_protocol_version', '2.0'),
            'token' => trim($this->stringValue('automation_engine.scheduler_api_token', '')),
            'due_grace_sec' => $dueGraceSec,
            'expires_after_sec' => $expiresAfterSec,
            'catchup_policy' => $catchupPolicy,
            'catchup_max_windows' => max(1, $this->intValue('automation_engine.scheduler_catchup_max_windows', 3)),
            'catchup_rate_limit_per_cycle' => max(1, $this->intValue('automation_engine.scheduler_catchup_rate_limit_per_cycle', 20)),
            'dispatch_interval_sec' => max(10, $this->intValue('automation_engine.scheduler_dispatch_interval_sec', 60)),
            'lock_key' => $this->stringValue('automation_engine.scheduler_lock_key', 'automation:dispatch-schedules'),
            'lock_ttl_sec' => max(10, $this->intValue('automation_engine.scheduler_lock_ttl_sec', 55)),
            'active_task_ttl_sec' => max(30, $this->intValue('automation_engine.scheduler_active_task_ttl_sec', $expiresAfterSec)),
            'active_task_retention_days' => max(1, $this->intValue('automation_engine.scheduler_active_task_retention_days', 60)),
            'active_task_cleanup_batch' => max(1, $this->intValue('automation_engine.scheduler_active_task_cleanup_batch', 500)),
            'active_task_poll_batch' => max(1, $this->intValue('automation_engine.scheduler_active_task_poll_batch', 500)),
            'cursor_persist_enabled' => $this->boolValue('automation_engine.scheduler_cursor_persist_enabled', true),
        ];
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
        $rows = [];
        $now = now();

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

            $rows[] = [
                'key' => $key,
                'value' => $this->serializeStoredValue($key, $normalized),
                'updated_by' => $userId,
                'created_at' => $now,
                'updated_at' => $now,
            ];
        }

        if (! empty($errors)) {
            throw ValidationException::withMessages($errors);
        }

        if (! empty($rows)) {
            AutomationRuntimeOverride::query()->upsert($rows, ['key'], ['value', 'updated_by', 'updated_at']);
        }
        $this->overrides = null;
    }

    public function resetOverrides(): void
    {
        AutomationRuntimeOverride::query()->delete();
        $this->overrides = null;
    }

    /**
     * @return array<string, string>
     */
    private function loadOverrides(): array
    {
        if ($this->overrides !== null) {
            return $this->overrides;
        }

        $this->overrides = AutomationRuntimeOverride::query()
            ->pluck('value', 'key')
            ->mapWithKeys(static fn ($value, $key) => [(string) $key => (string) $value])
            ->all();

        return $this->overrides;
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
            'automation_engine.scheduler_catchup_policy' => $schedulerConfig['catchup_policy'],
            'automation_engine.scheduler_catchup_max_windows' => $schedulerConfig['catchup_max_windows'],
            'automation_engine.scheduler_catchup_rate_limit_per_cycle' => $schedulerConfig['catchup_rate_limit_per_cycle'],
            'automation_engine.scheduler_dispatch_interval_sec' => $schedulerConfig['dispatch_interval_sec'],
            'automation_engine.scheduler_lock_ttl_sec' => $schedulerConfig['lock_ttl_sec'],
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

