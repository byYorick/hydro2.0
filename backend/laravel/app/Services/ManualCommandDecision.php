<?php

namespace App\Services;

final class ManualCommandDecision
{
    /**
     * @param  array<string, mixed>  $extra
     */
    public function __construct(
        public bool $allowed,
        public string $code = '',
        public string $message = '',
        public int $httpStatus = 422,
        public array $extra = [],
    ) {}

    public static function allow(): self
    {
        return new self(true);
    }

    /**
     * @param  array<string, mixed>  $extra
     */
    public static function reject(string $code, string $message, int $httpStatus = 422, array $extra = []): self
    {
        return new self(false, $code, $message, $httpStatus, $extra);
    }
}
