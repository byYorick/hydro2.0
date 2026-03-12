<?php

use Illuminate\Database\Migrations\Migration;

return new class extends Migration
{
    public function up(): void
    {
        DB::unprepared(<<<'SQL'
            CREATE OR REPLACE FUNCTION notify_intent_terminal()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.status IN ('completed', 'failed', 'cancelled')
                   AND (OLD.status IS DISTINCT FROM NEW.status) THEN
                    PERFORM pg_notify(
                        'scheduler_intent_terminal',
                        json_build_object(
                            'intent_id',  NEW.id,
                            'zone_id',    NEW.zone_id,
                            'status',     NEW.status,
                            'error_code', NEW.error_code
                        )::text
                    );
                END IF;
                RETURN NEW;
            END;
            $$;

            DROP TRIGGER IF EXISTS trg_intent_terminal ON zone_automation_intents;

            CREATE TRIGGER trg_intent_terminal
            AFTER UPDATE ON zone_automation_intents
            FOR EACH ROW EXECUTE FUNCTION notify_intent_terminal();
        SQL);
    }

    public function down(): void
    {
        DB::unprepared(<<<'SQL'
            DROP TRIGGER IF EXISTS trg_intent_terminal ON zone_automation_intents;
            DROP FUNCTION IF EXISTS notify_intent_terminal();
        SQL);
    }
};
