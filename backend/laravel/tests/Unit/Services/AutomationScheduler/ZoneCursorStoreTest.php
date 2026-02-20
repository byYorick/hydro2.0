<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ZoneCursorStore;
use Carbon\CarbonImmutable;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCursorStoreTest extends TestCase
{
    use RefreshDatabase;

    private ZoneCursorStore $store;

    protected function setUp(): void
    {
        parent::setUp();
        $this->store = new ZoneCursorStore;
    }

    public function test_upsert_and_get_cursor(): void
    {
        $zone = Zone::factory()->create();
        $cursorAt = CarbonImmutable::parse('2026-02-20 14:00:00', 'UTC');

        $this->store->upsertCursor(
            zoneId: $zone->id,
            cursorAt: $cursorAt,
            catchupPolicy: 'replay_limited',
            metadata: ['source' => 'unit-test'],
        );

        $loaded = $this->store->getCursorAt($zone->id);
        $this->assertNotNull($loaded);
        $this->assertSame($cursorAt->toDateTimeString(), $loaded->toDateTimeString());

        $updatedCursor = $cursorAt->addMinutes(30);
        $this->store->upsertCursor(
            zoneId: $zone->id,
            cursorAt: $updatedCursor,
            catchupPolicy: 'skip',
            metadata: ['source' => 'unit-test-2'],
        );

        $this->assertDatabaseCount('laravel_scheduler_zone_cursors', 1);
        $this->assertDatabaseHas('laravel_scheduler_zone_cursors', [
            'zone_id' => $zone->id,
            'catchup_policy' => 'skip',
        ]);

        $reloaded = $this->store->getCursorAt($zone->id);
        $this->assertNotNull($reloaded);
        $this->assertSame($updatedCursor->toDateTimeString(), $reloaded->toDateTimeString());
    }

    public function test_get_cursor_for_missing_zone_returns_null(): void
    {
        $this->assertNull($this->store->getCursorAt(999999));
    }
}
