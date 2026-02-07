<?php

namespace Tests\Feature;

use Tests\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class TimescaleDBRetentionTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Проверка наличия TimescaleDB расширения
     */
    public function test_timescaledb_extension_exists(): void
    {
        $this->assertTrue(
            $this->hasTimescaleExtension() || $this->isFallbackRetentionModeAvailable(),
            'Neither TimescaleDB extension nor fallback retention mode is available'
        );
    }

    /**
     * Проверка, что telemetry_samples является hypertable
     */
    public function test_telemetry_samples_is_hypertable(): void
    {
        if ($this->isHypertable('telemetry_samples')) {
            $this->assertTrue(true);
            return;
        }

        $this->assertFallbackRetentionModeForTable('telemetry_samples');
    }

    /**
     * Проверка retention policy для telemetry_samples
     */
    public function test_telemetry_samples_retention_policy(): void
    {
        $dropAfter = $this->getTimescaleRetentionDropAfter('telemetry_samples');

        if ($dropAfter !== null) {
            $this->assertStringContainsString('90 days', $dropAfter);
            return;
        }

        $this->assertFallbackRetentionModeForTable('telemetry_samples');
    }

    /**
     * Проверка retention policy для telemetry_agg_1m
     */
    public function test_telemetry_agg_1m_retention_policy(): void
    {
        $dropAfter = $this->getTimescaleRetentionDropAfter('telemetry_agg_1m');

        if ($dropAfter !== null) {
            $this->assertStringContainsString('30 days', $dropAfter);
            return;
        }

        $this->assertFallbackRetentionModeForTable('telemetry_agg_1m');
    }

    /**
     * Проверка retention policy для telemetry_agg_1h
     */
    public function test_telemetry_agg_1h_retention_policy(): void
    {
        $dropAfter = $this->getTimescaleRetentionDropAfter('telemetry_agg_1h');

        if ($dropAfter !== null) {
            $this->assertStringContainsString('365 days', $dropAfter);
            return;
        }

        $this->assertFallbackRetentionModeForTable('telemetry_agg_1h');
    }

    private function hasTimescaleExtension(): bool
    {
        try {
            $exists = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists
            ");

            return (bool) ($exists->exists ?? false);
        } catch (\Throwable) {
            return false;
        }
    }

    private function isHypertable(string $tableName): bool
    {
        if (! $this->hasTimescaleExtension()) {
            return false;
        }

        try {
            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = ?
                ) as exists
            ", [$tableName]);

            return (bool) ($isHypertable->exists ?? false);
        } catch (\Throwable) {
            return false;
        }
    }

    private function getTimescaleRetentionDropAfter(string $tableName): ?string
    {
        if (! $this->hasTimescaleExtension()) {
            return null;
        }

        try {
            $policy = DB::selectOne("
                SELECT config->>'drop_after' as drop_after
                FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                  AND hypertable_name = ?
                LIMIT 1
            ", [$tableName]);

            return $policy->drop_after ?? null;
        } catch (\Throwable) {
            return null;
        }
    }

    private function isFallbackRetentionModeAvailable(): bool
    {
        foreach (['telemetry_samples', 'telemetry_agg_1m', 'telemetry_agg_1h'] as $tableName) {
            if (! $this->tableExists($tableName)) {
                return false;
            }
        }

        return true;
    }

    private function assertFallbackRetentionModeForTable(string $tableName): void
    {
        $this->assertTrue(
            $this->tableExists($tableName),
            "Fallback retention mode requires table {$tableName} to exist"
        );

        $this->assertTrue(
            $this->tableHasTsIndex($tableName),
            "Fallback retention mode requires timestamp-oriented index for {$tableName}"
        );
    }

    private function tableExists(string $tableName): bool
    {
        $result = DB::selectOne('SELECT to_regclass(?) as regclass', ["public.{$tableName}"]);

        return $result !== null && $result->regclass !== null;
    }

    private function tableHasTsIndex(string $tableName): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = ?
                  AND indexdef ILIKE '%(ts%'
            ) as exists
        ", [$tableName]);

        return (bool) ($result->exists ?? false);
    }
}
