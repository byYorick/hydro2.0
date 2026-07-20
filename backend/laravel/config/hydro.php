<?php

return [
    'seed_profile' => env('HYDRO_SEED_PROFILE', 'lite'),
    'telemetry_retention_days' => (int) env('TELEMETRY_RETENTION_DAYS', 30),
    /**
     * TTL незавершённого bind/rebind/swap (pending_zone_id при zone_id = null).
     * По истечении janitor очищает pending — повторная привязка через UI (retry).
     */
    'pending_bind_ttl_minutes' => (int) env('PENDING_BIND_TTL_MINUTES', 30),

    /**
     * Молчаливый auto-bind transport-ролей (pump_main/drain) из каналов нод
     * при ZoneReadinessService::checkZoneReadiness. В prod — только явный операторский bind.
     * E2E/тесты могут включить: HYDRO_AUTO_BIND_TRANSPORT_ROLES=true.
     */
    'auto_bind_transport_roles' => filter_var(
        env('HYDRO_AUTO_BIND_TRANSPORT_ROLES', false),
        FILTER_VALIDATE_BOOLEAN
    ),
];
