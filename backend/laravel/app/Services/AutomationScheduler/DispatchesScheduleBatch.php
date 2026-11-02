<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Pool;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;

/** Dispatch prepared schedules concurrently and normalize transport failures. */
trait DispatchesScheduleBatch
{
    /**
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    public function dispatch(
        int $zoneId,
        ScheduleItem $schedule,
        CarbonImmutable $triggerTime,
        string $scheduleKey,
        ScheduleCycleContext $context,
        callable $writeLog,
    ): array {
        $results = $this->dispatchBatch(
            jobs: [[
                'zoneId' => $zoneId,
                'schedule' => $schedule,
                'triggerTime' => $triggerTime,
                'scheduleKey' => $scheduleKey,
            ]],
            context: $context,
            writeLog: $writeLog,
        );

        return $results[0] ?? [
            'dispatched' => false,
            'retryable' => true,
            'reason' => 'dispatch_batch_result_missing',
        ];
    }

    /**
     * @param  array<int, array{
     *     zoneId:int,
     *     schedule:ScheduleItem,
     *     triggerTime:CarbonImmutable,
     *     scheduleKey:string
     * }>  $jobs
     * @return array<int, array{dispatched: bool, retryable: bool, reason: string}>
     */
    public function dispatchBatch(
        array $jobs,
        ScheduleCycleContext $context,
        callable $writeLog,
    ): array {
        $results = [];
        $preparedByIndex = [];

        foreach ($jobs as $index => $job) {
            $prepared = $this->prepareDispatch(
                zoneId: (int) $job['zoneId'],
                schedule: $job['schedule'],
                triggerTime: $job['triggerTime'],
                scheduleKey: (string) $job['scheduleKey'],
                context: $context,
                writeLog: $writeLog,
            );
            if (! (bool) ($prepared['ready'] ?? false)) {
                $results[$index] = $prepared['result'];

                continue;
            }
            $preparedByIndex[$index] = $prepared;
        }

        if ($preparedByIndex === []) {
            ksort($results);

            return $results;
        }

        $responses = [];
        try {
            $poolResults = Http::pool(function (Pool $pool) use ($preparedByIndex): void {
                foreach ($preparedByIndex as $index => $prepared) {
                    $pool
                        ->as((string) $index)
                        ->acceptJson()
                        ->timeout($prepared['timeout_sec'])
                        ->withHeaders($prepared['headers'])
                        ->post($prepared['url'], $prepared['request_payload']);
                }
            });

            foreach ($preparedByIndex as $index => $_prepared) {
                $response = $poolResults[(string) $index] ?? null;
                $responses[$index] = [
                    'response' => $response instanceof Response ? $response : null,
                    'error' => $response instanceof \Throwable ? $response->getMessage() : null,
                ];
            }
        } catch (\Throwable $poolError) {
            foreach ($preparedByIndex as $index => $prepared) {
                try {
                    $response = Http::acceptJson()
                        ->timeout($prepared['timeout_sec'])
                        ->withHeaders($prepared['headers'])
                        ->post($prepared['url'], $prepared['request_payload']);
                    $responses[$index] = [
                        'response' => $response,
                        'error' => null,
                    ];
                } catch (ConnectionException $e) {
                    $responses[$index] = [
                        'response' => null,
                        'error' => $e->getMessage(),
                    ];
                }
            }
        }

        foreach ($preparedByIndex as $index => $prepared) {
            /** @var Response|null $response */
            $response = $responses[$index]['response'] ?? null;
            $results[$index] = $this->finalizePreparedDispatch(
                prepared: $prepared,
                response: $response,
                connectionErrorMessage: $responses[$index]['error'] ?? null,
                writeLog: $writeLog,
            );
        }

        ksort($results);

        return $results;
    }
}
