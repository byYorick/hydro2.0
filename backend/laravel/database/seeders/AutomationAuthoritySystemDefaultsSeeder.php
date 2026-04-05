<?php

namespace Database\Seeders;

use App\Services\AutomationConfigDocumentService;
use Illuminate\Database\Seeder;

/**
 * Гарантирует наличие системных документов authority (в т.ч. system.automation_defaults с water_manual_irrigation_sec и др.).
 * Идемпотентно: существующие записи не перезаписываются.
 */
class AutomationAuthoritySystemDefaultsSeeder extends Seeder
{
    public function run(): void
    {
        app(AutomationConfigDocumentService::class)->ensureSystemDefaults();
    }
}
