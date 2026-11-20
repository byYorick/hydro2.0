<?php

namespace App\Exceptions;

use RuntimeException;

class ManualAlertResolveRefusedException extends RuntimeException
{
    public const ERROR_CODE = 'alert_manual_resolve_refused';

    public function __construct(
        string $message = 'Нельзя закрыть алерт вручную, пока условие безопасности ещё активно.',
    ) {
        parent::__construct($message);
    }
}
