<?php

declare(strict_types=1);

namespace App\Services\AlertLocalization;

/**
 * Собирает (title, description, recommendation, message) для alert'а из каталога,
 * типа и пользовательских $details. Фоллбэки на нейтральные русские строки.
 */
class AlertMessageComposer
{
    public function __construct(
        private AlertCodeTranslator $codeTranslator,
        private AlertTypeTranslator $typeTranslator,
        private DetailsAccessor $accessor,
    ) {}

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    public function resolveTitle(string $code, array $catalog, ?string $type, array $details): string
    {
        $title = $this->accessor->stringValue($details, ['title']);
        if ($title !== null) {
            return $title;
        }

        $translatedType = $this->typeTranslator->translate($type);
        if (($code === '' || $code === 'unknown_alert') && $translatedType !== null) {
            return $translatedType;
        }

        $catalogTitle = trim((string) ($catalog['title'] ?? ''));
        if ($catalogTitle !== '') {
            return $catalogTitle;
        }

        if ($translatedType !== null) {
            return $translatedType;
        }

        return 'Системное предупреждение';
    }

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    public function resolveDescription(array $catalog, array $details): string
    {
        $description = $this->accessor->stringValue($details, ['description']);
        if ($description !== null && $this->accessor->looksLocalized($description)) {
            return $description;
        }

        $catalogDescription = trim((string) ($catalog['description'] ?? ''));
        if ($catalogDescription !== '') {
            return $catalogDescription;
        }

        return 'Событие требует проверки по журналам сервиса.';
    }

    /**
     * @param array<string, mixed> $catalog
     * @param array<string, mixed> $details
     */
    public function resolveRecommendation(array $catalog, array $details): string
    {
        $recommendation = $this->accessor->stringValue($details, ['recommendation']);
        if ($recommendation !== null && $this->accessor->looksLocalized($recommendation)) {
            return $recommendation;
        }

        $catalogRecommendation = trim((string) ($catalog['recommendation'] ?? ''));
        if ($catalogRecommendation !== '') {
            return $catalogRecommendation;
        }

        return 'Проверьте детали алерта и состояние сервисов.';
    }

    /**
     * @param array<string, mixed> $details
     */
    public function resolveMessage(string $code, ?string $type, array $details, string $description): string
    {
        $rawMessage = $this->accessor->stringValue($details, ['message', 'msg', 'reason', 'error_message']);

        if ($code === 'biz_ae3_task_failed') {
            $translatedTaskFailure = $this->codeTranslator->translateByCode($code, $rawMessage, $details);
            if ($translatedTaskFailure !== null) {
                return $translatedTaskFailure;
            }
        }

        if ($rawMessage !== null && $this->accessor->looksLocalized($rawMessage)) {
            return $rawMessage;
        }

        $translatedByCode = $this->codeTranslator->translateByCode($code, $rawMessage, $details);
        if ($translatedByCode !== null) {
            return $translatedByCode;
        }

        if ($rawMessage !== null) {
            $translatedRaw = $this->codeTranslator->translateRawMessage($rawMessage);
            if ($translatedRaw !== null) {
                return $translatedRaw;
            }
        }

        $translatedType = $this->typeTranslator->translate($type);
        if ($translatedType !== null && $translatedType !== 'Системное предупреждение') {
            return $translatedType;
        }

        return $description;
    }
}
