<?php

namespace App\Exceptions;

use RuntimeException;

class ZoneNotReadyException extends RuntimeException
{
    /**
     * @param  array<string, mixed>  $readiness  Полный отчёт от ZoneReadinessService::checkZoneReadiness()
     */
    public function __construct(
        private readonly array $readiness,
        string $message = 'Zone is not ready for cycle start'
    ) {
        parent::__construct($message);
    }

    /**
     * @return array<string, mixed>
     */
    public function readiness(): array
    {
        return $this->readiness;
    }

    /**
     * @return array<int, string>
     */
    public function errors(): array
    {
        $errors = $this->readiness['errors'] ?? [];

        return is_array($errors) ? array_values($errors) : [];
    }
}
