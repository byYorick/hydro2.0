<?php

namespace App\Services;

use Illuminate\Support\Facades\Log;

class ErrorCodeCatalogService
{
    /**
     * @var array<int, array<string, mixed>>|null
     */
    private static ?array $cachedCodes = null;

    /**
     * @var array<string, array<string, mixed>>|null
     */
    private static ?array $cachedByCode = null;

    /**
     * @return array{code:?string,title:string,message:?string}
     */
    public function present(?string $code, ?string $message = null): array
    {
        $normalizedCode = $this->normalizeCode($code);
        $entry = $normalizedCode !== '' ? ($this->codesByCode()[$normalizedCode] ?? null) : null;

        return [
            'code' => $normalizedCode !== '' ? $normalizedCode : null,
            'title' => is_array($entry) && is_string($entry['title'] ?? null) && trim($entry['title']) !== ''
                ? trim((string) $entry['title'])
                : 'Системная ошибка',
            'message' => $this->resolveMessage($normalizedCode, $message, $entry),
        ];
    }

    public function normalizeCode(?string $code): string
    {
        $normalized = strtolower(trim((string) ($code ?? '')));
        if ($normalized === '') {
            return '';
        }

        return preg_replace('/[^a-z0-9_\-]/', '_', $normalized) ?? $normalized;
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    private function codesByCode(): array
    {
        if (self::$cachedByCode !== null) {
            return self::$cachedByCode;
        }

        $this->loadCatalog();

        return self::$cachedByCode ?? [];
    }

    /**
     * @return array<int, array<string, mixed>>
     */
    private function loadCatalog(): array
    {
        if (self::$cachedCodes !== null) {
            return self::$cachedCodes;
        }

        $candidatePaths = [
            base_path('error_codes.json'),
            base_path('../error_codes.json'),
            base_path('../../error_codes.json'),
        ];

        $path = null;
        foreach ($candidatePaths as $candidatePath) {
            if (is_file($candidatePath)) {
                $path = $candidatePath;
                break;
            }
        }

        if (! is_string($path)) {
            Log::warning('Error code catalog file not found', ['paths' => $candidatePaths]);
            self::$cachedCodes = [];
            self::$cachedByCode = [];

            return [];
        }

        $raw = file_get_contents($path);
        $decoded = is_string($raw) ? json_decode($raw, true) : null;
        $codes = is_array($decoded['codes'] ?? null) ? $decoded['codes'] : [];

        $normalizedCodes = [];
        $byCode = [];

        foreach ($codes as $row) {
            if (! is_array($row)) {
                continue;
            }

            $normalizedCode = $this->normalizeCode($row['code'] ?? null);
            if ($normalizedCode === '') {
                continue;
            }

            $normalizedRow = [
                'code' => $normalizedCode,
                'title' => trim((string) ($row['title'] ?? '')),
                'message' => trim((string) ($row['message'] ?? '')),
            ];

            $normalizedCodes[] = $normalizedRow;
            $byCode[$normalizedCode] = $normalizedRow;
        }

        self::$cachedCodes = $normalizedCodes;
        self::$cachedByCode = $byCode;

        return $normalizedCodes;
    }

    /**
     * @param  array<string, mixed>|null  $entry
     */
    private function resolveMessage(string $code, ?string $message, ?array $entry): ?string
    {
        $rawMessage = trim((string) ($message ?? ''));

        if ($rawMessage !== '' && $this->looksLocalized($rawMessage)) {
            return $rawMessage;
        }

        if (is_array($entry) && is_string($entry['message'] ?? null) && trim((string) $entry['message']) !== '') {
            return trim((string) $entry['message']);
        }

        if ($rawMessage !== '') {
            $translated = $this->translateRawMessage($rawMessage);
            if ($translated !== null) {
                return $translated;
            }
        }

        if ($code !== '') {
            return sprintf('Внутренняя ошибка системы (код: %s).', $code);
        }

        if ($rawMessage !== '') {
            return 'Произошла ошибка сервиса. Проверьте логи и повторите попытку.';
        }

        return null;
    }

    private function translateRawMessage(string $message): ?string
    {
        $exactMap = [
            'Intent skipped: zone busy' => 'Повторный запуск отклонён: зона уже занята активной задачей.',
            'Task execution exceeded runtime timeout' => 'Выполнение задачи превысило допустимый runtime timeout.',
            'Execution not found' => 'Запрошенное выполнение не найдено.',
            'Command not found' => 'Запрошенная команда не найдена.',
            'Access denied' => 'У вас нет прав для доступа к этому объекту.',
            'Authentication required' => 'Для выполнения действия нужно войти в систему.',
            'Unauthorized' => 'Для выполнения действия нужно войти в систему.',
            'Forbidden' => 'У вас нет прав для выполнения этого действия.',
            'Not found' => 'Запрошенный объект не найден.',
            'Validation failed' => 'Проверьте корректность переданных данных.',
            'TIMEOUT' => 'Превышено время ожидания выполнения команды.',
            'SEND_FAILED' => 'Команду не удалось отправить до узла.',
        ];

        if (isset($exactMap[$message])) {
            return $exactMap[$message];
        }

        if (preg_match('/^Zone \d+ has no online actuator channels$/i', $message) === 1) {
            return 'В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.';
        }

        return null;
    }

    private function looksLocalized(string $value): bool
    {
        return preg_match('/[А-Яа-яЁё]/u', $value) === 1;
    }
}
