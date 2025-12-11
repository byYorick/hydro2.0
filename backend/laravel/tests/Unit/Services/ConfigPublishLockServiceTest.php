<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Services\ConfigPublishLockService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Tests\TestCase;

class ConfigPublishLockServiceTest extends TestCase
{
    use RefreshDatabase;

    private ConfigPublishLockService $service;

    protected function setUp(): void
    {
        parent::setUp();
        
        $this->service = new ConfigPublishLockService();
        Cache::flush();
    }

    public function test_acquire_optimistic_lock_returns_node_and_version(): void
    {
        $node = DeviceNode::factory()->create();
        
        $lock = $this->service->acquireOptimisticLock($node);

        $this->assertNotNull($lock);
        $this->assertArrayHasKey('node', $lock);
        $this->assertArrayHasKey('version', $lock);
        $this->assertInstanceOf(DeviceNode::class, $lock['node']);
        $this->assertIsInt($lock['version']);
    }

    public function test_check_optimistic_lock_returns_true_when_version_unchanged(): void
    {
        $node = DeviceNode::factory()->create();
        $lock = $this->service->acquireOptimisticLock($node);
        
        $isValid = $this->service->checkOptimisticLock($node, $lock['version']);

        $this->assertTrue($isValid);
    }

    public function test_check_optimistic_lock_returns_false_when_version_changed(): void
    {
        $node = DeviceNode::factory()->create();
        $lock = $this->service->acquireOptimisticLock($node);
        
        // Simulate node update - обновляем в БД с небольшой задержкой
        // чтобы гарантировать изменение timestamp
        sleep(1);
        $node->touch();
        $node->refresh(); // Обновляем модель из БД, чтобы получить новую версию
        
        $isValid = $this->service->checkOptimisticLock($node, $lock['version']);

        $this->assertFalse($isValid);
    }

    public function test_is_duplicate_returns_false_for_new_config(): void
    {
        $node = DeviceNode::factory()->create();
        $configHash = hash('sha256', 'test_config');

        $isDuplicate = $this->service->isDuplicate($node, $configHash);

        $this->assertFalse($isDuplicate);
    }

    public function test_is_duplicate_returns_true_for_published_config(): void
    {
        $node = DeviceNode::factory()->create();
        $configHash = hash('sha256', 'test_config');
        
        $this->service->markAsPublished($node, $configHash);
        
        $isDuplicate = $this->service->isDuplicate($node, $configHash);

        $this->assertTrue($isDuplicate);
    }

    public function test_mark_as_published_stores_config_hash_in_cache(): void
    {
        $node = DeviceNode::factory()->create();
        $configHash = hash('sha256', 'test_config');
        
        $this->service->markAsPublished($node, $configHash, 60);
        
        $cacheKey = "config_publish:{$node->id}:{$configHash}";
        $this->assertTrue(Cache::has($cacheKey));
    }
}

