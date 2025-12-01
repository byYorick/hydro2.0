<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class SecurityMiddlewareTest extends TestCase
{
    use RefreshDatabase;

    public function test_verify_python_service_token_requires_token_in_production(): void
    {
        // Устанавливаем production окружение
        Config::set('app.env', 'production');
        Config::set('app.debug', false);
        Config::set('services.python_bridge.token', 'required-token');

        // Запрос без токена должен быть отклонен
        $response = $this->getJson('/api/system/config/full');
        
        $response->assertStatus(401)
            ->assertJson([
                'status' => 'error',
                'message' => 'Unauthorized: missing service token',
            ]);
    }

    public function test_verify_python_service_token_denies_access_when_token_not_configured(): void
    {
        Config::set('app.env', 'production');
        Config::set('app.debug', false);
        Config::set('services.python_bridge.token', null);

        // Даже в production, если токен не настроен, доступ должен быть запрещен
        $response = $this->getJson('/api/system/config/full');
        
        $response->assertStatus(401)
            ->assertJson([
                'status' => 'error',
                'message' => 'Unauthorized: service token not configured or missing authentication',
            ]);
    }

    public function test_verify_alertmanager_webhook_requires_secret(): void
    {
        Config::set('app.env', 'production');
        Config::set('app.debug', false);
        Config::set('services.alertmanager.webhook_secret', null);

        // Запрос без секрета должен быть отклонен даже в production
        $response = $this->postJson('/api/alerts/webhook', [
            'alerts' => [],
        ]);
        
        $response->assertStatus(500)
            ->assertJson([
                'status' => 'error',
                'message' => 'Webhook authentication not configured',
            ]);
    }

    public function test_node_registration_requires_token(): void
    {
        Config::set('services.python_bridge.ingest_token', 'required-token');
        Config::set('services.python_bridge.token', 'required-token');

        // Запрос без токена должен быть отклонен
        $response = $this->postJson('/api/nodes/register', [
            'node_uid' => 'test-node',
        ]);
        
        $response->assertStatus(401)
            ->assertJson([
                'status' => 'error',
                'message' => 'Unauthorized: token required',
            ]);
    }

    public function test_node_registration_denies_when_token_not_configured(): void
    {
        Config::set('services.python_bridge.ingest_token', null);
        Config::set('services.python_bridge.token', null);
        // Устанавливаем production окружение для строгой проверки
        Config::set('app.env', 'production');
        Config::set('app.debug', false);

        // Если токен не настроен, регистрация должна быть запрещена
        $response = $this->postJson('/api/nodes/register', [
            'node_uid' => 'test-node',
        ]);
        
        $response->assertStatus(500)
            ->assertJson([
                'status' => 'error',
                'message' => 'Node registration token not configured',
            ]);
    }
}

