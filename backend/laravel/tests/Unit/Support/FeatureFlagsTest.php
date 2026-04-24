<?php

declare(strict_types=1);

namespace Tests\Unit\Support;

use App\Models\User;
use App\Support\FeatureFlags;
use Tests\TestCase;

/**
 * Unit-тесты резолва role-aware feature-flag'а для rollout Scheduler Cockpit.
 */
class FeatureFlagsTest extends TestCase
{
    public function test_returns_true_when_enabled_globally(): void
    {
        config()->set('features.scheduler_cockpit_ui', [
            'enabled_globally' => true,
            'enabled_for_roles' => [],
        ]);

        $user = new User(['role' => 'viewer']);

        self::assertTrue(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $user));
    }

    public function test_returns_true_when_role_in_allowed_list(): void
    {
        config()->set('features.scheduler_cockpit_ui', [
            'enabled_globally' => false,
            'enabled_for_roles' => ['engineer', 'admin'],
        ]);

        $engineer = new User(['role' => 'engineer']);
        $admin = new User(['role' => 'admin']);
        $operator = new User(['role' => 'operator']);

        self::assertTrue(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $engineer));
        self::assertTrue(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $admin));
        self::assertFalse(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $operator));
    }

    public function test_returns_false_without_user_in_cohort_mode(): void
    {
        config()->set('features.scheduler_cockpit_ui', [
            'enabled_globally' => false,
            'enabled_for_roles' => ['engineer'],
        ]);

        self::assertFalse(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, null));
    }

    public function test_backwards_compat_plain_bool_true(): void
    {
        config()->set('features.scheduler_cockpit_ui', true);

        self::assertTrue(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, null));
    }

    public function test_backwards_compat_plain_bool_false(): void
    {
        config()->set('features.scheduler_cockpit_ui', false);

        self::assertFalse(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, null));
        self::assertFalse(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, new User(['role' => 'admin'])));
    }

    public function test_viewer_role_fallback_for_missing_role(): void
    {
        config()->set('features.scheduler_cockpit_ui', [
            'enabled_globally' => false,
            'enabled_for_roles' => ['viewer'],
        ]);

        $user = new User;

        self::assertTrue(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $user));
    }

    public function test_empty_roles_list_with_global_off_disables_flag(): void
    {
        config()->set('features.scheduler_cockpit_ui', [
            'enabled_globally' => false,
            'enabled_for_roles' => [],
        ]);

        $user = new User(['role' => 'engineer']);

        self::assertFalse(FeatureFlags::isEnabled(FeatureFlags::SCHEDULER_COCKPIT_UI, $user));
    }
}
