<?php

namespace Tests\Unit\Services;

use App\Services\SystemAutomationSettingsCatalog;
use InvalidArgumentException;
use PHPUnit\Framework\TestCase;

class SystemAutomationSettingsOptionsTest extends TestCase
{
    public function test_strategy_and_ph_only_choice_are_presented_as_named_options(): void
    {
        $fields = SystemAutomationSettingsCatalog::flattenFields('automation_defaults');
        $this->assertSame(['task', 'smart_soil_v1'], $fields['water_irrigation_decision_strategy']['options']);
        $this->assertSame('По влажности субстрата', $fields['water_irrigation_decision_strategy']['option_labels']['smart_soil_v1']);
        $this->assertArrayHasKey('none', $fields['water_irrigation_ec_component']['option_labels']);
        $result = SystemAutomationSettingsCatalog::validate('automation_defaults', ['water_irrigation_ec_component' => 'none']);
        $this->assertSame('none', $result['water_irrigation_ec_component']);
    }

    public function test_unknown_strategy_is_rejected_at_settings_save(): void
    {
        $this->expectException(InvalidArgumentException::class);
        $this->expectExceptionMessage('выберите допустимый вариант');
        SystemAutomationSettingsCatalog::validate('automation_defaults', ['water_irrigation_decision_strategy' => 'smart_typo']);
    }
}
