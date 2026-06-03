<?php

namespace App\Support;

use App\Services\ErrorCodeCatalogService;
use Illuminate\Http\JsonResponse;

/**
 * Фабрика локализованных JSON-ответов об ошибках (фаза 2, для bootstrap и сервисов).
 */
final class LocalizedApiJsonResponse
{
    /**
     * @param  array<string, mixed>  $extra
     */
    public static function error(
        string $code,
        ?string $message = null,
        int $status = 422,
        array $extra = [],
    ): JsonResponse {
        return response()->json(
            app(ErrorCodeCatalogService::class)->errorPayload($code, $message, $extra),
            $status,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    public static function fromPayload(array $payload, int $status): JsonResponse
    {
        return response()->json(
            app(ErrorCodeCatalogService::class)->enrichErrorPayload($payload),
            $status,
        );
    }
}
