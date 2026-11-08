<?php

$sourceRoot = env('BACKUP_SOURCE_ROOT', base_path('..'));

return [
    'directory' => env('BACKUP_DIR', '/backups'),
    'script_directory' => env('BACKUP_SCRIPT_DIR', base_path('../scripts/backup')),
    'source_root' => $sourceRoot,
    'services_directory' => $sourceRoot.'/services',
    'mqtt_directory' => $sourceRoot.'/services/mqtt-bridge',
    'configs_directory' => $sourceRoot.'/configs',
    'env_file' => env('BACKUP_ENV_FILE', $sourceRoot.'/.env'),
    'compose_file' => env('BACKUP_COMPOSE_FILE', $sourceRoot.'/docker-compose.dev.yml'),
    // Application backup does not require access to the Docker daemon.
    'include_docker_volumes' => (bool) env('BACKUP_INCLUDE_DOCKER_VOLUMES', false),
];
