<?php

namespace Tests\Feature;

use App\Models\Zone;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class Ae3LiteSchemaTest extends TestCase
{
    use RefreshDatabase;

    public function test_ae3lite_schema_tables_and_columns_exist(): void
    {
        $this->assertTrue(DB::getSchemaBuilder()->hasTable('ae_tasks'));
        $this->assertTrue(DB::getSchemaBuilder()->hasTable('ae_commands'));
        $this->assertTrue(DB::getSchemaBuilder()->hasTable('ae_zone_leases'));

        $this->assertContains('automation_runtime', DB::getSchemaBuilder()->getColumnListing('zones'));
        $this->assertContains('version', DB::getSchemaBuilder()->getColumnListing('zone_workflow_state'));
        $this->assertContains('idempotency_key', DB::getSchemaBuilder()->getColumnListing('ae_tasks'));
        $this->assertContains('external_id', DB::getSchemaBuilder()->getColumnListing('ae_commands'));

        $zone = Zone::factory()->create();
        $zone->refresh();
        $this->assertSame('ae3', $zone->automation_runtime);
        $this->assertContains('control_mode', DB::getSchemaBuilder()->getColumnListing('zones'));

        DB::table('zone_workflow_state')->insert([
            'zone_id' => $zone->id,
            'workflow_phase' => 'idle',
        ]);

        $workflowRow = DB::table('zone_workflow_state')->where('zone_id', $zone->id)->first();
        $this->assertSame(0, (int) $workflowRow->version);

        $activeZoneIndex = DB::selectOne("
            SELECT 1
            FROM pg_indexes
            WHERE tablename = 'ae_tasks'
              AND indexname = 'ae_tasks_active_zone_unique'
        ");

        $this->assertNotNull($activeZoneIndex, 'Expected unique active-task index for ae_tasks.');
    }

    public function test_ae3lite_active_task_unique_index_blocks_second_active_task_for_same_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        $this->insertTask($zone->id, 'pending', 'ae3:start:'.$zone->id.':1');

        $this->assertInsertFails(function () use ($zone): void {
            $this->insertTask($zone->id, 'running', 'ae3:start:'.$zone->id.':2');
        }, 'duplicate');
    }

    public function test_ae3lite_terminal_task_does_not_block_new_active_task(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        $this->insertTask($zone->id, 'completed', 'ae3:start:'.$zone->id.':done');
        $this->insertTask($zone->id, 'pending', 'ae3:start:'.$zone->id.':next');

        $this->assertSame(2, DB::table('ae_tasks')->where('zone_id', $zone->id)->count());
    }

    public function test_ae3lite_idempotency_key_is_unique(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        $idempotencyKey = 'ae3:start:'.$zone->id.':dup';

        $this->insertTask($zone->id, 'pending', $idempotencyKey);

        $this->assertInsertFails(function () use ($zone, $idempotencyKey): void {
            $this->insertTask($zone->id, 'failed', $idempotencyKey);
        }, 'duplicate');
    }

    public function test_ae3lite_command_step_is_unique_per_task(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        $taskId = $this->insertTask($zone->id, 'pending', 'ae3:start:'.$zone->id.':cmd');

        $this->insertCommand($taskId, 1, 'nd-irrig-1', 'irrigation');

        $this->assertInsertFails(function () use ($taskId): void {
            $this->insertCommand($taskId, 1, 'nd-irrig-2', 'irrigation');
        }, 'duplicate');
    }

    public function test_ae3lite_zone_lease_is_single_writer_per_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-a',
            'leased_until' => now()->addMinute(),
        ]);

        $this->assertInsertFails(function () use ($zone): void {
            DB::table('ae_zone_leases')->insert([
                'zone_id' => $zone->id,
                'owner' => 'ae3-worker-b',
                'leased_until' => now()->addMinutes(2),
            ]);
        }, 'duplicate');
    }

    public function test_ae3lite_automation_runtime_constraint_rejects_unknown_value(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        $this->assertInsertFails(function () use ($zone): void {
            DB::table('zones')
                ->where('id', $zone->id)
                ->update(['automation_runtime' => 'broken']);
        }, 'check');
    }

    private function insertTask(int $zoneId, string $status, string $idempotencyKey): int
    {
        return (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zoneId,
            'task_type' => 'cycle_start',
            'status' => $status,
            'idempotency_key' => $idempotencyKey,
            'scheduled_for' => now(),
            'due_at' => now()->addMinute(),
            'completed_at' => in_array($status, ['completed', 'failed', 'cancelled'], true) ? now() : null,
        ]);
    }

    private function insertCommand(int $taskId, int $stepNo, string $nodeUid, string $channel): void
    {
        DB::table('ae_commands')->insert([
            'task_id' => $taskId,
            'step_no' => $stepNo,
            'node_uid' => $nodeUid,
            'channel' => $channel,
            'payload' => json_encode(['cmd' => 'test'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
        ]);
    }

    private function assertInsertFails(callable $callback, string $expectedNeedle): void
    {
        try {
            $callback();
            $this->fail('Expected DB constraint failure.');
        } catch (QueryException $exception) {
            $this->assertStringContainsString($expectedNeedle, strtolower($exception->getMessage()));
        }
    }
};
