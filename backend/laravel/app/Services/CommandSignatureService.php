<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\Log;

class CommandSignatureService
{
    /**
     * Подписать команду HMAC подписью.
     * 
     * @param DeviceNode $node Узел, для которого подписывается команда
     * @param array $command Команда для подписи (должна содержать 'cmd')
     * @return array Команда с добавленными полями 'ts' и 'sig'
     */
    public function signCommand(DeviceNode $node, array $command): array
    {
        $timestamp = now()->timestamp;
        $secret = $this->getNodeSecret($node);

        if (!$secret) {
            throw new \RuntimeException('Node secret not configured. Cannot sign command.');
        }

        $cmd = $command['cmd'] ?? $command['type'] ?? '';
        if (empty($cmd)) {
            throw new \InvalidArgumentException('Command must contain "cmd" or "type" field');
        }

        $command['ts'] = $timestamp;

        $payload = $this->buildCanonicalPayload($command);
        $signature = hash_hmac('sha256', $payload, $secret);

        $signedCommand = array_merge($command, [
            'sig' => $signature,
        ]);

        Log::debug('Command signed', [
            'node_id' => $node->id,
            'node_uid' => $node->uid,
            'cmd' => $cmd,
            'timestamp' => $timestamp,
        ]);

        return $signedCommand;
    }

    /**
     * Проверить HMAC подпись команды.
     * 
     * @param DeviceNode $node Узел, для которого проверяется команда
     * @param array $command Команда с полями 'cmd', 'ts', 'sig'
     * @return bool true если подпись валидна, false иначе
     */
    public function verifySignature(DeviceNode $node, array $command): bool
    {
        $secret = $this->getNodeSecret($node);
        $timestamp = $command['ts'] ?? null;
        $signature = $command['sig'] ?? null;
        $cmd = $command['cmd'] ?? $command['type'] ?? '';

        if (!$timestamp || !$signature || empty($cmd)) {
            Log::warning('Command signature verification failed: missing fields', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'has_ts' => !is_null($timestamp),
                'has_sig' => !is_null($signature),
                'has_cmd' => !empty($cmd),
            ]);
            return false;
        }

        if (!$secret) {
            Log::warning('Command signature verification failed: node secret not configured', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
            ]);
            return false;
        }

        // Проверка timestamp (не старше 30 секунд)
        $now = now()->timestamp;
        if (abs($now - $timestamp) > 30) {
            Log::warning('Command signature verification failed: timestamp expired', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'timestamp' => $timestamp,
                'now' => $now,
                'diff' => abs($now - $timestamp),
            ]);
            return false;
        }

        $payload = $this->buildCanonicalPayload($command);
        $expectedSignature = hash_hmac('sha256', $payload, $secret);

        $isValid = hash_equals($expectedSignature, $signature);

        if (!$isValid) {
            Log::warning('Command signature verification failed: signature mismatch', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'cmd' => $cmd,
            ]);
        }

        return $isValid;
    }

    private function buildCanonicalPayload(array $command): string
    {
        if (array_key_exists('sig', $command)) {
            unset($command['sig']);
        }

        $canonical = $this->canonicalizeValue($command);
        return $this->encodeCanonical($canonical);
    }

    private function canonicalizeValue($value)
    {
        if (is_array($value)) {
            if ($this->isList($value)) {
                $result = [];
                foreach ($value as $item) {
                    $result[] = $this->canonicalizeValue($item);
                }
                return $result;
            }

            $keys = array_keys($value);
            sort($keys, SORT_STRING);
            $result = [];
            foreach ($keys as $key) {
                $result[$key] = $this->canonicalizeValue($value[$key]);
            }
            return $result;
        }

        return $value;
    }

    private function encodeCanonical($value): string
    {
        if (is_null($value)) {
            return 'null';
        }

        if (is_bool($value)) {
            return $value ? 'true' : 'false';
        }

        if (is_int($value)) {
            return (string) $value;
        }

        if (is_float($value)) {
            return $this->formatNumber($value);
        }

        if (is_string($value)) {
            $encoded = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            if ($encoded === false) {
                throw new \RuntimeException('Failed to encode command string for signature');
            }
            return $encoded;
        }

        if (is_array($value)) {
            if ($this->isList($value)) {
                $items = [];
                foreach ($value as $item) {
                    $items[] = $this->encodeCanonical($item);
                }
                return '[' . implode(',', $items) . ']';
            }

            $items = [];
            foreach ($value as $key => $item) {
                $encodedKey = json_encode((string) $key, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
                if ($encodedKey === false) {
                    throw new \RuntimeException('Failed to encode command key for signature');
                }
                $items[] = $encodedKey . ':' . $this->encodeCanonical($item);
            }
            return '{' . implode(',', $items) . '}';
        }

        throw new \InvalidArgumentException('Unsupported command payload type for signature');
    }

    private function formatNumber(float $value): string
    {
        if (is_nan($value) || is_infinite($value)) {
            return 'null';
        }

        if ((float) (int) $value === $value) {
            return (string) (int) $value;
        }

        $formatted = sprintf('%.15g', $value);
        $formatted = str_replace(',', '.', $formatted);

        $test = (float) $formatted;
        if (!$this->compareDouble($test, $value)) {
            $formatted = sprintf('%.17g', $value);
            $formatted = str_replace(',', '.', $formatted);
        }

        return strtolower($formatted);
    }

    private function compareDouble(float $a, float $b): bool
    {
        $max = max(abs($a), abs($b));
        return abs($a - $b) <= $max * PHP_FLOAT_EPSILON;
    }

    private function isList(array $value): bool
    {
        $expected = 0;
        foreach ($value as $key => $unused) {
            if ((string) $key !== (string) $expected) {
                return false;
            }
            $expected++;
        }
        return true;
    }

    /**
     * Получить секрет узла для подписи команд.
     * 
     * @param DeviceNode $node
     * @return string|null
     */
    private function getNodeSecret(DeviceNode $node): ?string
    {
        // В будущем можно добавить поле secret в таблицу nodes
        // Пока используем общий секрет из конфигурации
        return config('app.node_default_secret') ?? config('app.key');
    }
}
