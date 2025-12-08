<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;

class CheckSecurityConfig extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'security:check-config';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Check security configuration for production';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        if (!app()->isProduction()) {
            $this->info('Not in production, skipping security checks');
            return self::SUCCESS;
        }

        $errors = [];

        // Проверка токенов
        if (!config('services.python_bridge.token')) {
            $errors[] = 'PY_API_TOKEN not set';
        }

        if (!config('services.python_bridge.ingest_token')) {
            $errors[] = 'PY_INGEST_TOKEN not set';
        }

        if (!config('services.history_logger.token')) {
            $errors[] = 'HISTORY_LOGGER_API_TOKEN not set';
        }

        // Проверка DB password
        if (!config('database.connections.pgsql.password')) {
            $errors[] = 'DB_PASSWORD not set';
        }

        // Проверка MQTT password
        if (!config('services.mqtt.password')) {
            $errors[] = 'MQTT_PASSWORD not set';
        }

        // Проверка APP_KEY
        $appKey = config('app.key');
        if (empty($appKey) || $appKey === 'base64:default_key') {
            $errors[] = 'APP_KEY is default or empty (insecure)';
        }

        if (!empty($errors)) {
            $this->error('Security configuration errors:');
            foreach ($errors as $error) {
                $this->error("  - {$error}");
            }
            return self::FAILURE;
        }

        $this->info('✓ Security configuration OK');
        return self::SUCCESS;
    }
}

