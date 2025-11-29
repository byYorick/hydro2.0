<?php

namespace Tests;

use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Foundation\Http\Middleware\ValidateCsrfToken;

abstract class TestCase extends BaseTestCase
{
    // Event::fake() и Notification::fake() должны вызываться только в тестах,
    // которые явно это требуют, чтобы не ломать тесты, проверяющие события

    protected function setUp(): void
    {
        parent::setUp();

        // Отключаем CSRF проверку для всех тестов, так как тесты используют
        // Bearer токены или session-based аутентификацию без CSRF токенов
        $this->withoutMiddleware(ValidateCsrfToken::class);
    }
}
