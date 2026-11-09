<?php

declare(strict_types=1);

namespace App\Exceptions;

use App\Support\Hydroponics\HydroponicSystemCatalog;
use DomainException;

/**
 * Отказ гидравлического старта по ADR-0001.
 * Код — один из hydro_system_not_implemented | hydro_system_unknown |
 * hydro_system_needs_review | hydro_system_environment_forbidden.
 */
class UnsupportedHydroponicSystemException extends DomainException
{
    /**
     * @param  list<string>  $supportedTypes
     */
    public function __construct(
        public readonly string $errorCode,
        public readonly string $requestedType,
        public readonly array $supportedTypes,
        string $message,
    ) {
        parent::__construct($message);
    }

    public static function forRaw(string $raw, ?string $environment = null): self
    {
        $code = HydroponicSystemCatalog::refusalCode($raw, $environment) ?? 'hydro_system_unknown';
        $requested = HydroponicSystemCatalog::canonicalize($raw) ?? trim($raw);

        return new self(
            $code,
            $requested,
            HydroponicSystemCatalog::implementedTypes(),
            HydroponicSystemCatalog::rejectionMessage($code, $requested, $environment),
        );
    }

    /**
     * @return array{requested_type: string, supported_types: list<string>}
     */
    public function extra(): array
    {
        return [
            'requested_type' => $this->requestedType,
            'supported_types' => array_values($this->supportedTypes),
        ];
    }
}
