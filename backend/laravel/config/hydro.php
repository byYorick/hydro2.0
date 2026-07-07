<?php

return [
    'seed_profile' => env('HYDRO_SEED_PROFILE', 'lite'),
    'telemetry_retention_days' => (int) env('TELEMETRY_RETENTION_DAYS', 30),
];
