<?php

namespace Tests;

use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    // Event::fake() и Notification::fake() должны вызываться только в тестах,
    // которые явно это требуют, чтобы не ломать тесты, проверяющие события
}
