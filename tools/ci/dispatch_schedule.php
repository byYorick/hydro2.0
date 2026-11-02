<?php
// Test driver for the production Laravel scheduler dispatcher. No HTTP fakes.
try {
require '/app/vendor/autoload.php';
$app = require '/app/bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$zoneId = (int) $argv[1];
if ($zoneId <= 0 || getenv('APP_ENV') !== 'testing') {
    throw new RuntimeException('This driver requires an isolated testing database and a fixture zone.');
}
$now = Carbon\CarbonImmutable::now('UTC');
$traceId = 'ci-pipeline-'.bin2hex(random_bytes(8));
$schedule = new App\Services\AutomationScheduler\ScheduleItem(
    zoneId: $zoneId,
    taskType: 'diagnostics',
    intervalSec: 60,
);
$context = new App\Services\AutomationScheduler\ScheduleCycleContext(
    cfg: ['api_url' => 'http://automation-engine:9505', 'timeout_sec' => 10, 'due_grace_sec' => 15,
        'expires_after_sec' => 600, 'active_task_ttl_sec' => 600],
    headers: ['Accept' => 'application/json', 'Authorization' => 'Bearer '.getenv('PY_API_TOKEN'),
        'X-Scheduler-Id' => 'laravel-scheduler', 'X-Trace-Id' => $traceId],
    traceId: $traceId,
    cycleNow: $now, lastRunByTaskName: [], reconciledBusyness: [], zoneWorkflowPhases: [],
);
$result = $app->make(App\Services\AutomationScheduler\ScheduleDispatcher::class)->dispatch(
    zoneId: $zoneId, schedule: $schedule, triggerTime: $now,
    scheduleKey: $schedule->scheduleKey, context: $context,
    writeLog: static function (string $name, string $status, array $details): void {
        fwrite(STDERR, json_encode(compact('name', 'status', 'details')).PHP_EOL);
    },
);
if (! $result['dispatched']) {
    throw new RuntimeException(json_encode($result));
}
$intent = Illuminate\Support\Facades\DB::table('zone_automation_intents')
    ->where('zone_id', $zoneId)->orderByDesc('id')->first();
$task = Illuminate\Support\Facades\DB::table('ae_tasks')->where('zone_id', $zoneId)->orderByDesc('id')->first();
if (! $intent || ! $task) {
    throw new RuntimeException('Scheduler dispatch must create both intent and AE task.');
}
echo 'CI_SCHEDULER_RESULT='.json_encode(['idempotency_key' => $intent->idempotency_key, 'task_id' => (string) $task->id]);

} catch (Throwable $error) {
    fwrite(STDERR, get_class($error).': '.$error->getMessage().PHP_EOL);
    exit(1);
}
