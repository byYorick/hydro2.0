<?php

declare(strict_types=1);

namespace App\Services;

use App\Services\AlertLocalization\AlertMessageComposer;

/**
 * Публичный API локализации alert'ов. Тонкий оркестратор — логика вынесена в
 * {@see \App\Services\AlertLocalization\AlertCodeTranslator},
 * {@see \App\Services\AlertLocalization\AlertStructuredMessageParser},
 * {@see \App\Services\AlertLocalization\AlertTypeTranslator},
 * {@see \App\Services\AlertLocalization\AlertMessageComposer}.
 */
class AlertLocalizationService
{
    public function __construct(
        private AlertCatalogService $alertCatalogService,
        private AlertMessageComposer $composer,
    ) {}

    /**
     * @param array<string, mixed>|null $details
     *
     * @return array{code:string,title:string,description:string,recommendation:string,message:string}
     */
    public function present(?string $code, ?string $type = null, ?array $details = null, ?string $source = null): array
    {
        $payload = is_array($details) ? $details : [];
        $resolvedCode = $this->alertCatalogService->normalizeCode($code ?? $payload['code'] ?? null);
        $catalog = $this->alertCatalogService->resolve($resolvedCode, $source ?? ($payload['source'] ?? null), $payload);

        $title = $this->composer->resolveTitle($resolvedCode, $catalog, $type, $payload);
        $description = $this->composer->resolveDescription($catalog, $payload);
        $recommendation = $this->composer->resolveRecommendation($catalog, $payload);
        $message = $this->composer->resolveMessage(
            code: $resolvedCode,
            type: $type,
            details: $payload,
            description: $description,
        );

        return [
            'code' => $resolvedCode !== '' ? $resolvedCode : 'unknown_alert',
            'title' => $title,
            'description' => $description,
            'recommendation' => $recommendation,
            'message' => $message,
        ];
    }
}
