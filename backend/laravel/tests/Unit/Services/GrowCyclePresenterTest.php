<?php

namespace Tests\Unit\Services;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Services\GrowCyclePresenter;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Mockery;
use Tests\TestCase;

class GrowCyclePresenterTest extends TestCase
{
    protected function tearDown(): void
    {
        Carbon::setTestNow();
        Mockery::close();
        parent::tearDown();
    }

    public function test_overall_and_stage_progress_increase_after_planting(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-07-16 16:30:00', 'UTC'));

        $revision = Mockery::mock(RecipeRevision::class);

        $cycle = Mockery::mock(GrowCycle::class)->makePartial();
        $cycle->id = 1;
        $cycle->status = GrowCycleStatus::RUNNING;
        $cycle->planting_at = Carbon::parse('2026-07-16 13:00:00', 'UTC');
        $cycle->started_at = $cycle->planting_at;
        $cycle->expected_harvest_at = Carbon::parse('2026-07-22 13:00:00', 'UTC');
        $cycle->shouldReceive('getAttribute')->with('recipeRevision')->andReturn($revision);
        $cycle->shouldReceive('getAttribute')->with('currentPhase')->andReturn(null);
        $cycle->shouldReceive('getRelationValue')->andReturnUsing(function (string $key) use ($revision) {
            return $key === 'recipeRevision' ? $revision : null;
        });

        // Обход Eloquent: presenter читает $cycle->recipeRevision / currentPhase как свойства.
        $cycle->setRelation('recipeRevision', $revision);
        $cycle->setRelation('currentPhase', null);

        $growCycleService = Mockery::mock(GrowCycleService::class);
        $growCycleService->shouldReceive('buildStageTimeline')
            ->once()
            ->with($revision)
            ->andReturn([
                'total_hours' => 144.0, // 6 суток
                'segments' => [
                    [
                        'code' => 'plant',
                        'name' => 'Посадка',
                        'duration_hours' => 72.0,
                        'phase_indices' => [0],
                    ],
                    [
                        'code' => 'grow',
                        'name' => 'Рост',
                        'duration_hours' => 72.0,
                        'phase_indices' => [1],
                    ],
                ],
            ]);

        $presenter = new GrowCyclePresenter($growCycleService);
        $dto = $presenter->buildCycleDto($cycle)['cycle'];

        // ~3.5 ч из 144 ≈ 2.4%
        $this->assertGreaterThan(2.0, $dto['progress']['overall_pct']);
        $this->assertLessThan(3.0, $dto['progress']['overall_pct']);

        $active = collect($dto['stages'])->firstWhere('state', 'ACTIVE');
        $this->assertNotNull($active);
        $this->assertSame('Посадка', $active['name']);
        // ~3.5 / 72 ≈ 4.9%
        $this->assertGreaterThan(4.0, $active['pct']);
        $this->assertLessThan(6.0, $active['pct']);
        $this->assertGreaterThan(4.0, $dto['progress']['stage_pct']);
    }
}
