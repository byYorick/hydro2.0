<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Services\ConfigSignatureService;
use Tests\TestCase;

class ConfigSignatureServiceTest extends TestCase
{

    private ConfigSignatureService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new ConfigSignatureService();
    }

    public function test_sign_config_adds_timestamp_and_signature(): void
    {
        // Создаем минимальную модель узла без сохранения в БД
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-test-001',
            'type' => 'ph',
        ]);
        $config = [
            'node_id' => $node->uid,
            'version' => 3,
        ];

        $signedConfig = $this->service->signConfig($node, $config);

        $this->assertArrayHasKey('ts', $signedConfig);
        $this->assertArrayHasKey('sig', $signedConfig);
        $this->assertIsInt($signedConfig['ts']);
        $this->assertIsString($signedConfig['sig']);
        $this->assertEquals(64, strlen($signedConfig['sig'])); // SHA256 hex length
    }

    public function test_verify_signature_returns_true_for_valid_signature(): void
    {
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-test-001',
            'type' => 'ph',
        ]);
        $config = [
            'node_id' => $node->uid,
            'version' => 3,
        ];

        $signedConfig = $this->service->signConfig($node, $config);
        $isValid = $this->service->verifySignature($node, $signedConfig);

        $this->assertTrue($isValid);
    }

    public function test_verify_signature_returns_false_for_invalid_signature(): void
    {
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-test-001',
            'type' => 'ph',
        ]);
        $config = [
            'node_id' => $node->uid,
            'version' => 3,
            'ts' => time(),
            'sig' => 'invalid_signature',
        ];

        $isValid = $this->service->verifySignature($node, $config);

        $this->assertFalse($isValid);
    }

    public function test_verify_signature_returns_false_for_expired_timestamp(): void
    {
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-test-001',
            'type' => 'ph',
        ]);
        $config = [
            'node_id' => $node->uid,
            'version' => 3,
            'ts' => time() - 120, // 2 minutes ago (expired)
            'sig' => 'some_signature',
        ];

        $isValid = $this->service->verifySignature($node, $config);

        $this->assertFalse($isValid);
    }

    public function test_verify_signature_returns_false_for_missing_fields(): void
    {
        $node = new DeviceNode([
            'id' => 1,
            'uid' => 'nd-test-001',
            'type' => 'ph',
        ]);
        $config = [
            'node_id' => $node->uid,
            'version' => 3,
            // Missing ts and sig
        ];

        $isValid = $this->service->verifySignature($node, $config);

        $this->assertFalse($isValid);
    }
}

