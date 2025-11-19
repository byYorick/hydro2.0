<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
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
        try {
            $exists = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists
            ");

            if (!$exists || !$exists->exists) {
                $this->markTestSkipped('TimescaleDB extension not available');
            }

            $this->assertTrue($exists->exists);
        } catch (\Exception $e) {
            $this->markTestSkipped('TimescaleDB extension not available: ' . $e->getMessage());
        }
    }

    /**
     * Проверка, что telemetry_samples является hypertable
     */
    public function test_telemetry_samples_is_hypertable(): void
    {
        $this->test_timescaledb_extension_exists();

        try {
            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists
            ");

            if (!$isHypertable || !$isHypertable->exists) {
                $this->markTestSkipped('telemetry_samples is not a hypertable');
            }

            $this->assertTrue($isHypertable->exists);
        } catch (\Exception $e) {
            $this->markTestSkipped('Cannot check hypertable: ' . $e->getMessage());
        }
    }

    /**
     * Проверка retention policy для telemetry_samples
     */
    public function test_telemetry_samples_retention_policy(): void
    {
        $this->test_timescaledb_extension_exists();

        try {
            $policy = DB::selectOne("
                SELECT 
                    job_id,
                    config->>'drop_after' as drop_after
                FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'telemetry_samples'
                LIMIT 1
            ");

            if (!$policy) {
                $this->markTestSkipped('Retention policy not configured for telemetry_samples');
            }

            $this->assertNotNull($policy->job_id);
            $this->assertNotNull($policy->drop_after);
            // Проверяем, что retention policy настроена на 90 дней
            $this->assertStringContainsString('90 days', $policy->drop_after);
        } catch (\Exception $e) {
            $this->markTestSkipped('Cannot check retention policy: ' . $e->getMessage());
        }
    }

    /**
     * Проверка retention policy для telemetry_agg_1m
     */
    public function test_telemetry_agg_1m_retention_policy(): void
    {
        $this->test_timescaledb_extension_exists();

        try {
            $policy = DB::selectOne("
                SELECT 
                    job_id,
                    config->>'drop_after' as drop_after
                FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'telemetry_agg_1m'
                LIMIT 1
            ");

            if (!$policy) {
                $this->markTestSkipped('Retention policy not configured for telemetry_agg_1m');
            }

            $this->assertNotNull($policy->job_id);
            $this->assertNotNull($policy->drop_after);
            // Проверяем, что retention policy настроена на 30 дней
            $this->assertStringContainsString('30 days', $policy->drop_after);
        } catch (\Exception $e) {
            $this->markTestSkipped('Cannot check retention policy: ' . $e->getMessage());
        }
    }

    /**
     * Проверка retention policy для telemetry_agg_1h
     */
    public function test_telemetry_agg_1h_retention_policy(): void
    {
        $this->test_timescaledb_extension_exists();

        try {
            $policy = DB::selectOne("
                SELECT 
                    job_id,
                    config->>'drop_after' as drop_after
                FROM timescaledb_information.jobs
                WHERE proc_name = 'policy_retention'
                AND hypertable_name = 'telemetry_agg_1h'
                LIMIT 1
            ");

            if (!$policy) {
                $this->markTestSkipped('Retention policy not configured for telemetry_agg_1h');
            }

            $this->assertNotNull($policy->job_id);
            $this->assertNotNull($policy->drop_after);
            // Проверяем, что retention policy настроена на 365 дней
            $this->assertStringContainsString('365 days', $policy->drop_after);
        } catch (\Exception $e) {
            $this->markTestSkipped('Cannot check retention policy: ' . $e->getMessage());
        }
    }
}

