<?php

namespace Tests\Unit;

use App\Services\DigitalTwinClient;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class DigitalTwinClientTest extends TestCase
{
    public function test_simulate_zone_sends_correct_request(): void
    {
        Http::fake([
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => [
                    'points' => [
                        ['t' => 0, 'ph' => 6.0, 'ec' => 1.2, 'temp_air' => 22.0],
                    ],
                    'duration_hours' => 72,
                    'step_minutes' => 10,
                ],
            ], 200),
        ]);

        $client = new DigitalTwinClient('http://digital-twin:8003');
        $result = $client->simulateZone(1, [
            'duration_hours' => 72,
            'step_minutes' => 10,
            'scenario' => ['recipe_id' => 1],
        ]);

        $this->assertEquals('ok', $result['status']);
        $this->assertArrayHasKey('data', $result);
        $this->assertEquals(72, $result['data']['duration_hours']);

        Http::assertSent(function ($request) {
            $url = $request->url();
            $data = $request->data();
            return str_contains($url, 'simulate/zone')
                && $request->method() === 'POST'
                && $data['zone_id'] === 1
                && $data['duration_hours'] === 72
                && $data['step_minutes'] === 10;
        });
    }

    public function test_simulate_zone_handles_error_response(): void
    {
        Http::fake([
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'error',
                'message' => 'Recipe not found',
            ], 404),
        ]);

        $client = new DigitalTwinClient('http://digital-twin:8003');

        $this->expectException(\Exception::class);

        $client->simulateZone(1, [
            'duration_hours' => 72,
            'step_minutes' => 10,
        ]);
    }

    public function test_simulate_zone_handles_connection_error(): void
    {
        Http::fake(function () {
            throw new \Illuminate\Http\Client\ConnectionException('Connection refused');
        });

        $client = new DigitalTwinClient('http://digital-twin:8003');

        $this->expectException(\Exception::class);

        $client->simulateZone(1, [
            'duration_hours' => 72,
            'step_minutes' => 10,
        ]);
    }

    public function test_simulate_zone_uses_default_parameters(): void
    {
        Http::fake([
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => ['points' => [], 'duration_hours' => 72, 'step_minutes' => 10],
            ], 200),
        ]);

        $client = new DigitalTwinClient('http://digital-twin:8003');
        $result = $client->simulateZone(1, []);

        Http::assertSent(function ($request) {
            $data = $request->data();
            return $data['duration_hours'] === 72
                && $data['step_minutes'] === 10;
        });
    }
}

