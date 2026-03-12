<?php

namespace Tests\Unit\AutomationScheduler;

use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\LightingScheduleParser;
use App\Services\AutomationScheduler\SchedulerCycleService;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Mockery;
use ReflectionClass;
use Tests\TestCase;

class DispatchesAutomationSchedulesTest extends TestCase
{
    private SchedulerCycleService $service;

    private ReflectionClass $reflection;

    protected function setUp(): void
    {
        parent::setUp();

        $activeTaskStore = new ActiveTaskStore;
        $this->service = new SchedulerCycleService(
            effectiveTargetsService: Mockery::mock(EffectiveTargetsService::class),
            activeTaskStore: $activeTaskStore,
            zoneCursorStore: new ZoneCursorStore,
            lightingScheduleParser: new LightingScheduleParser,
            activeTaskPoller: new ActiveTaskPoller($activeTaskStore),
        );
        $this->reflection = new ReflectionClass($this->service);
    }

    public function test_to_iso_adds_utc_suffix(): void
    {
        $value = CarbonImmutable::parse('2026-03-03 10:15:20', 'UTC');
        $iso = $this->invokePrivateMethod('toIso', [$value]);

        $this->assertSame('2026-03-03T10:15:20Z', $iso);
    }

    /**
     * @param  array<int, mixed>  $args
     */
    private function invokePrivateMethod(string $method, array $args = []): mixed
    {
        $refMethod = $this->reflection->getMethod($method);
        $refMethod->setAccessible(true);

        return $refMethod->invokeArgs($this->service, $args);
    }
}
