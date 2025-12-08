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

        $payload = $cmd . '|' . $timestamp;
        $signature = hash_hmac('sha256', $payload, $secret);

        $signedCommand = array_merge($command, [
            'ts' => $timestamp,
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

        $payload = $cmd . '|' . $timestamp;
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

