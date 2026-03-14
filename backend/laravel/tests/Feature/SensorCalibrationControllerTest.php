<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\SensorCalibration;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Database\QueryException;
use Illuminate\Support\Facades\Http;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SensorCalibrationControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Sanctum::actingAs(User::factory()->create(['role' => 'admin']));
        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.history_logger.token', 'history-token');
        Config::set('services.python_bridge.ingest_token', 'ingest-token');
    }

    public function test_create_calibration_session(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');

        $response = $this->postJson("/api/zones/{$zone->id}/sensor-calibrations", [
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
        ]);

        $response->assertCreated()
            ->assertJsonPath('data.calibration.status', 'started');
        $this->assertEquals(7.0, $response->json('data.defaults.point_1_value'));
    }

    public function test_create_prevents_duplicate_active_session(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_STARTED,
        ]);

        $this->postJson("/api/zones/{$zone->id}/sensor-calibrations", [
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
        ])->assertStatus(422);
    }

    public function test_database_enforces_single_active_session_per_channel(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_STARTED,
        ]);

        $this->expectException(QueryException::class);

        SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_POINT_1_PENDING,
        ]);
    }

    public function test_submit_point_1_enqueues_command_and_marks_pending(): void
    {
        Http::fake([
            'http://history-logger:9300/commands' => Http::response(['status' => 'ok'], 200),
        ]);

        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        $calibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_STARTED,
            'calibrated_by' => auth()->id(),
        ]);

        $response = $this->postJson("/api/zones/{$zone->id}/sensor-calibrations/{$calibration->id}/point", [
            'stage' => 1,
            'reference_value' => 7.0,
        ]);

        $response->assertOk()
            ->assertJsonPath('data.status', SensorCalibration::STATUS_POINT_1_PENDING);
        $this->assertEquals(7.0, $response->json('data.point_1_reference'));

        $this->assertNotNull($calibration->fresh()->point_1_command_id);

        Http::assertSent(function ($request) {
            return $request->url() === 'http://history-logger:9300/commands'
                && $request['cmd'] === 'calibrate'
                && $request['params']['stage'] === 1
                && $request['params']['known_ph'] === 7.0;
        });
    }

    public function test_status_returns_overview_for_all_sensors(): void
    {
        [$zone, $phChannel] = $this->makeSensorChannel('ph_sensor', 'PH');
        [, $ecChannel] = $this->makeSensorChannel('ec_sensor', 'EC', $zone);

        SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $phChannel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_COMPLETED,
            'completed_at' => now()->subDays(40),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/sensor-calibrations/status");

        $response->assertOk()
            ->assertJsonCount(2, 'data');

        $items = collect($response->json('data'));
        $ph = $items->firstWhere('sensor_type', 'ph');
        $ec = $items->firstWhere('sensor_type', 'ec');

        $this->assertSame('warning', $ph['calibration_status']);
        $this->assertSame('never', $ec['calibration_status']);
    }

    public function test_status_includes_active_calibration_id_for_channel(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        $activeCalibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_POINT_1_PENDING,
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/sensor-calibrations/status");

        $response->assertOk()
            ->assertJsonPath('data.0.has_active_session', true)
            ->assertJsonPath('data.0.active_calibration_id', $activeCalibration->id);
    }

    public function test_history_can_be_filtered_by_node_channel_id(): void
    {
        [$zone, $firstChannel] = $this->makeSensorChannel('ph_sensor', 'PH');
        [, $secondChannel] = $this->makeSensorChannel('ph_sensor_aux', 'PH', $zone);

        $firstCalibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $firstChannel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_COMPLETED,
            'completed_at' => now(),
        ]);

        SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $secondChannel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_COMPLETED,
            'completed_at' => now()->subMinute(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/sensor-calibrations?sensor_type=ph&node_channel_id={$firstChannel->id}");

        $response->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.id', $firstCalibration->id)
            ->assertJsonPath('data.0.node_channel_id', $firstChannel->id);
    }

    public function test_command_terminal_ingest_marks_calibration_completed(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        $calibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_POINT_2_PENDING,
            'point_2_command_id' => 'cmd-cal-2',
        ]);

        Command::query()->create([
            'zone_id' => $zone->id,
            'node_id' => $channel->node_id,
            'channel' => $channel->channel,
            'cmd' => 'calibrate',
            'status' => Command::STATUS_ACK,
            'cmd_id' => 'cmd-cal-2',
        ]);

        $this->withHeader('Authorization', 'Bearer ingest-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-cal-2',
                'status' => 'DONE',
            ])
            ->assertOk();

        $calibration->refresh();
        $this->assertSame(SensorCalibration::STATUS_COMPLETED, $calibration->status);
        $this->assertSame('DONE', $calibration->point_2_result);
        $this->assertNotNull($calibration->completed_at);
    }

    public function test_non_done_terminal_command_statuses_map_to_failed(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ec_sensor', 'EC');
        $calibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ec',
            'status' => SensorCalibration::STATUS_POINT_1_PENDING,
            'point_1_command_id' => 'cmd-cal-1',
        ]);

        Command::query()->create([
            'zone_id' => $zone->id,
            'node_id' => $channel->node_id,
            'channel' => $channel->channel,
            'cmd' => 'calibrate',
            'status' => Command::STATUS_ACK,
            'cmd_id' => 'cmd-cal-1',
        ]);

        $this->withHeader('Authorization', 'Bearer ingest-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-cal-1',
                'status' => 'TIMEOUT',
                'details' => [
                    'error_code' => 'TIMEOUT',
                    'error_message' => 'timed out',
                ],
            ])
            ->assertOk();

        $calibration->refresh();
        $this->assertSame(SensorCalibration::STATUS_FAILED, $calibration->status);
        $this->assertSame('TIMEOUT', $calibration->point_1_result);
        $this->assertSame('timed out', $calibration->point_1_error);
        $this->assertNotNull($calibration->completed_at);
    }

    public function test_cancelled_calibration_ignores_late_terminal_ack(): void
    {
        [$zone, $channel] = $this->makeSensorChannel('ph_sensor', 'PH');
        $calibration = SensorCalibration::query()->create([
            'zone_id' => $zone->id,
            'node_channel_id' => $channel->id,
            'sensor_type' => 'ph',
            'status' => SensorCalibration::STATUS_CANCELLED,
            'completed_at' => now(),
            'point_1_command_id' => 'cmd-cal-cancelled',
        ]);

        Command::query()->create([
            'zone_id' => $zone->id,
            'node_id' => $channel->node_id,
            'channel' => $channel->channel,
            'cmd' => 'calibrate',
            'status' => Command::STATUS_ACK,
            'cmd_id' => 'cmd-cal-cancelled',
        ]);

        $this->withHeader('Authorization', 'Bearer ingest-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-cal-cancelled',
                'status' => 'DONE',
            ])
            ->assertOk();

        $calibration->refresh();
        $this->assertSame(SensorCalibration::STATUS_CANCELLED, $calibration->status);
        $this->assertNull($calibration->point_1_result);
    }

    /**
     * @return array{0: Zone, 1: NodeChannel}
     */
    private function makeSensorChannel(string $channelName, string $metric, ?Zone $zone = null): array
    {
        $zone ??= Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
            'type' => strtolower($metric),
        ]);

        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => $channelName,
            'type' => 'sensor',
            'metric' => $metric,
            'unit' => $metric === 'PH' ? 'pH' : 'mS/cm',
            'config' => [],
        ]);

        return [$zone, $channel];
    }
}
