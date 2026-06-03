<?php

namespace App\Http\Controllers\Concerns;

use App\Services\ErrorCodeCatalogService;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;

trait PresentsLocalizedApiErrors
{
    protected function errorCodeCatalog(): ErrorCodeCatalogService
    {
        return app(ErrorCodeCatalogService::class);
    }

    /**
     * @param  array<string, mixed>  $extra
     */
    protected function localizedError(
        string $code,
        ?string $message = null,
        int $status = 422,
        array $extra = [],
    ): JsonResponse {
        return response()->json(
            $this->errorCodeCatalog()->errorPayload($code, $message, $extra),
            $status,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    protected function enrichedErrorResponse(array $payload, int $status): JsonResponse
    {
        return response()->json(
            $this->errorCodeCatalog()->enrichErrorPayload($payload),
            $status,
        );
    }

    /**
     * Проксирует тело ошибки automation-engine с локализацией.
     *
     * @param  array<string, mixed>  $decoded
     */
    protected function enrichedUpstreamResponse(array $decoded, int $status): JsonResponse
    {
        return $this->enrichedErrorResponse($decoded, $status);
    }

    /**
     * Проксирует 4xx от automation-engine с human_error_message.
     */
    protected function buildAutomationEngineErrorResponse(
        RequestException $exception,
        ?string $notFoundMessage = null,
    ): ?JsonResponse {
        $response = $exception->response;
        if (! $response instanceof Response) {
            return null;
        }

        $status = $response->status();
        if ($status < 400 || $status >= 500) {
            return null;
        }

        $decoded = $response->json();
        if (is_array($decoded)) {
            if ($status === 404) {
                return $this->localizedError(
                    'upstream_not_supported',
                    $notFoundMessage ?? 'Automation-engine не поддерживает этот API.',
                    501,
                );
            }

            return $this->enrichedUpstreamResponse($decoded, $status);
        }

        return $this->localizedError('upstream_error', null, $status);
    }
}
