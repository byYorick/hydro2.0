<?php

namespace Tests\Unit\Services;

use App\Models\Command;
use App\Services\PipelineMetricsService;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class PipelineMetricsServiceTest extends TestCase
{
    public function test_record_command_latency_posts_to_history_logger_without_facade_error(): void
    {
        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.history_logger.token', 'test-token');

        Http::fake([
            'http://history-logger:9300/internal/metrics/command-latency' => Http::response(['ok' => true], 200),
        ]);

        $command = new Command([
            'cmd_id' => 'test-cmd-latency-1',
            'status' => Command::STATUS_DONE,
        ]);
        $command->sent_at = now()->subSeconds(10);
        $command->ack_at = now();

        (new PipelineMetricsService)->recordCommandLatency($command);

        Http::assertSent(function ($request) {
            return $request->url() === 'http://history-logger:9300/internal/metrics/command-latency'
                && $request['cmd_id'] === 'test-cmd-latency-1';
        });
    }
}
