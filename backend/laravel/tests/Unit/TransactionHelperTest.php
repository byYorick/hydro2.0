<?php

namespace Tests\Unit;

use App\Helpers\TransactionHelper;
use Tests\TestCase;

class TransactionHelperTest extends TestCase
{
    public function test_is_serialization_failure_detects_pdo_exception_sqlstate(): void
    {
        $exception = new \PDOException('SQLSTATE[40001]: Serialization failure');
        $exception->errorInfo = ['40001', 7, 'could not serialize access'];

        $this->assertTrue($this->isSerializationFailure($exception));
    }

    public function test_is_serialization_failure_detects_deadlock_message(): void
    {
        $exception = new \RuntimeException('deadlock detected while updating nodes');

        $this->assertTrue($this->isSerializationFailure($exception));
    }

    public function test_is_serialization_failure_returns_false_for_non_retryable_error(): void
    {
        $exception = new \RuntimeException('validation failed');

        $this->assertFalse($this->isSerializationFailure($exception));
    }

    private function isSerializationFailure(\Throwable $exception): bool
    {
        $method = new \ReflectionMethod(TransactionHelper::class, 'isSerializationFailure');
        $method->setAccessible(true);

        return (bool) $method->invoke(null, $exception);
    }
}
