<?php

namespace App\Services;

use App\Models\DeviceNode;
use Illuminate\Support\Facades\Log;

/**
 * Per-node HMAC secrets (nodes.config.node_secret).
 *
 * Production: fail-closed — only the per-node secret is accepted (no app.key fallback).
 * Local/testing: legacy fallback to NODE_DEFAULT_SECRET / APP_KEY with WARN.
 */
class NodeSecretService
{
    /**
     * Cryptographically secure 32-byte secret as lowercase hex (64 chars).
     */
    public function generate(): string
    {
        return bin2hex(random_bytes(32));
    }

    /**
     * Ensure nodes.config.node_secret exists on the model (mutates, does not save).
     *
     * @return string The existing or newly generated secret
     */
    public function ensureOnNode(DeviceNode $node): string
    {
        $config = is_array($node->config) ? $node->config : [];
        $existing = $config['node_secret'] ?? null;

        if (is_string($existing) && $existing !== '') {
            return $existing;
        }

        $secret = $this->generate();
        $config['node_secret'] = $secret;
        $node->config = $config;

        Log::info('Generated per-node node_secret', [
            'node_id' => $node->id,
            'node_uid' => $node->uid,
        ]);

        return $secret;
    }

    /**
     * Resolve HMAC secret for a node.
     *
     * Order: nodes.config.node_secret → (non-production only) NODE_DEFAULT_SECRET / APP_KEY.
     */
    public function resolve(DeviceNode $node): ?string
    {
        $config = is_array($node->config) ? $node->config : [];
        $secret = $config['node_secret'] ?? null;

        if (is_string($secret) && $secret !== '') {
            return $secret;
        }

        if ($this->isProductionLike()) {
            Log::error('Node secret missing in production (fail-closed, no app.key fallback)', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
            ]);

            return null;
        }

        $fallback = config('app.node_default_secret');
        if (! is_string($fallback) || $fallback === '') {
            $fallback = config('app.key');
        }

        if (! is_string($fallback) || $fallback === '') {
            return null;
        }

        Log::warning('Using legacy node secret fallback (dev/testing only)', [
            'node_id' => $node->id,
            'node_uid' => $node->uid,
            'fallback_source' => config('app.node_default_secret') ? 'node_default_secret' : 'app.key',
        ]);

        return $fallback;
    }

    private function isProductionLike(): bool
    {
        return app()->environment('production', 'prod');
    }
}
