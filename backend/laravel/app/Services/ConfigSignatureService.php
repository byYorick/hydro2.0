<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\Log;

class ConfigSignatureService
{
    /**
     * Подписать конфигурацию узла HMAC подписью с timestamp.
     * 
     * @param DeviceNode $node Узел, для которого подписывается конфиг
     * @param array $config Конфигурация для подписи
     * @return array Конфигурация с добавленными полями 'ts' и 'sig'
     */
    public function signConfig(DeviceNode $node, array $config): array
    {
        $timestamp = now()->timestamp;
        $secret = $this->getNodeSecret($node);

        if (!$secret) {
            throw new \RuntimeException('Node secret not configured. Cannot sign config.');
        }

        // Создаем строку для подписи: node_uid|version|timestamp
        $nodeUid = $config['node_id'] ?? $config['node_uid'] ?? $node->uid;
        $version = $config['version'] ?? 1;
        $payload = $nodeUid . '|' . $version . '|' . $timestamp;
        $signature = hash_hmac('sha256', $payload, $secret);

        $signedConfig = array_merge($config, [
            'ts' => $timestamp,
            'sig' => $signature,
        ]);

        Log::debug('Config signed', [
            'node_id' => $node->id,
            'node_uid' => $nodeUid,
            'version' => $version,
            'timestamp' => $timestamp,
        ]);

        return $signedConfig;
    }

    /**
     * Проверить HMAC подпись конфигурации.
     * 
     * @param DeviceNode $node Узел, для которого проверяется конфиг
     * @param array $config Конфигурация с полями 'ts', 'sig', 'node_id'/'node_uid', 'version'
     * @return bool true если подпись валидна, false иначе
     */
    public function verifySignature(DeviceNode $node, array $config): bool
    {
        $secret = $this->getNodeSecret($node);
        $timestamp = $config['ts'] ?? null;
        $signature = $config['sig'] ?? null;
        $nodeUid = $config['node_id'] ?? $config['node_uid'] ?? $node->uid;
        $version = $config['version'] ?? 1;

        if (!$timestamp || !$signature) {
            Log::warning('Config signature verification failed: missing fields', [
                'node_id' => $node->id,
                'node_uid' => $nodeUid,
                'has_ts' => !is_null($timestamp),
                'has_sig' => !is_null($signature),
            ]);
            return false;
        }

        if (!$secret) {
            Log::warning('Config signature verification failed: node secret not configured', [
                'node_id' => $node->id,
                'node_uid' => $nodeUid,
            ]);
            return false;
        }

        // Проверка timestamp (не старше 60 секунд для конфигов)
        $now = now()->timestamp;
        if (abs($now - $timestamp) > 60) {
            Log::warning('Config signature verification failed: timestamp expired', [
                'node_id' => $node->id,
                'node_uid' => $nodeUid,
                'timestamp' => $timestamp,
                'now' => $now,
                'diff' => abs($now - $timestamp),
            ]);
            return false;
        }

        $payload = $nodeUid . '|' . $version . '|' . $timestamp;
        $expectedSignature = hash_hmac('sha256', $payload, $secret);

        $isValid = hash_equals($expectedSignature, $signature);

        if (!$isValid) {
            Log::warning('Config signature verification failed: signature mismatch', [
                'node_id' => $node->id,
                'node_uid' => $nodeUid,
                'version' => $version,
            ]);
        }

        return $isValid;
    }

    /**
     * Получить секрет узла для подписи конфигураций.
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

