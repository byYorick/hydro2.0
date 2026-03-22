<?php

namespace App\Http\Middleware;

use App\Models\SystemAutomationSetting;
use App\Services\SystemAutomationSettingsCatalog;
use Illuminate\Http\Request;
use Inertia\Middleware;

class HandleInertiaRequests extends Middleware
{
    /**
     * The root template that is loaded on the first page visit.
     *
     * @var string
     */
    protected $rootView = 'app';

    /**
     * Determine the current asset version.
     */
    public function version(Request $request): ?string
    {
        return parent::version($request);
    }

    /**
     * Define the props that are shared by default.
     *
     * @return array<string, mixed>
     */
    public function share(Request $request): array
    {
        return [
            ...parent::share($request),
            'auth' => [
                'user' => $request->user(),
            ],
            'automationDefaults' => static function (): array {
                try {
                    return SystemAutomationSetting::forNamespace('automation_defaults');
                } catch (\RuntimeException) {
                    return SystemAutomationSettingsCatalog::defaults('automation_defaults');
                }
            },
            'automationCommandTemplates' => static function (): array {
                try {
                    return SystemAutomationSetting::forNamespace('automation_command_templates');
                } catch (\RuntimeException) {
                    return SystemAutomationSettingsCatalog::defaults('automation_command_templates');
                }
            },
            'processCalibrationDefaults' => static function (): array {
                try {
                    return SystemAutomationSetting::forNamespace('process_calibration_defaults');
                } catch (\RuntimeException) {
                    return SystemAutomationSettingsCatalog::defaults('process_calibration_defaults');
                }
            },
        ];
    }
}
