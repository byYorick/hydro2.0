<?php

namespace App\Http\Middleware;

use App\Services\ErrorCodeCatalogService;
use Closure;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Дополняет все API JSON-ответы со status=error полями human_error_message/title (100% i18n).
 */
class LocalizeApiErrorResponse
{
    public function handle(Request $request, Closure $next): Response
    {
        $response = $next($request);

        if (! $response instanceof JsonResponse) {
            return $response;
        }

        if (! $request->is('api/*') && ! $request->expectsJson()) {
            return $response;
        }

        $data = $response->getData(true);
        if (! is_array($data)) {
            return $response;
        }

        $status = $data['status'] ?? null;
        if ($status !== 'error' && $status !== 'failed') {
            return $response;
        }

        $localized = app(ErrorCodeCatalogService::class)->localizeResponsePayload($data);
        $response->setData($localized);

        return $response;
    }
}
