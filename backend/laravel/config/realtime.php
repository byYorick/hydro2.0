<?php

return [
    'telemetry_batch_max_updates' => (int) env('REALTIME_BATCH_MAX_UPDATES', 200),
    'telemetry_batch_max_bytes' => (int) env('REALTIME_BATCH_MAX_BYTES', 262144),
];
