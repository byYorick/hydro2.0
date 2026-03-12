<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement(
            "
            CREATE OR REPLACE FUNCTION public.ae_notify_command_status()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                payload jsonb;
            BEGIN
                payload := jsonb_build_object(
                    'cmd_id', NEW.cmd_id,
                    'zone_id', NEW.zone_id,
                    'status', NEW.status,
                    'updated_at', COALESCE(NEW.updated_at, NOW())
                );
                PERFORM pg_notify('ae_command_status', payload::text);
                RETURN NEW;
            END;
            $$;
            "
        );

        DB::statement(
            "
            CREATE OR REPLACE FUNCTION public.ae_notify_signal_update()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                signal_zone_id bigint;
                signal_kind text;
                payload jsonb;
            BEGIN
                IF TG_TABLE_NAME = 'zone_events' THEN
                    signal_zone_id := NEW.zone_id;
                    signal_kind := 'zone_event';
                ELSIF TG_TABLE_NAME = 'telemetry_last' THEN
                    SELECT s.zone_id INTO signal_zone_id
                    FROM sensors s
                    WHERE s.id = NEW.sensor_id
                    LIMIT 1;
                    signal_kind := 'telemetry_last';
                ELSE
                    signal_zone_id := NULL;
                    signal_kind := TG_TABLE_NAME;
                END IF;

                IF signal_zone_id IS NULL THEN
                    RETURN NEW;
                END IF;

                payload := jsonb_build_object(
                    'zone_id', signal_zone_id,
                    'kind', signal_kind,
                    'updated_at', NOW()
                );
                PERFORM pg_notify('ae_signal_update', payload::text);
                RETURN NEW;
            END;
            $$;
            "
        );

        DB::statement('DROP TRIGGER IF EXISTS trg_ae_command_status_notify ON commands;');
        DB::statement(
            "
            CREATE TRIGGER trg_ae_command_status_notify
            AFTER INSERT OR UPDATE OF status, updated_at
            ON commands
            FOR EACH ROW
            EXECUTE FUNCTION public.ae_notify_command_status();
            "
        );

        DB::statement('DROP TRIGGER IF EXISTS trg_ae_signal_update_zone_events ON zone_events;');
        DB::statement(
            "
            CREATE TRIGGER trg_ae_signal_update_zone_events
            AFTER INSERT OR UPDATE
            ON zone_events
            FOR EACH ROW
            EXECUTE FUNCTION public.ae_notify_signal_update();
            "
        );

        DB::statement('DROP TRIGGER IF EXISTS trg_ae_signal_update_telemetry_last ON telemetry_last;');
        DB::statement(
            "
            CREATE TRIGGER trg_ae_signal_update_telemetry_last
            AFTER INSERT OR UPDATE OF last_value, last_ts, updated_at
            ON telemetry_last
            FOR EACH ROW
            EXECUTE FUNCTION public.ae_notify_signal_update();
            "
        );
    }

    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        DB::statement('DROP TRIGGER IF EXISTS trg_ae_command_status_notify ON commands;');
        DB::statement('DROP TRIGGER IF EXISTS trg_ae_signal_update_zone_events ON zone_events;');
        DB::statement('DROP TRIGGER IF EXISTS trg_ae_signal_update_telemetry_last ON telemetry_last;');
        DB::statement('DROP FUNCTION IF EXISTS public.ae_notify_command_status();');
        DB::statement('DROP FUNCTION IF EXISTS public.ae_notify_signal_update();');
    }
};
