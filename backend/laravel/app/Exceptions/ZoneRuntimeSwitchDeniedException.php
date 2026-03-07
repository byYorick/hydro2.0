<?php

namespace App\Exceptions;

use DomainException;

class ZoneRuntimeSwitchDeniedException extends DomainException
{
    public function __construct(
        private readonly array $details,
        string $message = 'Cannot switch automation runtime while zone is busy.'
    ) {
        parent::__construct($message);
    }

    public function details(): array
    {
        return $this->details;
    }
}
