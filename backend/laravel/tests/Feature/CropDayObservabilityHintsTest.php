<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\Zone;
use App\Services\ZoneAutomationObservabilityService;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Tests\TestCase;

class CropDayObservabilityHintsTest extends TestCase
{
    /** @var list<int> */
    private array $greenhouseIds = [];

    /** @var list<int> */
    private array $zoneIds = [];

    /** @var list<int> */
    private array $eventIds = [];

    /** @var list<int> */
    private array $taskIds = [];

    protected function tearDown(): void
    {
        Carbon::setTestNow();
        $this->deleteFixture();
        parent::tearDown();
    }

    public function test_moisture_vent_hint_reads_flag_and_does_not_calculate_vpd(): void
    {
        $zone = $this->makeZone();
        $this->insertClimateState($zone, [
            'moisture_vent_suppressed' => true,
            'inside_temp_c' => 25,
            'inside_rh_pct' => 60,
        ]);

        $hint = $this->hint($this->enrich($zone), 'moisture_vent_suppressed');

        $this->assertNotNull($hint);
        $this->assertSame('info', $hint['severity']);
        $this->assertTrue($hint['details']['moisture_vent_suppressed']);
        $this->assertArrayNotHasKey('air_vpd_kpa', $hint['details']);
        $this->assertArrayNotHasKey('dew_point_c', $hint['details']);
        $this->assertArrayNotHasKey('inside_temp_c', $hint['details']);

        DB::table('greenhouse_automation_state')
            ->where('greenhouse_id', $zone->greenhouse_id)
            ->update([
                'decision_factors' => json_encode([
                    'inside_temp_c' => 30,
                    'inside_rh_pct' => 20,
                    'outside_temp_c' => 32,
                    'outside_rh_pct' => 90,
                    'air_vpd_kpa' => 2.5,
                ], JSON_THROW_ON_ERROR),
            ]);

        $this->assertNull($this->hint($this->enrich($zone), 'moisture_vent_suppressed'));
    }

    public function test_missing_decision_factors_do_not_create_moisture_vent_hint(): void
    {
        $zone = $this->makeZone();
        $this->insertClimateState($zone, null);

        $this->assertNull($this->hint($this->enrich($zone), 'moisture_vent_suppressed'));

        $bare = $this->makeZone();
        $this->assertNull($this->hint($this->enrich($bare), 'moisture_vent_suppressed'));
    }

    public function test_stale_cache_keeps_projected_hint_absent_from_input_payload(): void
    {
        $zone = $this->makeZone();
        $this->insertClimateState($zone, ['moisture_vent_suppressed' => true]);

        $payload = app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => [
                    'task_is_active' => false,
                    'task_status' => 'completed',
                ],
                'hang_hints' => [],
                'overall_health' => 'idle',
            ],
        ], isStale: true);

        $hint = $this->hint($payload, 'moisture_vent_suppressed');
        $this->assertNotNull($hint);
        $this->assertSame('info', $hint['severity']);
        $this->assertArrayNotHasKey('air_vpd_kpa', $hint['details']);
        $this->assertSame('idle', $payload['observability']['overall_health']);

        $kept = app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => false, 'task_status' => 'completed'],
                'hang_hints' => [[
                    'code' => 'irrigation_sensor_blocked',
                    'severity' => 'critical',
                    'message' => 'Полив пропущен: нет свежего измерения влажности. Насос не запускался.',
                    'details' => ['reason_code' => 'smart_soil_telemetry_missing_or_stale'],
                ]],
                'overall_health' => 'critical',
            ],
        ], isStale: true);
        $blocked = $this->hint($kept, 'irrigation_sensor_blocked');
        $this->assertNotNull($blocked);
        $this->assertSame('critical', $blocked['severity']);
        $this->assertArrayNotHasKey('air_vpd_kpa', $blocked['details']);
    }

    public function test_dli_and_solution_refresh_hints_are_projections(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-10-04 12:00:00', 'UTC'));
        $zone = $this->makeZone();
        $eventsBefore = (int) DB::table('zone_events')->where('zone_id', $zone->id)->count();

        $sensor = app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'day_balance' => ['dli_status' => 'sensor_unavailable', 'dli_mol' => null],
            'observability' => ['hang_hints' => [], 'runtime' => ['task_is_active' => false]],
        ]);
        $gap = app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'day_balance' => ['dli_status' => 'gap', 'dli_mol' => null],
            'observability' => ['hang_hints' => [], 'runtime' => ['task_is_active' => false]],
        ]);
        $within = app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'day_balance' => ['dli_status' => 'within_target', 'dli_mol' => 1.0],
            'observability' => ['hang_hints' => [], 'runtime' => ['task_is_active' => false]],
        ]);
        $withoutBalance = $this->enrich($zone);

        $this->assertSame('warning', $this->hint($sensor, 'dli_sensor_unavailable')['severity'] ?? null);
        $this->assertNull($this->hint($sensor, 'dli_gap'));
        $this->assertSame('warning', $this->hint($gap, 'dli_gap')['severity'] ?? null);
        $this->assertNull($this->hint($within, 'dli_sensor_unavailable'));
        $this->assertNull($this->hint($within, 'dli_gap'));
        $this->assertNull($this->hint($withoutBalance, 'dli_sensor_unavailable'));
        $this->assertSame($eventsBefore, (int) DB::table('zone_events')->where('zone_id', $zone->id)->count());

        $eventId = $this->insertRefreshEvent($zone, '2026-10-04 11:00:00');
        $due = $this->hint($this->enrich($zone), 'solution_refresh_due');
        $this->assertNotNull($due);
        $this->assertSame('warning', $due['severity']);
        $this->assertSame($eventId, $due['details']['event_id']);

        $this->insertCompletedSolutionChange($zone, '2026-10-04 11:30:00');
        $this->assertNull($this->hint($this->enrich($zone), 'solution_refresh_due'));
    }

    public function test_new_biz_codes_exist_in_json_catalogs(): void
    {
        foreach (['dli_sensor_unavailable', 'solution_refresh_recommended'] as $code) {
            $alert = $this->catalogCode('alert_codes.json', $code);
            $error = $this->catalogCode('error_codes.json', $code);
            $this->assertMatchesRegularExpression('/\p{Cyrillic}/u', (string) $alert['title']);
            $this->assertMatchesRegularExpression('/\p{Cyrillic}/u', (string) $alert['recommendation']);
            $this->assertMatchesRegularExpression('/\p{Cyrillic}/u', (string) $error['title']);
            $this->assertMatchesRegularExpression('/\p{Cyrillic}/u', (string) $error['message']);
            $this->assertStringNotContainsString('SELECT ', (string) $alert['recommendation']);
            $this->assertStringNotContainsString('SELECT ', (string) $error['message']);
        }
    }

    /**
     * @param  array<string,mixed>|null  $factors
     */
    private function insertClimateState(Zone $zone, ?array $factors): void
    {
        $now = now();
        DB::table('greenhouse_automation_state')->insert([
            'greenhouse_id' => $zone->greenhouse_id,
            'control_mode' => 'auto',
            'decision_factors' => $factors === null ? null : json_encode($factors, JSON_THROW_ON_ERROR),
            'created_at' => $now,
            'updated_at' => $now,
        ]);
    }

    private function insertRefreshEvent(Zone $zone, string $atUtc): int
    {
        $at = Carbon::parse($atUtc, 'UTC');
        $eventId = (int) DB::table('zone_events')->insertGetId([
            'zone_id' => $zone->id,
            'type' => 'SOLUTION_REFRESH_RECOMMENDED',
            'payload_json' => json_encode(['message' => 'Пора подменить раствор'], JSON_THROW_ON_ERROR),
            'created_at' => $at,
        ]);
        $this->eventIds[] = $eventId;

        return $eventId;
    }

    private function insertCompletedSolutionChange(Zone $zone, string $atUtc): void
    {
        $at = Carbon::parse($atUtc, 'UTC')->format('Y-m-d H:i:s');
        $this->taskIds[] = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'solution_change',
            'status' => 'completed',
            'idempotency_key' => 'g9-'.Str::lower(Str::uuid()->toString()),
            'scheduled_for' => $at,
            'due_at' => $at,
            'completed_at' => $at,
            'created_at' => $at,
            'updated_at' => $at,
        ]);
    }

    /**
     * @return array<string,mixed>
     */
    private function enrich(Zone $zone): array
    {
        return app(ZoneAutomationObservabilityService::class)->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => false],
                'hang_hints' => [],
                'overall_health' => 'idle',
            ],
        ]);
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>|null
     */
    private function hint(array $payload, string $code): ?array
    {
        foreach ($payload['observability']['hang_hints'] ?? [] as $hint) {
            if (is_array($hint) && ($hint['code'] ?? '') === $code) {
                return $hint;
            }
        }

        return null;
    }

    private function makeZone(): Zone
    {
        $greenhouse = Greenhouse::factory()->create(['timezone' => 'UTC']);
        $this->greenhouseIds[] = (int) $greenhouse->id;
        $zone = Zone::factory()->create([
            'status' => 'online',
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->zoneIds[] = (int) $zone->id;

        return $zone->fresh();
    }

    /**
     * @return array<string,mixed>
     */
    private function catalogCode(string $file, string $code): array
    {
        $path = base_path($file);
        $this->assertFileExists($path);
        $decoded = json_decode((string) file_get_contents($path), true);
        $this->assertIsArray($decoded);
        foreach ($decoded['codes'] as $row) {
            if (is_array($row) && ($row['code'] ?? '') === $code) {
                return $row;
            }
        }

        $this->fail($code.' missing in '.$file);
    }

    private function deleteFixture(): void
    {
        if ($this->eventIds !== []) {
            DB::table('zone_events')->whereIn('id', $this->eventIds)->delete();
        }
        if ($this->taskIds !== []) {
            DB::table('ae_tasks')->whereIn('id', $this->taskIds)->delete();
        }
        if ($this->greenhouseIds !== []) {
            DB::table('greenhouse_automation_state')->whereIn('greenhouse_id', $this->greenhouseIds)->delete();
        }
        if ($this->zoneIds !== []) {
            DB::table('zones')->whereIn('id', $this->zoneIds)->delete();
        }
        if ($this->greenhouseIds !== []) {
            DB::table('greenhouses')->whereIn('id', $this->greenhouseIds)->delete();
        }
    }
}
