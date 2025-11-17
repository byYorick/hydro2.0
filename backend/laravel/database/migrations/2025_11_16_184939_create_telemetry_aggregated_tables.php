<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Отключаем транзакции для этой миграции,
     * так как create_hypertable требует commit.
     */
    public $withinTransaction = false;

    /**
     * Run the migrations.
     * Создает таблицы для агрегированных данных телеметрии.
     */
    public function up(): void
    {
        // Таблица агрегации по 1 минуте
        Schema::create('telemetry_agg_1m', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->string('channel')->nullable();
            $table->string('metric_type');
            $table->float('value_avg')->nullable();
            $table->float('value_min')->nullable();
            $table->float('value_max')->nullable();
            $table->float('value_median')->nullable();
            $table->integer('sample_count')->default(0);
            $table->timestamp('ts')->index();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['zone_id', 'metric_type', 'ts'], 'telemetry_agg_1m_zone_metric_ts_idx');
            $table->index(['node_id', 'ts'], 'telemetry_agg_1m_node_ts_idx');
            $table->unique(['zone_id', 'node_id', 'channel', 'metric_type', 'ts'], 'telemetry_agg_1m_unique');
        });

        // Преобразуем в hypertable (только для PostgreSQL)
        // Выполняем вне транзакции миграции, так как create_hypertable требует commit
        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                // Проверяем, не является ли таблица уже hypertable
                $isHypertable = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'telemetry_agg_1m'
                    ) as exists;
                ");
                
                if (!$isHypertable || !$isHypertable->exists) {
                    // Удаляем существующий primary key
                    DB::statement("ALTER TABLE telemetry_agg_1m DROP CONSTRAINT IF EXISTS telemetry_agg_1m_pkey;");
                    
                    // Создаем составной primary key с ts (требуется для TimescaleDB)
                    DB::statement("ALTER TABLE telemetry_agg_1m ADD PRIMARY KEY (id, ts);");
                    
                    // Выполняем вне транзакции миграции
                    DB::unprepared("
                        SELECT create_hypertable(
                            'telemetry_agg_1m',
                            'ts',
                            chunk_time_interval => INTERVAL '7 days',
                            if_not_exists => TRUE
                        );
                    ");
                }
            } catch (\Exception $e) {
                // TimescaleDB недоступно - пропускаем создание hypertable
                // Логируем ошибку, но не прерываем миграцию
                \Log::warning('Failed to create hypertable for telemetry_agg_1m: ' . $e->getMessage());
            }
        }

        // Таблица агрегации по 1 часу
        Schema::create('telemetry_agg_1h', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->string('channel')->nullable();
            $table->string('metric_type');
            $table->float('value_avg')->nullable();
            $table->float('value_min')->nullable();
            $table->float('value_max')->nullable();
            $table->float('value_median')->nullable();
            $table->integer('sample_count')->default(0);
            $table->timestamp('ts')->index();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['zone_id', 'metric_type', 'ts'], 'telemetry_agg_1h_zone_metric_ts_idx');
            $table->index(['node_id', 'ts'], 'telemetry_agg_1h_node_ts_idx');
            $table->unique(['zone_id', 'node_id', 'channel', 'metric_type', 'ts'], 'telemetry_agg_1h_unique');
        });

        // Преобразуем в hypertable (только для PostgreSQL)
        // Выполняем вне транзакции миграции, так как create_hypertable требует commit
        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                // Проверяем, не является ли таблица уже hypertable
                $isHypertable = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'telemetry_agg_1h'
                    ) as exists;
                ");
                
                if (!$isHypertable || !$isHypertable->exists) {
                    // Удаляем существующий primary key
                    DB::statement("ALTER TABLE telemetry_agg_1h DROP CONSTRAINT IF EXISTS telemetry_agg_1h_pkey;");
                    
                    // Создаем составной primary key с ts (требуется для TimescaleDB)
                    DB::statement("ALTER TABLE telemetry_agg_1h ADD PRIMARY KEY (id, ts);");
                    
                    // Выполняем вне транзакции миграции
                    DB::unprepared("
                        SELECT create_hypertable(
                            'telemetry_agg_1h',
                            'ts',
                            chunk_time_interval => INTERVAL '30 days',
                            if_not_exists => TRUE
                        );
                    ");
                }
            } catch (\Exception $e) {
                // TimescaleDB недоступно - пропускаем создание hypertable
                // Логируем ошибку, но не прерываем миграцию
                \Log::warning('Failed to create hypertable for telemetry_agg_1h: ' . $e->getMessage());
            }
        }

        // Таблица дневной агрегации
        Schema::create('telemetry_daily', function (Blueprint $table) {
            $table->id();
            $table->foreignId('zone_id')->nullable()->constrained('zones')->nullOnDelete();
            $table->foreignId('node_id')->nullable()->constrained('nodes')->nullOnDelete();
            $table->string('channel')->nullable();
            $table->string('metric_type');
            $table->float('value_avg')->nullable();
            $table->float('value_min')->nullable();
            $table->float('value_max')->nullable();
            $table->float('value_median')->nullable();
            $table->integer('sample_count')->default(0);
            $table->date('date')->index();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['zone_id', 'metric_type', 'date'], 'telemetry_daily_zone_metric_date_idx');
            $table->index(['node_id', 'date'], 'telemetry_daily_node_date_idx');
            $table->unique(['zone_id', 'node_id', 'channel', 'metric_type', 'date'], 'telemetry_daily_unique');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Удаляем hypertable (только для PostgreSQL)
        if (DB::getDriverName() === 'pgsql') {
            try {
                DB::statement("SELECT drop_hypertable('telemetry_agg_1h', if_exists => TRUE);");
            } catch (\Exception $e) {
                // Игнорируем ошибки при удалении
            }
            try {
                DB::statement("SELECT drop_hypertable('telemetry_agg_1m', if_exists => TRUE);");
            } catch (\Exception $e) {
                // Игнорируем ошибки при удалении
            }
        }
        
        Schema::dropIfExists('telemetry_daily');
        Schema::dropIfExists('telemetry_agg_1h');
        Schema::dropIfExists('telemetry_agg_1m');
    }
};
