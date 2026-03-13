<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ScheduleDispatcher;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ScheduleDispatcherTest extends TestCase
{
    use RefreshDatabase;

    public function test_upsert_scheduler_intent_does_not_mutate_terminal_intent(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var ScheduleDispatcher $dispatcher */
        $dispatcher = $this->app->make(ScheduleDispatcher::class);
        $triggerTime = CarbonImmutable::parse('2026-03-12 12:00:00', 'UTC');
        $correlationId = 'sch:z'.$zone->id.':irrigation:test-guard';

        $created = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'irrigation',
            correlationId: $correlationId,
            triggerTime: $triggerTime,
        );

        $this->assertTrue($created['ok']);
        $this->assertNotNull($created['intent_id']);

        DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->update([
                'status' => 'completed',
                'payload' => json_encode([
                    'source' => 'laravel_scheduler',
                    'workflow' => 'cycle_start',
                    'marker' => 'terminal',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'not_before' => $triggerTime,
                'completed_at' => $triggerTime,
                'updated_at' => $triggerTime,
            ]);

        $before = DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->first();

        $this->assertNotNull($before);

        $result = $dispatcher->upsertSchedulerIntent(
            zoneId: $zone->id,
            taskType: 'irrigation',
            correlationId: $correlationId,
            triggerTime: $triggerTime->addMinutes(5),
        );

        $after = DB::table('zone_automation_intents')
            ->where('id', $created['intent_id'])
            ->first();

        $this->assertTrue($result['ok']);
        $this->assertNotNull($after);
        $this->assertSame('completed', $after->status);
        $this->assertSame($before->updated_at, $after->updated_at);
        $this->assertSame($before->not_before, $after->not_before);
        $this->assertSame(
            json_decode((string) $before->payload, true, 512, JSON_THROW_ON_ERROR),
            json_decode((string) $after->payload, true, 512, JSON_THROW_ON_ERROR),
        );
    }
}
