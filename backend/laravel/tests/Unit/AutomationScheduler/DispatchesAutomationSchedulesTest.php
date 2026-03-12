<?php

namespace Tests\Unit\AutomationScheduler;

use App\Services\AutomationScheduler\ActiveTaskPoller;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\LightingScheduleParser;
use App\Services\AutomationScheduler\SchedulerCycleOrchestrator;
use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use App\Services\AutomationScheduler\ScheduleLoader;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Mockery;
use ReflectionClass;
use Tests\TestCase;

class DispatchesAutomationSchedulesTest extends TestCase
{
    private SchedulerCycleOrchestrator $orchestrator;

    private ReflectionClass $reflection;

    protected function setUp(): void
    {
        parent::setUp();

        $activeTaskStore = new ActiveTaskStore;
        $activeTaskPoller = new ActiveTaskPoller($activeTaskStore);
        $zoneCursorStore = new ZoneCursorStore;

        $this->orchestrator = new SchedulerCycleOrchestrator(
            scheduleLoader: new ScheduleLoader(
                effectiveTargetsService: Mockery::mock(EffectiveTargetsService::class),
                zoneCursorStore: $zoneCursorStore,
            ),
            scheduleDispatcher: new ScheduleDispatcher(
                activeTaskStore: $activeTaskStore,
                activeTaskPoller: $activeTaskPoller,
            ),
            finalizer: new SchedulerCycleFinalizer(
                zoneCursorStore: $zoneCursorStore,
                activeTaskStore: $activeTaskStore,
            ),
            lightingScheduleParser: new LightingScheduleParser,
            activeTaskPoller: $activeTaskPoller,
            activeTaskStore: $activeTaskStore,
        );
        $this->reflection = new ReflectionClass($this->orchestrator);
    }

    public function test_to_iso_adds_utc_suffix(): void
    {
        $value = CarbonImmutable::parse('2026-03-03 10:15:20', 'UTC');
        $iso = SchedulerRuntimeHelper::toIso($value);

        $this->assertSame('2026-03-03T10:15:20Z', $iso);
    }

    /**
     * @param  array<int, mixed>  $args
     */
    private function invokePrivateMethod(string $method, array $args = []): mixed
    {
        $refMethod = $this->reflection->getMethod($method);
        $refMethod->setAccessible(true);

        return $refMethod->invokeArgs($this->orchestrator, $args);
    }
}
