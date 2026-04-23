--
-- PostgreSQL database dump
--

\restrict 7Bu3CzYpaCjGLHzw5Arb3bcdEENof5MygKAPH3QYNIfqmSNkRayNgBsFC12ZZKN

-- Dumped from database version 16.11
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: timescaledb; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public;


--
-- Name: ae_notify_command_status(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.ae_notify_command_status() RETURNS trigger
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


--
-- Name: ae_notify_signal_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.ae_notify_signal_update() RETURNS trigger
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


--
-- Name: notify_intent_terminal(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.notify_intent_terminal() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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


--
-- Name: retention_policy_commands(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.retention_policy_commands() RETURNS void
    LANGUAGE plpgsql
    AS $$
                BEGIN
                    DELETE FROM commands 
                    WHERE created_at < NOW() - INTERVAL '365 days';
                END;
                $$;


--
-- Name: retention_policy_zone_events(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.retention_policy_zone_events() RETURNS void
    LANGUAGE plpgsql
    AS $$
                BEGIN
                    DELETE FROM zone_events 
                    WHERE created_at < NOW() - INTERVAL '365 days';
                END;
                $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ae_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ae_commands (
    id bigint NOT NULL,
    task_id bigint NOT NULL,
    step_no integer NOT NULL,
    node_uid character varying(128) NOT NULL,
    channel character varying(64) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    external_id character varying(191),
    publish_status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    terminal_status character varying(32),
    ack_received_at timestamp(0) with time zone,
    terminal_at timestamp(0) with time zone,
    last_error text,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    stage_name character varying(64),
    CONSTRAINT ae_commands_publish_status_check CHECK (((publish_status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT ae_commands_step_no_check CHECK ((step_no >= 1)),
    CONSTRAINT ae_commands_terminal_status_check CHECK (((terminal_status IS NULL) OR ((terminal_status)::text = ANY ((ARRAY['DONE'::character varying, 'NO_EFFECT'::character varying, 'ERROR'::character varying, 'INVALID'::character varying, 'BUSY'::character varying, 'TIMEOUT'::character varying, 'SEND_FAILED'::character varying])::text[]))))
);


--
-- Name: ae_commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ae_commands_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ae_commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ae_commands_id_seq OWNED BY public.ae_commands.id;


--
-- Name: ae_stage_transitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ae_stage_transitions (
    id bigint NOT NULL,
    task_id bigint NOT NULL,
    from_stage character varying(64),
    to_stage character varying(64) NOT NULL,
    workflow_phase character varying(32),
    triggered_at timestamp(0) with time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ae_stage_transitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ae_stage_transitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ae_stage_transitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ae_stage_transitions_id_seq OWNED BY public.ae_stage_transitions.id;


--
-- Name: ae_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ae_tasks (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    task_type character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    idempotency_key character varying(191) NOT NULL,
    scheduled_for timestamp(0) with time zone NOT NULL,
    due_at timestamp(0) with time zone NOT NULL,
    claimed_by character varying(191),
    claimed_at timestamp(0) with time zone,
    error_code character varying(128),
    error_message text,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp(0) with time zone,
    intent_source character varying(64),
    intent_trigger character varying(64),
    intent_id bigint,
    intent_meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    topology character varying(64) DEFAULT 'two_tank'::character varying NOT NULL,
    current_stage character varying(64) DEFAULT 'startup'::character varying NOT NULL,
    workflow_phase character varying(32) DEFAULT 'idle'::character varying NOT NULL,
    stage_deadline_at timestamp(0) with time zone,
    stage_retry_count smallint DEFAULT '0'::smallint NOT NULL,
    stage_entered_at timestamp(0) with time zone,
    clean_fill_cycle smallint DEFAULT '0'::smallint NOT NULL,
    corr_step character varying(32),
    corr_attempt smallint,
    corr_max_attempts smallint,
    corr_activated_here boolean,
    corr_stabilization_sec smallint,
    corr_return_stage_success character varying(64),
    corr_return_stage_fail character varying(64),
    corr_outcome_success boolean,
    corr_needs_ec boolean,
    corr_ec_node_uid character varying(128),
    corr_ec_channel character varying(64),
    corr_ec_duration_ms integer,
    corr_needs_ph_up boolean,
    corr_needs_ph_down boolean,
    corr_ph_node_uid character varying(128),
    corr_ph_channel character varying(64),
    corr_ph_duration_ms integer,
    corr_wait_until timestamp(0) with time zone,
    corr_ec_attempt smallint,
    corr_ph_attempt smallint,
    pending_manual_step character varying(64),
    control_mode_snapshot character varying(16),
    corr_ec_max_attempts smallint,
    corr_ph_max_attempts smallint,
    corr_ec_component character varying(100),
    corr_ec_amount_ml numeric(12,3),
    corr_ph_amount_ml numeric(12,3),
    corr_limit_policy_logged boolean DEFAULT false NOT NULL,
    irrigation_mode character varying(16),
    irrigation_requested_duration_sec integer,
    irrigation_decision_strategy character varying(64),
    irrigation_decision_outcome character varying(32),
    irrigation_decision_reason_code character varying(128),
    irrigation_decision_degraded boolean,
    irrigation_replay_count smallint DEFAULT '0'::smallint NOT NULL,
    irrigation_wait_ready_deadline_at timestamp(0) with time zone,
    irrigation_setup_deadline_at timestamp(0) with time zone,
    corr_ec_dose_sequence_json json,
    corr_ec_current_seq_index integer DEFAULT 0 NOT NULL,
    irrigation_decision_config jsonb,
    irrigation_bundle_revision character varying(64),
    corr_snapshot_event_id bigint,
    corr_snapshot_created_at timestamp(0) without time zone,
    corr_snapshot_cmd_id character varying(255),
    corr_snapshot_source_event_type character varying(255),
    start_event_emitted boolean DEFAULT false NOT NULL,
    irr_probe_failure_streak smallint DEFAULT '0'::smallint NOT NULL,
    CONSTRAINT ae_tasks_clean_fill_cycle_check CHECK ((clean_fill_cycle >= 0)),
    CONSTRAINT ae_tasks_corr_ec_max_attempts_check CHECK (((corr_ec_max_attempts IS NULL) OR (corr_ec_max_attempts >= 1))),
    CONSTRAINT ae_tasks_corr_ph_max_attempts_check CHECK (((corr_ph_max_attempts IS NULL) OR (corr_ph_max_attempts >= 1))),
    CONSTRAINT ae_tasks_corr_step_check CHECK (((corr_step IS NULL) OR ((corr_step)::text = ANY ((ARRAY['corr_activate'::character varying, 'corr_wait_stable'::character varying, 'corr_check'::character varying, 'corr_dose_ec'::character varying, 'corr_wait_ec'::character varying, 'corr_dose_ph'::character varying, 'corr_wait_ph'::character varying, 'corr_dose_ph_piggyback'::character varying, 'corr_wait_ph_piggyback'::character varying, 'corr_deactivate'::character varying, 'corr_done'::character varying])::text[])))),
    CONSTRAINT ae_tasks_current_stage_check CHECK (((current_stage)::text <> ''::text)),
    CONSTRAINT ae_tasks_irr_probe_failure_streak_check CHECK ((irr_probe_failure_streak >= 0)),
    CONSTRAINT ae_tasks_irrigation_decision_outcome_check CHECK (((irrigation_decision_outcome IS NULL) OR ((irrigation_decision_outcome)::text = ANY ((ARRAY['run'::character varying, 'skip'::character varying, 'degraded_run'::character varying, 'fail'::character varying])::text[])))),
    CONSTRAINT ae_tasks_irrigation_mode_check CHECK (((irrigation_mode IS NULL) OR ((irrigation_mode)::text = ANY ((ARRAY['normal'::character varying, 'force'::character varying])::text[])))),
    CONSTRAINT ae_tasks_irrigation_replay_count_check CHECK ((irrigation_replay_count >= 0)),
    CONSTRAINT ae_tasks_stage_retry_count_check CHECK ((stage_retry_count >= 0)),
    CONSTRAINT ae_tasks_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'claimed'::character varying, 'running'::character varying, 'waiting_command'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT ae_tasks_task_type_check CHECK (((task_type)::text = ANY ((ARRAY['cycle_start'::character varying, 'irrigation_start'::character varying, 'lighting_tick'::character varying])::text[]))),
    CONSTRAINT ae_tasks_topology_check CHECK (((topology)::text <> ''::text)),
    CONSTRAINT ae_tasks_workflow_phase_check CHECK (((workflow_phase)::text = ANY ((ARRAY['idle'::character varying, 'tank_filling'::character varying, 'tank_recirc'::character varying, 'ready'::character varying, 'irrigating'::character varying, 'irrig_recirc'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: ae_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ae_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ae_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ae_tasks_id_seq OWNED BY public.ae_tasks.id;


--
-- Name: ae_zone_leases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ae_zone_leases (
    zone_id bigint NOT NULL,
    owner character varying(191) NOT NULL,
    leased_until timestamp(0) with time zone NOT NULL,
    updated_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: aggregator_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aggregator_state (
    id bigint NOT NULL,
    aggregation_type character varying(32) NOT NULL,
    last_ts timestamp(0) without time zone,
    updated_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: aggregator_state_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.aggregator_state_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: aggregator_state_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.aggregator_state_id_seq OWNED BY public.aggregator_state.id;


--
-- Name: ai_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_logs (
    id bigint NOT NULL,
    zone_id bigint,
    action character varying(255) NOT NULL,
    details jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: ai_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ai_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ai_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ai_logs_id_seq OWNED BY public.ai_logs.id;


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id bigint NOT NULL,
    zone_id bigint,
    source character varying(255) DEFAULT 'biz'::character varying NOT NULL,
    code character varying(255),
    type character varying(255) NOT NULL,
    details jsonb,
    status character varying(255) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    resolved_at timestamp(0) without time zone,
    error_count integer DEFAULT 1 NOT NULL,
    category character varying(32),
    severity character varying(16),
    node_uid character varying(100),
    hardware_id character varying(100),
    first_seen_at timestamp(0) without time zone,
    last_seen_at timestamp(0) without time zone
);


--
-- Name: alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alerts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alerts_id_seq OWNED BY public.alerts.id;


--
-- Name: automation_config_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_config_documents (
    id bigint NOT NULL,
    namespace character varying(128) NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_id bigint NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'valid'::character varying NOT NULL,
    source character varying(32) DEFAULT 'migration'::character varying NOT NULL,
    checksum character varying(64) NOT NULL,
    updated_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: automation_config_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_config_documents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_config_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_config_documents_id_seq OWNED BY public.automation_config_documents.id;


--
-- Name: automation_config_preset_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_config_preset_versions (
    id bigint NOT NULL,
    preset_id bigint NOT NULL,
    namespace character varying(128) NOT NULL,
    scope character varying(32) NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    checksum character varying(64) NOT NULL,
    changed_by bigint,
    changed_at timestamp(0) with time zone NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: automation_config_preset_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_config_preset_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_config_preset_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_config_preset_versions_id_seq OWNED BY public.automation_config_preset_versions.id;


--
-- Name: automation_config_presets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_config_presets (
    id bigint NOT NULL,
    namespace character varying(128) NOT NULL,
    scope character varying(32) DEFAULT 'custom'::character varying NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    description text,
    schema_version integer DEFAULT 1 NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    updated_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: automation_config_presets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_config_presets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_config_presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_config_presets_id_seq OWNED BY public.automation_config_presets.id;


--
-- Name: automation_config_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_config_versions (
    id bigint NOT NULL,
    document_id bigint NOT NULL,
    namespace character varying(128) NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_id bigint NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'valid'::character varying NOT NULL,
    source character varying(32) DEFAULT 'migration'::character varying NOT NULL,
    checksum character varying(64) NOT NULL,
    changed_by bigint,
    changed_at timestamp(0) with time zone NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: automation_config_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_config_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_config_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_config_versions_id_seq OWNED BY public.automation_config_versions.id;


--
-- Name: automation_config_violations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_config_violations (
    id bigint NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_id bigint NOT NULL,
    namespace character varying(128) NOT NULL,
    path character varying(255) DEFAULT ''::character varying NOT NULL,
    code character varying(128) NOT NULL,
    severity character varying(32) NOT NULL,
    blocking boolean DEFAULT false NOT NULL,
    message text NOT NULL,
    detected_at timestamp(0) with time zone NOT NULL
);


--
-- Name: automation_config_violations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_config_violations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_config_violations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_config_violations_id_seq OWNED BY public.automation_config_violations.id;


--
-- Name: automation_effective_bundles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.automation_effective_bundles (
    id bigint NOT NULL,
    scope_type character varying(32) NOT NULL,
    scope_id bigint NOT NULL,
    bundle_revision character varying(64) NOT NULL,
    schema_revision character varying(64) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    violations jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'valid'::character varying NOT NULL,
    compiled_at timestamp(0) with time zone NOT NULL,
    inputs_checksum character varying(64) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: automation_effective_bundles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.automation_effective_bundles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: automation_effective_bundles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.automation_effective_bundles_id_seq OWNED BY public.automation_effective_bundles.id;


--
-- Name: cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache (
    key character varying(255) NOT NULL,
    value text NOT NULL,
    expiration integer NOT NULL
);


--
-- Name: cache_locks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache_locks (
    key character varying(255) NOT NULL,
    owner character varying(255) NOT NULL,
    expiration integer NOT NULL
);


--
-- Name: channel_bindings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.channel_bindings (
    id bigint NOT NULL,
    infrastructure_instance_id bigint NOT NULL,
    node_channel_id bigint NOT NULL,
    direction character varying(255) NOT NULL,
    role character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT channel_bindings_direction_check CHECK (((direction)::text = ANY ((ARRAY['actuator'::character varying, 'sensor'::character varying])::text[])))
);


--
-- Name: channel_bindings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.channel_bindings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: channel_bindings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.channel_bindings_id_seq OWNED BY public.channel_bindings.id;


--
-- Name: command_acks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.command_acks (
    id bigint NOT NULL,
    command_id bigint NOT NULL,
    ack_type character varying(255) DEFAULT 'accepted'::character varying NOT NULL,
    measured_current numeric(10,4),
    measured_flow numeric(10,4),
    error_message text,
    metadata jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT command_acks_ack_type_check CHECK (((ack_type)::text = ANY ((ARRAY['accepted'::character varying, 'executed'::character varying, 'verified'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: command_acks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.command_acks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: command_acks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.command_acks_id_seq OWNED BY public.command_acks.id;


--
-- Name: command_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.command_audit (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    command_type character varying(50) NOT NULL,
    command_data jsonb NOT NULL,
    telemetry_snapshot jsonb,
    decision_context jsonb,
    pid_state jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: command_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.command_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: command_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.command_audit_id_seq OWNED BY public.command_audit.id;


--
-- Name: command_tracking; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.command_tracking (
    id bigint NOT NULL,
    cmd_id character varying(100) NOT NULL,
    zone_id bigint NOT NULL,
    command jsonb NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    sent_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp(0) without time zone,
    response jsonb,
    error text,
    latency_seconds double precision,
    context jsonb
);


--
-- Name: command_tracking_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.command_tracking_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: command_tracking_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.command_tracking_id_seq OWNED BY public.command_tracking.id;


--
-- Name: commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands (
    id bigint NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
)
PARTITION BY RANGE (created_at);


--
-- Name: commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.commands_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.commands_id_seq OWNED BY public.commands.id;


--
-- Name: commands_partitioned_2026_03; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_03 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_04; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_04 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_05; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_05 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_06; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_06 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_07; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_07 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_08; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_08 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_09; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_09 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_10 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_11; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_11 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2026_12; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2026_12 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2027_01; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2027_01 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2027_02; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2027_02 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2027_03; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2027_03 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: commands_partitioned_2027_04; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands_partitioned_2027_04 (
    id bigint DEFAULT nextval('public.commands_id_seq'::regclass) NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    cmd character varying(255) NOT NULL,
    params jsonb,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    cmd_id character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    sent_at timestamp(0) without time zone,
    ack_at timestamp(0) without time zone,
    failed_at timestamp(0) without time zone,
    source character varying(255),
    error_code character varying(64),
    error_message character varying(512),
    result_code integer DEFAULT 0 NOT NULL,
    duration_ms integer,
    cycle_id bigint,
    context_type character varying(255) DEFAULT 'manual'::character varying,
    command_type character varying(255),
    payload jsonb,
    request_id character varying(128)
);


--
-- Name: failed_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failed_jobs (
    id bigint NOT NULL,
    uuid character varying(255) NOT NULL,
    connection text NOT NULL,
    queue text NOT NULL,
    payload text NOT NULL,
    exception text NOT NULL,
    failed_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.failed_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.failed_jobs_id_seq OWNED BY public.failed_jobs.id;


--
-- Name: firmware_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.firmware_files (
    id bigint NOT NULL,
    node_type character varying(255) NOT NULL,
    version character varying(255) NOT NULL,
    file_path character varying(255) NOT NULL,
    checksum_sha256 character varying(255) NOT NULL,
    release_notes text,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: firmware_files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.firmware_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: firmware_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.firmware_files_id_seq OWNED BY public.firmware_files.id;


--
-- Name: greenhouse_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.greenhouse_types (
    id bigint NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    sort_order smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: greenhouse_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.greenhouse_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: greenhouse_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.greenhouse_types_id_seq OWNED BY public.greenhouse_types.id;


--
-- Name: greenhouses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.greenhouses (
    id bigint NOT NULL,
    uid character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    timezone character varying(255),
    type character varying(255),
    coordinates json,
    description text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    provisioning_token character varying(64) NOT NULL,
    greenhouse_type_id bigint
);


--
-- Name: greenhouses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.greenhouses_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: greenhouses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.greenhouses_id_seq OWNED BY public.greenhouses.id;


--
-- Name: grow_cycle_phase_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grow_cycle_phase_steps (
    id bigint NOT NULL,
    grow_cycle_phase_id bigint NOT NULL,
    recipe_revision_phase_step_id bigint,
    step_index integer DEFAULT 0 NOT NULL,
    name character varying(255) NOT NULL,
    offset_hours integer DEFAULT 0 NOT NULL,
    action character varying(255),
    description text,
    ph_target numeric(4,2),
    ph_min numeric(4,2),
    ph_max numeric(4,2),
    ec_target numeric(5,2),
    ec_min numeric(5,2),
    ec_max numeric(5,2),
    irrigation_mode character varying(255),
    irrigation_interval_sec integer,
    irrigation_duration_sec integer,
    lighting_photoperiod_hours integer,
    lighting_start_time time(0) without time zone,
    mist_interval_sec integer,
    mist_duration_sec integer,
    mist_mode character varying(255),
    temp_air_target numeric(5,2),
    humidity_target numeric(5,2),
    co2_target integer,
    extensions jsonb,
    started_at timestamp(0) without time zone,
    ended_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT grow_cycle_phase_steps_irrigation_mode_check CHECK (((irrigation_mode)::text = ANY ((ARRAY['SUBSTRATE'::character varying, 'RECIRC'::character varying])::text[]))),
    CONSTRAINT grow_cycle_phase_steps_mist_mode_check CHECK (((mist_mode)::text = ANY ((ARRAY['NORMAL'::character varying, 'SPRAY'::character varying])::text[])))
);


--
-- Name: grow_cycle_phase_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grow_cycle_phase_steps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grow_cycle_phase_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grow_cycle_phase_steps_id_seq OWNED BY public.grow_cycle_phase_steps.id;


--
-- Name: grow_cycle_phases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grow_cycle_phases (
    id bigint NOT NULL,
    grow_cycle_id bigint NOT NULL,
    recipe_revision_phase_id bigint,
    phase_index integer DEFAULT 0 NOT NULL,
    name character varying(255) NOT NULL,
    ph_target numeric(4,2),
    ph_min numeric(4,2),
    ph_max numeric(4,2),
    ec_target numeric(5,2),
    ec_min numeric(5,2),
    ec_max numeric(5,2),
    irrigation_mode character varying(255),
    irrigation_interval_sec integer,
    irrigation_duration_sec integer,
    lighting_photoperiod_hours integer,
    lighting_start_time time(0) without time zone,
    mist_interval_sec integer,
    mist_duration_sec integer,
    mist_mode character varying(255),
    temp_air_target numeric(5,2),
    humidity_target numeric(5,2),
    co2_target integer,
    progress_model character varying(255),
    duration_hours integer,
    duration_days integer,
    base_temp_c numeric(4,2),
    target_gdd numeric(8,2),
    dli_target numeric(6,2),
    extensions jsonb,
    started_at timestamp(0) without time zone,
    ended_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    nutrient_program_code character varying(64),
    nutrient_npk_ratio_pct numeric(5,2),
    nutrient_calcium_ratio_pct numeric(5,2),
    nutrient_micro_ratio_pct numeric(5,2),
    nutrient_npk_dose_ml_l numeric(8,3),
    nutrient_calcium_dose_ml_l numeric(8,3),
    nutrient_micro_dose_ml_l numeric(8,3),
    nutrient_npk_product_id bigint,
    nutrient_calcium_product_id bigint,
    nutrient_micro_product_id bigint,
    nutrient_dose_delay_sec integer,
    nutrient_ec_stop_tolerance numeric(5,3),
    nutrient_mode character varying(32),
    nutrient_magnesium_ratio_pct numeric(5,2),
    nutrient_magnesium_dose_ml_l numeric(8,3),
    nutrient_magnesium_product_id bigint,
    nutrient_solution_volume_l numeric(8,2),
    nutrient_ec_dosing_mode character varying(32),
    irrigation_system_type character varying(32),
    substrate_type character varying(64),
    day_night_enabled boolean,
    phase_advance_strategy character varying(32) DEFAULT 'time'::character varying NOT NULL,
    CONSTRAINT grow_cycle_phases_advance_strategy_check CHECK (((phase_advance_strategy)::text = ANY ((ARRAY['time'::character varying, 'gdd'::character varying, 'dli'::character varying, 'ai'::character varying, 'manual_only'::character varying])::text[]))),
    CONSTRAINT grow_cycle_phases_irrigation_mode_check CHECK (((irrigation_mode)::text = ANY ((ARRAY['SUBSTRATE'::character varying, 'RECIRC'::character varying])::text[]))),
    CONSTRAINT grow_cycle_phases_mist_mode_check CHECK (((mist_mode)::text = ANY ((ARRAY['NORMAL'::character varying, 'SPRAY'::character varying])::text[]))),
    CONSTRAINT grow_cycle_phases_phase_index_nonneg CHECK ((phase_index >= 0))
);


--
-- Name: grow_cycle_phases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grow_cycle_phases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grow_cycle_phases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grow_cycle_phases_id_seq OWNED BY public.grow_cycle_phases.id;


--
-- Name: grow_cycle_transitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grow_cycle_transitions (
    id bigint NOT NULL,
    grow_cycle_id bigint NOT NULL,
    from_phase_id bigint,
    to_phase_id bigint,
    from_step_id bigint,
    to_step_id bigint,
    trigger_type character varying(255) NOT NULL,
    comment text,
    triggered_by bigint,
    metadata jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: grow_cycle_transitions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grow_cycle_transitions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grow_cycle_transitions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grow_cycle_transitions_id_seq OWNED BY public.grow_cycle_transitions.id;


--
-- Name: grow_cycles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grow_cycles (
    id bigint NOT NULL,
    greenhouse_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    plant_id bigint,
    recipe_id bigint,
    status character varying(255) DEFAULT 'PLANNED'::character varying NOT NULL,
    started_at timestamp(0) without time zone,
    recipe_started_at timestamp(0) without time zone,
    expected_harvest_at timestamp(0) without time zone,
    actual_harvest_at timestamp(0) without time zone,
    batch_label character varying(255),
    notes text,
    settings jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    planting_at timestamp(0) without time zone,
    recipe_revision_id bigint NOT NULL,
    phase_started_at timestamp(0) without time zone,
    step_started_at timestamp(0) without time zone,
    progress_meta jsonb,
    current_phase_id bigint,
    current_step_id bigint,
    current_stage_code character varying(32),
    current_stage_started_at timestamp(0) without time zone
);


--
-- Name: grow_cycles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grow_cycles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grow_cycles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grow_cycles_id_seq OWNED BY public.grow_cycles.id;


--
-- Name: grow_stage_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grow_stage_templates (
    id bigint NOT NULL,
    name character varying(128) NOT NULL,
    code character varying(64) NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    default_duration_days integer,
    ui_meta jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: grow_stage_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.grow_stage_templates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: grow_stage_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.grow_stage_templates_id_seq OWNED BY public.grow_stage_templates.id;


--
-- Name: harvests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.harvests (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    recipe_id bigint,
    harvest_date date NOT NULL,
    yield_weight_kg numeric(8,2),
    yield_count integer,
    quality_score numeric(3,2),
    notes jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: harvests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.harvests_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: harvests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.harvests_id_seq OWNED BY public.harvests.id;


--
-- Name: infrastructure_instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.infrastructure_instances (
    id bigint NOT NULL,
    owner_type character varying(255) NOT NULL,
    owner_id bigint NOT NULL,
    asset_type character varying(255) NOT NULL,
    label character varying(255) NOT NULL,
    required boolean DEFAULT false NOT NULL,
    capacity_liters numeric(10,2),
    flow_rate numeric(10,2),
    specs jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT infrastructure_instances_asset_type_check CHECK (((asset_type)::text = ANY ((ARRAY['PUMP'::character varying, 'MISTER'::character varying, 'TANK_CLEAN'::character varying, 'TANK_WORKING'::character varying, 'TANK_NUTRIENT'::character varying, 'DRAIN'::character varying, 'LIGHT'::character varying, 'VENT'::character varying, 'HEATER'::character varying, 'FAN'::character varying, 'CO2_INJECTOR'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: infrastructure_instances_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.infrastructure_instances_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: infrastructure_instances_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.infrastructure_instances_id_seq OWNED BY public.infrastructure_instances.id;


--
-- Name: job_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_batches (
    id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    total_jobs integer NOT NULL,
    pending_jobs integer NOT NULL,
    failed_jobs integer NOT NULL,
    failed_job_ids text NOT NULL,
    options text,
    cancelled_at integer,
    created_at integer NOT NULL,
    finished_at integer
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id bigint NOT NULL,
    queue character varying(255) NOT NULL,
    payload text NOT NULL,
    attempts smallint NOT NULL,
    reserved_at integer,
    available_at integer NOT NULL,
    created_at integer NOT NULL
);


--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: laravel_scheduler_active_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.laravel_scheduler_active_tasks (
    id bigint NOT NULL,
    task_id character varying(128) NOT NULL,
    zone_id bigint NOT NULL,
    task_type character varying(64) NOT NULL,
    schedule_key character varying(255) NOT NULL,
    correlation_id character varying(255) NOT NULL,
    status character varying(32) NOT NULL,
    accepted_at timestamp(0) with time zone NOT NULL,
    due_at timestamp(0) with time zone,
    expires_at timestamp(0) with time zone,
    last_polled_at timestamp(0) with time zone,
    terminal_at timestamp(0) with time zone,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(0) with time zone,
    updated_at timestamp(0) with time zone
);


--
-- Name: laravel_scheduler_active_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.laravel_scheduler_active_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: laravel_scheduler_active_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.laravel_scheduler_active_tasks_id_seq OWNED BY public.laravel_scheduler_active_tasks.id;


--
-- Name: laravel_scheduler_cycle_duration_aggregates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.laravel_scheduler_cycle_duration_aggregates (
    id bigint NOT NULL,
    dispatch_mode character varying(64) NOT NULL,
    sample_count bigint DEFAULT '0'::bigint NOT NULL,
    sample_sum double precision DEFAULT '0'::double precision NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: laravel_scheduler_cycle_duration_aggregates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.laravel_scheduler_cycle_duration_aggregates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: laravel_scheduler_cycle_duration_aggregates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.laravel_scheduler_cycle_duration_aggregates_id_seq OWNED BY public.laravel_scheduler_cycle_duration_aggregates.id;


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.laravel_scheduler_cycle_duration_bucket_counts (
    id bigint NOT NULL,
    dispatch_mode character varying(64) NOT NULL,
    bucket_le character varying(32) NOT NULL,
    sample_count bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.laravel_scheduler_cycle_duration_bucket_counts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.laravel_scheduler_cycle_duration_bucket_counts_id_seq OWNED BY public.laravel_scheduler_cycle_duration_bucket_counts.id;


--
-- Name: laravel_scheduler_dispatch_metric_totals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.laravel_scheduler_dispatch_metric_totals (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    task_type character varying(64) NOT NULL,
    result character varying(64) NOT NULL,
    total bigint DEFAULT '0'::bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: laravel_scheduler_dispatch_metric_totals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.laravel_scheduler_dispatch_metric_totals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: laravel_scheduler_dispatch_metric_totals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.laravel_scheduler_dispatch_metric_totals_id_seq OWNED BY public.laravel_scheduler_dispatch_metric_totals.id;


--
-- Name: laravel_scheduler_zone_cursors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.laravel_scheduler_zone_cursors (
    zone_id bigint NOT NULL,
    cursor_at timestamp(0) with time zone NOT NULL,
    catchup_policy character varying(32) NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(0) with time zone,
    updated_at timestamp(0) with time zone
);


--
-- Name: migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.migrations (
    id integer NOT NULL,
    migration character varying(255) NOT NULL,
    batch integer NOT NULL
);


--
-- Name: migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.migrations_id_seq OWNED BY public.migrations.id;


--
-- Name: node_channels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_channels (
    id bigint NOT NULL,
    node_id bigint NOT NULL,
    channel character varying(255) NOT NULL,
    type character varying(255),
    metric character varying(255),
    unit character varying(255),
    config jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    last_seen_at timestamp(0) without time zone,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: node_channels_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.node_channels_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: node_channels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.node_channels_id_seq OWNED BY public.node_channels.id;


--
-- Name: node_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_logs (
    id bigint NOT NULL,
    node_id bigint NOT NULL,
    level character varying(255) NOT NULL,
    message text NOT NULL,
    context jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: node_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.node_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: node_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.node_logs_id_seq OWNED BY public.node_logs.id;


--
-- Name: nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nodes (
    id bigint NOT NULL,
    zone_id bigint,
    uid character varying(64) NOT NULL,
    name character varying(255),
    type character varying(255) DEFAULT 'unknown'::character varying NOT NULL,
    fw_version character varying(255),
    last_seen_at timestamp(0) without time zone,
    status character varying(255) DEFAULT 'offline'::character varying NOT NULL,
    config jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    lifecycle_state character varying(32) DEFAULT 'UNPROVISIONED'::character varying NOT NULL,
    hardware_id character varying(128),
    last_heartbeat_at timestamp(0) without time zone,
    uptime_seconds integer,
    free_heap_bytes integer,
    rssi integer,
    hardware_revision character varying(64),
    first_seen_at timestamp(0) without time zone,
    validated boolean DEFAULT false NOT NULL,
    pending_zone_id bigint,
    error_count integer DEFAULT 0 NOT NULL,
    warning_count integer DEFAULT 0 NOT NULL,
    critical_count integer DEFAULT 0 NOT NULL,
    CONSTRAINT nodes_type_canonical_check CHECK (((type)::text = ANY ((ARRAY['ph'::character varying, 'ec'::character varying, 'climate'::character varying, 'irrig'::character varying, 'light'::character varying, 'relay'::character varying, 'water_sensor'::character varying, 'recirculation'::character varying, 'unknown'::character varying])::text[])))
);


--
-- Name: nodes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nodes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nodes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nodes_id_seq OWNED BY public.nodes.id;


--
-- Name: nutrient_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nutrient_products (
    id bigint NOT NULL,
    manufacturer character varying(128) NOT NULL,
    name character varying(191) NOT NULL,
    component character varying(16) NOT NULL,
    composition character varying(128),
    recommended_stage character varying(64),
    notes text,
    metadata jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: nutrient_products_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nutrient_products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nutrient_products_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nutrient_products_id_seq OWNED BY public.nutrient_products.id;


--
-- Name: parameter_predictions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parameter_predictions (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    metric_type character varying(64) NOT NULL,
    predicted_value double precision NOT NULL,
    confidence double precision,
    horizon_minutes integer NOT NULL,
    predicted_at timestamp(0) without time zone NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: parameter_predictions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.parameter_predictions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: parameter_predictions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.parameter_predictions_id_seq OWNED BY public.parameter_predictions.id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    email character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    created_at timestamp(0) without time zone
);


--
-- Name: pending_alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_alerts (
    id bigint NOT NULL,
    zone_id bigint,
    source character varying(255) DEFAULT 'biz'::character varying NOT NULL,
    code character varying(255),
    type character varying(255) NOT NULL,
    details jsonb,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 10 NOT NULL,
    last_attempt_at timestamp(0) without time zone,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    last_error text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    next_retry_at timestamp(0) with time zone,
    moved_to_dlq_at timestamp(0) with time zone,
    CONSTRAINT pending_alerts_source_check CHECK (((source)::text = ANY ((ARRAY['biz'::character varying, 'infra'::character varying, 'node'::character varying])::text[]))),
    CONSTRAINT pending_alerts_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'failed'::character varying, 'dlq'::character varying, 'ACTIVE'::character varying, 'RESOLVED'::character varying])::text[])))
);


--
-- Name: pending_alerts_dlq; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_alerts_dlq (
    id bigint NOT NULL,
    zone_id bigint,
    source character varying(16) NOT NULL,
    code character varying(64) NOT NULL,
    type character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    details jsonb,
    attempts integer NOT NULL,
    max_attempts integer,
    last_error text,
    failed_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    moved_to_dlq_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    original_id bigint,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: pending_alerts_dlq_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pending_alerts_dlq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pending_alerts_dlq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pending_alerts_dlq_id_seq OWNED BY public.pending_alerts_dlq.id;


--
-- Name: pending_alerts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pending_alerts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pending_alerts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pending_alerts_id_seq OWNED BY public.pending_alerts.id;


--
-- Name: pending_status_updates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_status_updates (
    id bigint NOT NULL,
    cmd_id character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    details jsonb,
    retry_count integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 10 NOT NULL,
    next_retry_at timestamp(0) with time zone,
    last_error text,
    moved_to_dlq_at timestamp(0) with time zone,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pending_status_updates_status_check CHECK (((status)::text = ANY ((ARRAY['SENT'::character varying, 'ACK'::character varying, 'DONE'::character varying, 'ERROR'::character varying, 'INVALID'::character varying, 'BUSY'::character varying, 'NO_EFFECT'::character varying])::text[])))
);


--
-- Name: pending_status_updates_dlq; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_status_updates_dlq (
    id bigint NOT NULL,
    cmd_id character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    details jsonb,
    retry_count integer NOT NULL,
    max_attempts integer,
    last_error text,
    failed_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    moved_to_dlq_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    original_id bigint,
    created_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pending_status_updates_dlq_status_check CHECK (((status)::text = ANY ((ARRAY['SENT'::character varying, 'ACK'::character varying, 'DONE'::character varying, 'ERROR'::character varying, 'INVALID'::character varying, 'BUSY'::character varying, 'NO_EFFECT'::character varying])::text[])))
);


--
-- Name: pending_status_updates_dlq_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pending_status_updates_dlq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pending_status_updates_dlq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pending_status_updates_dlq_id_seq OWNED BY public.pending_status_updates_dlq.id;


--
-- Name: pending_status_updates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pending_status_updates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pending_status_updates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pending_status_updates_id_seq OWNED BY public.pending_status_updates.id;


--
-- Name: personal_access_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.personal_access_tokens (
    id bigint NOT NULL,
    tokenable_type character varying(255) NOT NULL,
    tokenable_id bigint NOT NULL,
    name character varying(255) NOT NULL,
    token character varying(64) NOT NULL,
    abilities text,
    last_used_at timestamp(0) without time zone,
    expires_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: personal_access_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.personal_access_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: personal_access_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.personal_access_tokens_id_seq OWNED BY public.personal_access_tokens.id;


--
-- Name: pid_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pid_state (
    zone_id bigint NOT NULL,
    pid_type character varying(10) NOT NULL,
    integral double precision DEFAULT '0'::double precision NOT NULL,
    prev_error double precision,
    last_output_ms bigint DEFAULT '0'::bigint NOT NULL,
    stats jsonb,
    current_zone character varying(20),
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    last_dose_at timestamp(0) with time zone,
    prev_derivative double precision DEFAULT '0'::double precision NOT NULL,
    hold_until timestamp(0) with time zone,
    last_measurement_at timestamp(0) with time zone,
    last_measured_value double precision,
    feedforward_bias double precision DEFAULT '0'::double precision NOT NULL,
    no_effect_count integer DEFAULT 0 NOT NULL,
    last_correction_kind character varying(32)
);


--
-- Name: plant_cost_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_cost_items (
    id bigint NOT NULL,
    plant_id bigint NOT NULL,
    plant_price_version_id bigint,
    type character varying(255) NOT NULL,
    amount numeric(12,2) NOT NULL,
    currency character varying(8) DEFAULT 'RUB'::character varying NOT NULL,
    notes character varying(255),
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plant_cost_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_cost_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_cost_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_cost_items_id_seq OWNED BY public.plant_cost_items.id;


--
-- Name: plant_price_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_price_versions (
    id bigint NOT NULL,
    plant_id bigint NOT NULL,
    effective_from date,
    effective_to date,
    currency character varying(8) DEFAULT 'RUB'::character varying NOT NULL,
    seedling_cost numeric(12,2),
    substrate_cost numeric(12,2),
    nutrient_cost numeric(12,2),
    labor_cost numeric(12,2),
    protection_cost numeric(12,2),
    logistics_cost numeric(12,2),
    other_cost numeric(12,2),
    wholesale_price numeric(12,2),
    retail_price numeric(12,2),
    source character varying(255),
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plant_price_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_price_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_price_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_price_versions_id_seq OWNED BY public.plant_price_versions.id;


--
-- Name: plant_recipe; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_recipe (
    id bigint NOT NULL,
    plant_id bigint NOT NULL,
    recipe_id bigint NOT NULL,
    season character varying(255),
    site_type character varying(255),
    is_default boolean DEFAULT false NOT NULL,
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plant_recipe_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_recipe_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_recipe_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_recipe_id_seq OWNED BY public.plant_recipe.id;


--
-- Name: plant_sale_prices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_sale_prices (
    id bigint NOT NULL,
    plant_id bigint NOT NULL,
    plant_price_version_id bigint,
    channel character varying(255) NOT NULL,
    price numeric(12,2) NOT NULL,
    currency character varying(8) DEFAULT 'RUB'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plant_sale_prices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_sale_prices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_sale_prices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_sale_prices_id_seq OWNED BY public.plant_sale_prices.id;


--
-- Name: plant_zone; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plant_zone (
    id bigint NOT NULL,
    plant_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    assigned_at timestamp(0) without time zone,
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plant_zone_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plant_zone_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plant_zone_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plant_zone_id_seq OWNED BY public.plant_zone.id;


--
-- Name: plants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plants (
    id bigint NOT NULL,
    slug character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    species character varying(255),
    variety character varying(255),
    substrate_type character varying(255),
    growing_system character varying(255),
    photoperiod_preset character varying(255),
    seasonality character varying(255),
    icon_path character varying(255),
    description text,
    environment_requirements json,
    growth_phases json,
    recommended_recipes json,
    metadata json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: plants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plants_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plants_id_seq OWNED BY public.plants.id;


--
-- Name: presets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.presets (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    plant_type character varying(255) NOT NULL,
    ph_optimal_range jsonb,
    ec_range jsonb,
    vpd_range jsonb,
    light_intensity_range jsonb,
    climate_ranges jsonb,
    irrigation_behavior jsonb,
    growth_profile character varying(255) DEFAULT 'mid'::character varying NOT NULL,
    default_recipe_id bigint,
    description text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: presets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.presets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.presets_id_seq OWNED BY public.presets.id;


--
-- Name: pump_calibrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pump_calibrations (
    id bigint NOT NULL,
    node_channel_id bigint NOT NULL,
    component character varying(64),
    ml_per_sec numeric(12,6) NOT NULL,
    k_ms_per_ml_l numeric(12,6),
    duration_sec integer,
    actual_ml numeric(12,3),
    test_volume_l numeric(12,3),
    ec_before_ms numeric(12,6),
    ec_after_ms numeric(12,6),
    delta_ec_ms numeric(12,6),
    temperature_c numeric(12,3),
    source character varying(64) DEFAULT 'manual_calibration'::character varying NOT NULL,
    quality_score numeric(5,2),
    sample_count integer DEFAULT 1 NOT NULL,
    valid_from timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    valid_to timestamp(0) without time zone,
    is_active boolean DEFAULT true NOT NULL,
    meta jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    mode character varying(32) DEFAULT 'generic'::character varying NOT NULL,
    min_effective_ml numeric(12,3),
    transport_delay_sec integer,
    deadtime_sec integer,
    curve_points jsonb,
    CONSTRAINT pump_calibrations_ml_per_sec_runtime_bounds_check CHECK (((ml_per_sec >= 0.01) AND (ml_per_sec <= 100.0)))
);


--
-- Name: pump_calibrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pump_calibrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pump_calibrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pump_calibrations_id_seq OWNED BY public.pump_calibrations.id;


--
-- Name: recipe_analytics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_analytics (
    id bigint NOT NULL,
    recipe_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    start_date timestamp(0) without time zone NOT NULL,
    end_date timestamp(0) without time zone,
    total_duration_hours integer,
    avg_ph_deviation numeric(6,3),
    avg_ec_deviation numeric(6,3),
    alerts_count integer DEFAULT 0 NOT NULL,
    final_yield jsonb,
    efficiency_score numeric(5,2),
    additional_metrics jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: recipe_analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recipe_analytics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipe_analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recipe_analytics_id_seq OWNED BY public.recipe_analytics.id;


--
-- Name: recipe_revision_phase_steps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_revision_phase_steps (
    id bigint NOT NULL,
    phase_id bigint NOT NULL,
    step_index integer DEFAULT 0 NOT NULL,
    name character varying(255) NOT NULL,
    offset_hours integer DEFAULT 0 NOT NULL,
    action character varying(255),
    description text,
    ph_target numeric(4,2),
    ph_min numeric(4,2),
    ph_max numeric(4,2),
    ec_target numeric(5,2),
    ec_min numeric(5,2),
    ec_max numeric(5,2),
    irrigation_mode character varying(255),
    irrigation_interval_sec integer,
    irrigation_duration_sec integer,
    lighting_photoperiod_hours integer,
    lighting_start_time time(0) without time zone,
    mist_interval_sec integer,
    mist_duration_sec integer,
    mist_mode character varying(255),
    temp_air_target numeric(5,2),
    humidity_target numeric(5,2),
    co2_target integer,
    extensions jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT recipe_revision_phase_steps_irrigation_mode_check CHECK (((irrigation_mode)::text = ANY ((ARRAY['SUBSTRATE'::character varying, 'RECIRC'::character varying])::text[]))),
    CONSTRAINT recipe_revision_phase_steps_mist_mode_check CHECK (((mist_mode)::text = ANY ((ARRAY['NORMAL'::character varying, 'SPRAY'::character varying])::text[])))
);


--
-- Name: recipe_revision_phase_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recipe_revision_phase_steps_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipe_revision_phase_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recipe_revision_phase_steps_id_seq OWNED BY public.recipe_revision_phase_steps.id;


--
-- Name: recipe_revision_phases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_revision_phases (
    id bigint NOT NULL,
    recipe_revision_id bigint NOT NULL,
    stage_template_id bigint,
    phase_index integer DEFAULT 0 NOT NULL,
    name character varying(255) NOT NULL,
    ph_target numeric(4,2),
    ph_min numeric(4,2),
    ph_max numeric(4,2),
    ec_target numeric(5,2),
    ec_min numeric(5,2),
    ec_max numeric(5,2),
    irrigation_mode character varying(255),
    irrigation_interval_sec integer,
    irrigation_duration_sec integer,
    lighting_photoperiod_hours integer,
    lighting_start_time time(0) without time zone,
    mist_interval_sec integer,
    mist_duration_sec integer,
    mist_mode character varying(255),
    temp_air_target numeric(5,2),
    humidity_target numeric(5,2),
    co2_target integer,
    progress_model character varying(255),
    duration_hours integer,
    duration_days integer,
    base_temp_c numeric(4,2),
    target_gdd numeric(8,2),
    dli_target numeric(6,2),
    extensions jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    nutrient_program_code character varying(64),
    nutrient_npk_ratio_pct numeric(5,2),
    nutrient_calcium_ratio_pct numeric(5,2),
    nutrient_micro_ratio_pct numeric(5,2),
    nutrient_npk_dose_ml_l numeric(8,3),
    nutrient_calcium_dose_ml_l numeric(8,3),
    nutrient_micro_dose_ml_l numeric(8,3),
    nutrient_npk_product_id bigint,
    nutrient_calcium_product_id bigint,
    nutrient_micro_product_id bigint,
    nutrient_dose_delay_sec integer,
    nutrient_ec_stop_tolerance numeric(5,3),
    nutrient_mode character varying(32),
    nutrient_magnesium_ratio_pct numeric(5,2),
    nutrient_magnesium_dose_ml_l numeric(8,3),
    nutrient_magnesium_product_id bigint,
    nutrient_solution_volume_l numeric(8,2),
    nutrient_ec_dosing_mode character varying(32),
    irrigation_system_type character varying(32),
    substrate_type character varying(64),
    day_night_enabled boolean,
    phase_advance_strategy character varying(32) DEFAULT 'time'::character varying NOT NULL,
    CONSTRAINT recipe_revision_phases_advance_strategy_check CHECK (((phase_advance_strategy)::text = ANY ((ARRAY['time'::character varying, 'gdd'::character varying, 'dli'::character varying, 'ai'::character varying, 'manual_only'::character varying])::text[]))),
    CONSTRAINT recipe_revision_phases_irrigation_mode_check CHECK (((irrigation_mode)::text = ANY ((ARRAY['SUBSTRATE'::character varying, 'RECIRC'::character varying])::text[]))),
    CONSTRAINT recipe_revision_phases_mist_mode_check CHECK (((mist_mode)::text = ANY ((ARRAY['NORMAL'::character varying, 'SPRAY'::character varying])::text[]))),
    CONSTRAINT recipe_revision_phases_phase_index_nonneg CHECK ((phase_index >= 0))
);


--
-- Name: recipe_revision_phases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recipe_revision_phases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipe_revision_phases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recipe_revision_phases_id_seq OWNED BY public.recipe_revision_phases.id;


--
-- Name: recipe_revisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipe_revisions (
    id bigint NOT NULL,
    recipe_id bigint NOT NULL,
    revision_number integer DEFAULT 1 NOT NULL,
    status character varying(255) DEFAULT 'DRAFT'::character varying NOT NULL,
    description text,
    created_by bigint,
    published_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: recipe_revisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recipe_revisions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipe_revisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recipe_revisions_id_seq OWNED BY public.recipe_revisions.id;


--
-- Name: recipes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recipes (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    metadata jsonb
);


--
-- Name: recipes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.recipes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: recipes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.recipes_id_seq OWNED BY public.recipes.id;


--
-- Name: scheduler_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scheduler_logs (
    id bigint NOT NULL,
    task_name character varying(255) NOT NULL,
    status character varying(255) NOT NULL,
    details jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: scheduler_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scheduler_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scheduler_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scheduler_logs_id_seq OWNED BY public.scheduler_logs.id;


--
-- Name: sensor_calibrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sensor_calibrations (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    node_channel_id bigint NOT NULL,
    sensor_type character varying(16) NOT NULL,
    status character varying(32) DEFAULT 'started'::character varying NOT NULL,
    point_1_reference numeric(12,4),
    point_1_command_id character varying(128),
    point_1_sent_at timestamp(0) with time zone,
    point_1_result character varying(16),
    point_1_error text,
    point_2_reference numeric(12,4),
    point_2_command_id character varying(128),
    point_2_sent_at timestamp(0) with time zone,
    point_2_result character varying(16),
    point_2_error text,
    completed_at timestamp(0) with time zone,
    calibrated_by bigint,
    notes text,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT chk_sensor_calibrations_sensor_type CHECK (((sensor_type)::text = ANY ((ARRAY['ph'::character varying, 'ec'::character varying])::text[]))),
    CONSTRAINT chk_sensor_calibrations_status CHECK (((status)::text = ANY ((ARRAY['started'::character varying, 'point_1_pending'::character varying, 'point_1_done'::character varying, 'point_2_pending'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: sensor_calibrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sensor_calibrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sensor_calibrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sensor_calibrations_id_seq OWNED BY public.sensor_calibrations.id;


--
-- Name: sensors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sensors (
    id bigint NOT NULL,
    greenhouse_id bigint NOT NULL,
    zone_id bigint,
    node_id bigint,
    scope character varying(255) DEFAULT 'inside'::character varying NOT NULL,
    type character varying(255) DEFAULT 'TEMPERATURE'::character varying NOT NULL,
    label character varying(255) NOT NULL,
    unit character varying(255),
    specs jsonb,
    is_active boolean DEFAULT true NOT NULL,
    last_read_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    CONSTRAINT sensors_scope_check CHECK (((scope)::text = ANY ((ARRAY['inside'::character varying, 'outside'::character varying])::text[]))),
    CONSTRAINT sensors_type_check CHECK (((type)::text = ANY ((ARRAY['TEMPERATURE'::character varying, 'HUMIDITY'::character varying, 'CO2'::character varying, 'PH'::character varying, 'EC'::character varying, 'WATER_LEVEL'::character varying, 'FLOW_RATE'::character varying, 'PUMP_CURRENT'::character varying, 'WIND_SPEED'::character varying, 'WIND_DIRECTION'::character varying, 'PRESSURE'::character varying, 'LIGHT_INTENSITY'::character varying, 'SOIL_MOISTURE'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- Name: sensors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sensors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sensors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sensors_id_seq OWNED BY public.sensors.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id character varying(255) NOT NULL,
    user_id bigint,
    ip_address character varying(45),
    user_agent text,
    payload text NOT NULL,
    last_activity integer NOT NULL
);


--
-- Name: simulation_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.simulation_events (
    id bigint NOT NULL,
    simulation_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    service character varying(64) NOT NULL,
    stage character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    level character varying(16) DEFAULT 'info'::character varying NOT NULL,
    message text,
    payload jsonb,
    occurred_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: simulation_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.simulation_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: simulation_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.simulation_events_id_seq OWNED BY public.simulation_events.id;


--
-- Name: simulation_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.simulation_reports (
    id bigint NOT NULL,
    simulation_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    status character varying(32) DEFAULT 'running'::character varying NOT NULL,
    started_at timestamp(0) without time zone,
    finished_at timestamp(0) without time zone,
    summary_json jsonb,
    phases_json jsonb,
    metrics_json jsonb,
    errors_json jsonb,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: simulation_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.simulation_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: simulation_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.simulation_reports_id_seq OWNED BY public.simulation_reports.id;


--
-- Name: substrates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.substrates (
    id bigint NOT NULL,
    code character varying(64) NOT NULL,
    name character varying(128) NOT NULL,
    components jsonb DEFAULT '[]'::jsonb NOT NULL,
    applicable_systems jsonb DEFAULT '[]'::jsonb NOT NULL,
    notes text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: substrates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.substrates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: substrates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.substrates_id_seq OWNED BY public.substrates.id;


--
-- Name: system_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_logs (
    id bigint NOT NULL,
    level character varying(255) NOT NULL,
    message text NOT NULL,
    context jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: system_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.system_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: system_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_logs_id_seq OWNED BY public.system_logs.id;


--
-- Name: telemetry_agg_1h; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telemetry_agg_1h (
    id bigint NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    metric_type character varying(255) NOT NULL,
    value_avg double precision,
    value_min double precision,
    value_max double precision,
    value_median double precision,
    sample_count integer DEFAULT 0 NOT NULL,
    ts timestamp(0) without time zone NOT NULL,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: telemetry_agg_1h_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telemetry_agg_1h_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telemetry_agg_1h_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telemetry_agg_1h_id_seq OWNED BY public.telemetry_agg_1h.id;


--
-- Name: telemetry_agg_1m; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telemetry_agg_1m (
    id bigint NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    metric_type character varying(255) NOT NULL,
    value_avg double precision,
    value_min double precision,
    value_max double precision,
    value_median double precision,
    sample_count integer DEFAULT 0 NOT NULL,
    ts timestamp(0) without time zone NOT NULL,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: telemetry_agg_1m_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telemetry_agg_1m_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telemetry_agg_1m_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telemetry_agg_1m_id_seq OWNED BY public.telemetry_agg_1m.id;


--
-- Name: telemetry_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telemetry_daily (
    id bigint NOT NULL,
    zone_id bigint,
    node_id bigint,
    channel character varying(255),
    metric_type character varying(255) NOT NULL,
    value_avg double precision,
    value_min double precision,
    value_max double precision,
    value_median double precision,
    sample_count integer DEFAULT 0 NOT NULL,
    date date NOT NULL,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: telemetry_daily_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telemetry_daily_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telemetry_daily_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telemetry_daily_id_seq OWNED BY public.telemetry_daily.id;


--
-- Name: telemetry_last; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telemetry_last (
    sensor_id bigint NOT NULL,
    last_value numeric(10,4) NOT NULL,
    last_ts timestamp(0) without time zone NOT NULL,
    last_quality character varying(255) DEFAULT 'GOOD'::character varying NOT NULL,
    updated_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT telemetry_last_last_quality_check CHECK (((last_quality)::text = ANY ((ARRAY['GOOD'::character varying, 'BAD'::character varying, 'UNCERTAIN'::character varying])::text[])))
);


--
-- Name: telemetry_samples; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.telemetry_samples (
    id bigint NOT NULL,
    sensor_id bigint NOT NULL,
    ts timestamp(0) without time zone NOT NULL,
    zone_id bigint,
    cycle_id bigint,
    value numeric(10,4) NOT NULL,
    quality character varying(255) DEFAULT 'GOOD'::character varying NOT NULL,
    metadata jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT telemetry_samples_quality_check CHECK (((quality)::text = ANY ((ARRAY['GOOD'::character varying, 'BAD'::character varying, 'UNCERTAIN'::character varying])::text[])))
);


--
-- Name: telemetry_samples_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.telemetry_samples_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: telemetry_samples_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.telemetry_samples_id_seq OWNED BY public.telemetry_samples.id;


--
-- Name: unassigned_node_errors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.unassigned_node_errors (
    id bigint NOT NULL,
    hardware_id character varying(255) NOT NULL,
    error_message text NOT NULL,
    error_code character varying(255),
    severity character varying(255) DEFAULT 'ERROR'::character varying NOT NULL,
    topic character varying(255) NOT NULL,
    last_payload jsonb,
    count integer DEFAULT 1 NOT NULL,
    first_seen_at timestamp(0) without time zone NOT NULL,
    last_seen_at timestamp(0) without time zone NOT NULL,
    node_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: unassigned_node_errors_archive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.unassigned_node_errors_archive (
    id bigint NOT NULL,
    hardware_id character varying(255) NOT NULL,
    error_message text NOT NULL,
    error_code character varying(255),
    severity character varying(255) DEFAULT 'ERROR'::character varying NOT NULL,
    topic character varying(255) NOT NULL,
    last_payload jsonb,
    count integer DEFAULT 1 NOT NULL,
    first_seen_at timestamp(0) without time zone NOT NULL,
    last_seen_at timestamp(0) without time zone NOT NULL,
    node_id bigint,
    archived_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    attached_at timestamp(0) without time zone,
    attached_zone_id bigint
);


--
-- Name: unassigned_node_errors_archive_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.unassigned_node_errors_archive_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: unassigned_node_errors_archive_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.unassigned_node_errors_archive_id_seq OWNED BY public.unassigned_node_errors_archive.id;


--
-- Name: unassigned_node_errors_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.unassigned_node_errors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: unassigned_node_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.unassigned_node_errors_id_seq OWNED BY public.unassigned_node_errors.id;


--
-- Name: user_greenhouses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_greenhouses (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    greenhouse_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: user_greenhouses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_greenhouses_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_greenhouses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_greenhouses_id_seq OWNED BY public.user_greenhouses.id;


--
-- Name: user_zones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_zones (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    zone_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: user_zones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_zones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_zones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_zones_id_seq OWNED BY public.user_zones.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    email_verified_at timestamp(0) without time zone,
    password character varying(255) NOT NULL,
    remember_token character varying(100),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    role character varying(255) DEFAULT 'operator'::character varying NOT NULL,
    preferences jsonb
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: zone_automation_intents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_automation_intents (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    intent_type character varying(64) NOT NULL,
    payload jsonb,
    idempotency_key character varying(191) NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    not_before timestamp(0) with time zone,
    claimed_at timestamp(0) with time zone,
    completed_at timestamp(0) with time zone,
    error_code character varying(128),
    error_message text,
    retry_count integer DEFAULT 0 NOT NULL,
    max_retries integer DEFAULT 3 NOT NULL,
    created_at timestamp(0) with time zone,
    updated_at timestamp(0) with time zone,
    task_type character varying(64) DEFAULT 'cycle_start'::character varying NOT NULL,
    topology character varying(64) DEFAULT 'two_tank'::character varying NOT NULL,
    irrigation_mode character varying(32),
    irrigation_requested_duration_sec integer,
    intent_source character varying(64),
    CONSTRAINT zone_automation_intents_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'claimed'::character varying, 'running'::character varying, 'completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: zone_automation_intents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_automation_intents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_automation_intents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_automation_intents_id_seq OWNED BY public.zone_automation_intents.id;


--
-- Name: zone_automation_presets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_automation_presets (
    id bigint NOT NULL,
    name character varying(128) NOT NULL,
    slug character varying(128) NOT NULL,
    description text,
    scope character varying(16) DEFAULT 'custom'::character varying NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    tanks_count smallint DEFAULT '2'::smallint NOT NULL,
    irrigation_system_type character varying(32) DEFAULT 'dwc'::character varying NOT NULL,
    correction_preset_id bigint,
    correction_profile character varying(32),
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_by bigint,
    updated_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: zone_automation_presets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_automation_presets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_automation_presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_automation_presets_id_seq OWNED BY public.zone_automation_presets.id;


--
-- Name: zone_automation_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_automation_state (
    zone_id bigint NOT NULL,
    state jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: zone_config_changes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_config_changes (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    revision bigint NOT NULL,
    namespace character varying(64) NOT NULL,
    diff_json jsonb NOT NULL,
    user_id bigint,
    reason text,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: zone_config_changes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_config_changes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_config_changes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_config_changes_id_seq OWNED BY public.zone_config_changes.id;


--
-- Name: zone_correction_presets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_correction_presets (
    id bigint NOT NULL,
    slug character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    scope character varying(16) DEFAULT 'custom'::character varying NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    description text,
    config jsonb NOT NULL,
    created_by bigint,
    updated_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: zone_correction_presets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_correction_presets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_correction_presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_correction_presets_id_seq OWNED BY public.zone_correction_presets.id;


--
-- Name: zone_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
)
PARTITION BY RANGE (created_at);


--
-- Name: zone_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_events_id_seq OWNED BY public.zone_events.id;


--
-- Name: zone_events_partitioned_2026_03; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_03 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_04; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_04 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_05; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_05 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_06; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_06 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_07; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_07 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_08; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_08 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_09; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_09 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_10; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_10 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_11; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_11 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2026_12; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2026_12 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2027_01; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2027_01 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2027_02; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2027_02 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2027_03; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2027_03 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_events_partitioned_2027_04; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_events_partitioned_2027_04 (
    id bigint DEFAULT nextval('public.zone_events_id_seq'::regclass) NOT NULL,
    zone_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    payload_json jsonb,
    created_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    entity_type character varying(255),
    entity_id text,
    server_ts bigint,
    details jsonb,
    processed_at timestamp(0) without time zone
);


--
-- Name: zone_model_params; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_model_params (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    model_type character varying(32) NOT NULL,
    params jsonb NOT NULL,
    calibrated_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: zone_model_params_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_model_params_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_model_params_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_model_params_id_seq OWNED BY public.zone_model_params.id;


--
-- Name: zone_simulations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_simulations (
    id bigint NOT NULL,
    zone_id bigint NOT NULL,
    scenario jsonb NOT NULL,
    results jsonb,
    duration_hours integer NOT NULL,
    step_minutes integer DEFAULT 10 NOT NULL,
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    error_message text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: zone_simulations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zone_simulations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zone_simulations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zone_simulations_id_seq OWNED BY public.zone_simulations.id;


--
-- Name: zone_workflow_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zone_workflow_state (
    zone_id bigint NOT NULL,
    workflow_phase character varying(50) DEFAULT 'idle'::character varying NOT NULL,
    started_at timestamp(0) with time zone,
    updated_at timestamp(0) with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    scheduler_task_id character varying(100),
    version bigint DEFAULT '0'::bigint NOT NULL
);


--
-- Name: zones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.zones (
    id bigint NOT NULL,
    greenhouse_id bigint,
    name character varying(255) NOT NULL,
    description text,
    status character varying(255) DEFAULT 'offline'::character varying NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    preset_id bigint,
    hardware_profile jsonb,
    capabilities jsonb DEFAULT '{"ec_control": false, "ph_control": false, "flow_sensor": false, "light_control": false, "recirculation": false, "climate_control": false, "irrigation_control": false}'::jsonb,
    health_score numeric(5,2),
    health_status character varying(16),
    uid character varying(64) NOT NULL,
    settings jsonb,
    water_state character varying(255) DEFAULT 'NORMAL_RECIRC'::character varying NOT NULL,
    solution_started_at timestamp(0) without time zone,
    automation_runtime character varying(16) DEFAULT 'ae3'::character varying NOT NULL,
    control_mode character varying(16) DEFAULT 'auto'::character varying NOT NULL,
    config_mode character varying(16) DEFAULT 'locked'::character varying NOT NULL,
    config_mode_changed_at timestamp(0) without time zone,
    config_mode_changed_by bigint,
    live_until timestamp(0) without time zone,
    live_started_at timestamp(0) without time zone,
    config_revision bigint DEFAULT '1'::bigint NOT NULL,
    CONSTRAINT zones_automation_runtime_check CHECK (((automation_runtime)::text = 'ae3'::text)),
    CONSTRAINT zones_config_mode_check CHECK (((config_mode)::text = ANY ((ARRAY['locked'::character varying, 'live'::character varying])::text[]))),
    CONSTRAINT zones_control_mode_check CHECK (((control_mode)::text = ANY ((ARRAY['auto'::character varying, 'semi'::character varying, 'manual'::character varying])::text[]))),
    CONSTRAINT zones_live_requires_until CHECK ((((config_mode)::text = 'locked'::text) OR (live_until IS NOT NULL)))
);


--
-- Name: zones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.zones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.zones_id_seq OWNED BY public.zones.id;


--
-- Name: commands_partitioned_2026_03; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_03 FOR VALUES FROM ('2026-03-01 00:00:00') TO ('2026-04-01 00:00:00');


--
-- Name: commands_partitioned_2026_04; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_04 FOR VALUES FROM ('2026-04-01 00:00:00') TO ('2026-05-01 00:00:00');


--
-- Name: commands_partitioned_2026_05; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_05 FOR VALUES FROM ('2026-05-01 00:00:00') TO ('2026-06-01 00:00:00');


--
-- Name: commands_partitioned_2026_06; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_06 FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');


--
-- Name: commands_partitioned_2026_07; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_07 FOR VALUES FROM ('2026-07-01 00:00:00') TO ('2026-08-01 00:00:00');


--
-- Name: commands_partitioned_2026_08; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_08 FOR VALUES FROM ('2026-08-01 00:00:00') TO ('2026-09-01 00:00:00');


--
-- Name: commands_partitioned_2026_09; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_09 FOR VALUES FROM ('2026-09-01 00:00:00') TO ('2026-10-01 00:00:00');


--
-- Name: commands_partitioned_2026_10; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_10 FOR VALUES FROM ('2026-10-01 00:00:00') TO ('2026-11-01 00:00:00');


--
-- Name: commands_partitioned_2026_11; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_11 FOR VALUES FROM ('2026-11-01 00:00:00') TO ('2026-12-01 00:00:00');


--
-- Name: commands_partitioned_2026_12; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2026_12 FOR VALUES FROM ('2026-12-01 00:00:00') TO ('2027-01-01 00:00:00');


--
-- Name: commands_partitioned_2027_01; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2027_01 FOR VALUES FROM ('2027-01-01 00:00:00') TO ('2027-02-01 00:00:00');


--
-- Name: commands_partitioned_2027_02; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2027_02 FOR VALUES FROM ('2027-02-01 00:00:00') TO ('2027-03-01 00:00:00');


--
-- Name: commands_partitioned_2027_03; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2027_03 FOR VALUES FROM ('2027-03-01 00:00:00') TO ('2027-04-01 00:00:00');


--
-- Name: commands_partitioned_2027_04; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ATTACH PARTITION public.commands_partitioned_2027_04 FOR VALUES FROM ('2027-04-01 00:00:00') TO ('2027-05-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_03; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_03 FOR VALUES FROM ('2026-03-01 00:00:00') TO ('2026-04-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_04; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_04 FOR VALUES FROM ('2026-04-01 00:00:00') TO ('2026-05-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_05; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_05 FOR VALUES FROM ('2026-05-01 00:00:00') TO ('2026-06-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_06; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_06 FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_07; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_07 FOR VALUES FROM ('2026-07-01 00:00:00') TO ('2026-08-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_08; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_08 FOR VALUES FROM ('2026-08-01 00:00:00') TO ('2026-09-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_09; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_09 FOR VALUES FROM ('2026-09-01 00:00:00') TO ('2026-10-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_10; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_10 FOR VALUES FROM ('2026-10-01 00:00:00') TO ('2026-11-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_11; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_11 FOR VALUES FROM ('2026-11-01 00:00:00') TO ('2026-12-01 00:00:00');


--
-- Name: zone_events_partitioned_2026_12; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2026_12 FOR VALUES FROM ('2026-12-01 00:00:00') TO ('2027-01-01 00:00:00');


--
-- Name: zone_events_partitioned_2027_01; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2027_01 FOR VALUES FROM ('2027-01-01 00:00:00') TO ('2027-02-01 00:00:00');


--
-- Name: zone_events_partitioned_2027_02; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2027_02 FOR VALUES FROM ('2027-02-01 00:00:00') TO ('2027-03-01 00:00:00');


--
-- Name: zone_events_partitioned_2027_03; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2027_03 FOR VALUES FROM ('2027-03-01 00:00:00') TO ('2027-04-01 00:00:00');


--
-- Name: zone_events_partitioned_2027_04; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ATTACH PARTITION public.zone_events_partitioned_2027_04 FOR VALUES FROM ('2027-04-01 00:00:00') TO ('2027-05-01 00:00:00');


--
-- Name: ae_commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_commands ALTER COLUMN id SET DEFAULT nextval('public.ae_commands_id_seq'::regclass);


--
-- Name: ae_stage_transitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_stage_transitions ALTER COLUMN id SET DEFAULT nextval('public.ae_stage_transitions_id_seq'::regclass);


--
-- Name: ae_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_tasks ALTER COLUMN id SET DEFAULT nextval('public.ae_tasks_id_seq'::regclass);


--
-- Name: aggregator_state id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregator_state ALTER COLUMN id SET DEFAULT nextval('public.aggregator_state_id_seq'::regclass);


--
-- Name: ai_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_logs ALTER COLUMN id SET DEFAULT nextval('public.ai_logs_id_seq'::regclass);


--
-- Name: alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts ALTER COLUMN id SET DEFAULT nextval('public.alerts_id_seq'::regclass);


--
-- Name: automation_config_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_documents ALTER COLUMN id SET DEFAULT nextval('public.automation_config_documents_id_seq'::regclass);


--
-- Name: automation_config_preset_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_preset_versions ALTER COLUMN id SET DEFAULT nextval('public.automation_config_preset_versions_id_seq'::regclass);


--
-- Name: automation_config_presets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_presets ALTER COLUMN id SET DEFAULT nextval('public.automation_config_presets_id_seq'::regclass);


--
-- Name: automation_config_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_versions ALTER COLUMN id SET DEFAULT nextval('public.automation_config_versions_id_seq'::regclass);


--
-- Name: automation_config_violations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_violations ALTER COLUMN id SET DEFAULT nextval('public.automation_config_violations_id_seq'::regclass);


--
-- Name: automation_effective_bundles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_effective_bundles ALTER COLUMN id SET DEFAULT nextval('public.automation_effective_bundles_id_seq'::regclass);


--
-- Name: channel_bindings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings ALTER COLUMN id SET DEFAULT nextval('public.channel_bindings_id_seq'::regclass);


--
-- Name: command_acks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_acks ALTER COLUMN id SET DEFAULT nextval('public.command_acks_id_seq'::regclass);


--
-- Name: command_audit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_audit ALTER COLUMN id SET DEFAULT nextval('public.command_audit_id_seq'::regclass);


--
-- Name: command_tracking id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_tracking ALTER COLUMN id SET DEFAULT nextval('public.command_tracking_id_seq'::regclass);


--
-- Name: commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ALTER COLUMN id SET DEFAULT nextval('public.commands_id_seq'::regclass);


--
-- Name: failed_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs ALTER COLUMN id SET DEFAULT nextval('public.failed_jobs_id_seq'::regclass);


--
-- Name: firmware_files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.firmware_files ALTER COLUMN id SET DEFAULT nextval('public.firmware_files_id_seq'::regclass);


--
-- Name: greenhouse_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouse_types ALTER COLUMN id SET DEFAULT nextval('public.greenhouse_types_id_seq'::regclass);


--
-- Name: greenhouses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouses ALTER COLUMN id SET DEFAULT nextval('public.greenhouses_id_seq'::regclass);


--
-- Name: grow_cycle_phase_steps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phase_steps ALTER COLUMN id SET DEFAULT nextval('public.grow_cycle_phase_steps_id_seq'::regclass);


--
-- Name: grow_cycle_phases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases ALTER COLUMN id SET DEFAULT nextval('public.grow_cycle_phases_id_seq'::regclass);


--
-- Name: grow_cycle_transitions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions ALTER COLUMN id SET DEFAULT nextval('public.grow_cycle_transitions_id_seq'::regclass);


--
-- Name: grow_cycles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles ALTER COLUMN id SET DEFAULT nextval('public.grow_cycles_id_seq'::regclass);


--
-- Name: grow_stage_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_stage_templates ALTER COLUMN id SET DEFAULT nextval('public.grow_stage_templates_id_seq'::regclass);


--
-- Name: harvests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.harvests ALTER COLUMN id SET DEFAULT nextval('public.harvests_id_seq'::regclass);


--
-- Name: infrastructure_instances id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.infrastructure_instances ALTER COLUMN id SET DEFAULT nextval('public.infrastructure_instances_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: laravel_scheduler_active_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_active_tasks ALTER COLUMN id SET DEFAULT nextval('public.laravel_scheduler_active_tasks_id_seq'::regclass);


--
-- Name: laravel_scheduler_cycle_duration_aggregates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_aggregates ALTER COLUMN id SET DEFAULT nextval('public.laravel_scheduler_cycle_duration_aggregates_id_seq'::regclass);


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_bucket_counts ALTER COLUMN id SET DEFAULT nextval('public.laravel_scheduler_cycle_duration_bucket_counts_id_seq'::regclass);


--
-- Name: laravel_scheduler_dispatch_metric_totals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_dispatch_metric_totals ALTER COLUMN id SET DEFAULT nextval('public.laravel_scheduler_dispatch_metric_totals_id_seq'::regclass);


--
-- Name: migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations ALTER COLUMN id SET DEFAULT nextval('public.migrations_id_seq'::regclass);


--
-- Name: node_channels id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_channels ALTER COLUMN id SET DEFAULT nextval('public.node_channels_id_seq'::regclass);


--
-- Name: node_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_logs ALTER COLUMN id SET DEFAULT nextval('public.node_logs_id_seq'::regclass);


--
-- Name: nodes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes ALTER COLUMN id SET DEFAULT nextval('public.nodes_id_seq'::regclass);


--
-- Name: nutrient_products id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nutrient_products ALTER COLUMN id SET DEFAULT nextval('public.nutrient_products_id_seq'::regclass);


--
-- Name: parameter_predictions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parameter_predictions ALTER COLUMN id SET DEFAULT nextval('public.parameter_predictions_id_seq'::regclass);


--
-- Name: pending_alerts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_alerts ALTER COLUMN id SET DEFAULT nextval('public.pending_alerts_id_seq'::regclass);


--
-- Name: pending_alerts_dlq id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_alerts_dlq ALTER COLUMN id SET DEFAULT nextval('public.pending_alerts_dlq_id_seq'::regclass);


--
-- Name: pending_status_updates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_status_updates ALTER COLUMN id SET DEFAULT nextval('public.pending_status_updates_id_seq'::regclass);


--
-- Name: pending_status_updates_dlq id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_status_updates_dlq ALTER COLUMN id SET DEFAULT nextval('public.pending_status_updates_dlq_id_seq'::regclass);


--
-- Name: personal_access_tokens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_access_tokens ALTER COLUMN id SET DEFAULT nextval('public.personal_access_tokens_id_seq'::regclass);


--
-- Name: plant_cost_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_cost_items ALTER COLUMN id SET DEFAULT nextval('public.plant_cost_items_id_seq'::regclass);


--
-- Name: plant_price_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_price_versions ALTER COLUMN id SET DEFAULT nextval('public.plant_price_versions_id_seq'::regclass);


--
-- Name: plant_recipe id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_recipe ALTER COLUMN id SET DEFAULT nextval('public.plant_recipe_id_seq'::regclass);


--
-- Name: plant_sale_prices id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_sale_prices ALTER COLUMN id SET DEFAULT nextval('public.plant_sale_prices_id_seq'::regclass);


--
-- Name: plant_zone id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_zone ALTER COLUMN id SET DEFAULT nextval('public.plant_zone_id_seq'::regclass);


--
-- Name: plants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants ALTER COLUMN id SET DEFAULT nextval('public.plants_id_seq'::regclass);


--
-- Name: presets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presets ALTER COLUMN id SET DEFAULT nextval('public.presets_id_seq'::regclass);


--
-- Name: pump_calibrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pump_calibrations ALTER COLUMN id SET DEFAULT nextval('public.pump_calibrations_id_seq'::regclass);


--
-- Name: recipe_analytics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_analytics ALTER COLUMN id SET DEFAULT nextval('public.recipe_analytics_id_seq'::regclass);


--
-- Name: recipe_revision_phase_steps id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phase_steps ALTER COLUMN id SET DEFAULT nextval('public.recipe_revision_phase_steps_id_seq'::regclass);


--
-- Name: recipe_revision_phases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases ALTER COLUMN id SET DEFAULT nextval('public.recipe_revision_phases_id_seq'::regclass);


--
-- Name: recipe_revisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revisions ALTER COLUMN id SET DEFAULT nextval('public.recipe_revisions_id_seq'::regclass);


--
-- Name: recipes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes ALTER COLUMN id SET DEFAULT nextval('public.recipes_id_seq'::regclass);


--
-- Name: scheduler_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_logs ALTER COLUMN id SET DEFAULT nextval('public.scheduler_logs_id_seq'::regclass);


--
-- Name: sensor_calibrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations ALTER COLUMN id SET DEFAULT nextval('public.sensor_calibrations_id_seq'::regclass);


--
-- Name: sensors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors ALTER COLUMN id SET DEFAULT nextval('public.sensors_id_seq'::regclass);


--
-- Name: simulation_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_events ALTER COLUMN id SET DEFAULT nextval('public.simulation_events_id_seq'::regclass);


--
-- Name: simulation_reports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_reports ALTER COLUMN id SET DEFAULT nextval('public.simulation_reports_id_seq'::regclass);


--
-- Name: substrates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.substrates ALTER COLUMN id SET DEFAULT nextval('public.substrates_id_seq'::regclass);


--
-- Name: system_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_logs ALTER COLUMN id SET DEFAULT nextval('public.system_logs_id_seq'::regclass);


--
-- Name: telemetry_agg_1h id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1h ALTER COLUMN id SET DEFAULT nextval('public.telemetry_agg_1h_id_seq'::regclass);


--
-- Name: telemetry_agg_1m id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1m ALTER COLUMN id SET DEFAULT nextval('public.telemetry_agg_1m_id_seq'::regclass);


--
-- Name: telemetry_daily id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_daily ALTER COLUMN id SET DEFAULT nextval('public.telemetry_daily_id_seq'::regclass);


--
-- Name: telemetry_samples id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_samples ALTER COLUMN id SET DEFAULT nextval('public.telemetry_samples_id_seq'::regclass);


--
-- Name: unassigned_node_errors id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors ALTER COLUMN id SET DEFAULT nextval('public.unassigned_node_errors_id_seq'::regclass);


--
-- Name: unassigned_node_errors_archive id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors_archive ALTER COLUMN id SET DEFAULT nextval('public.unassigned_node_errors_archive_id_seq'::regclass);


--
-- Name: user_greenhouses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_greenhouses ALTER COLUMN id SET DEFAULT nextval('public.user_greenhouses_id_seq'::regclass);


--
-- Name: user_zones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zones ALTER COLUMN id SET DEFAULT nextval('public.user_zones_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: zone_automation_intents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_intents ALTER COLUMN id SET DEFAULT nextval('public.zone_automation_intents_id_seq'::regclass);


--
-- Name: zone_automation_presets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets ALTER COLUMN id SET DEFAULT nextval('public.zone_automation_presets_id_seq'::regclass);


--
-- Name: zone_config_changes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_config_changes ALTER COLUMN id SET DEFAULT nextval('public.zone_config_changes_id_seq'::regclass);


--
-- Name: zone_correction_presets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_correction_presets ALTER COLUMN id SET DEFAULT nextval('public.zone_correction_presets_id_seq'::regclass);


--
-- Name: zone_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events ALTER COLUMN id SET DEFAULT nextval('public.zone_events_id_seq'::regclass);


--
-- Name: zone_model_params id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_model_params ALTER COLUMN id SET DEFAULT nextval('public.zone_model_params_id_seq'::regclass);


--
-- Name: zone_simulations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_simulations ALTER COLUMN id SET DEFAULT nextval('public.zone_simulations_id_seq'::regclass);


--
-- Name: zones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones ALTER COLUMN id SET DEFAULT nextval('public.zones_id_seq'::regclass);


--
-- Name: ae_commands ae_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_commands
    ADD CONSTRAINT ae_commands_pkey PRIMARY KEY (id);


--
-- Name: ae_commands ae_commands_task_step_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_commands
    ADD CONSTRAINT ae_commands_task_step_unique UNIQUE (task_id, step_no);


--
-- Name: ae_stage_transitions ae_stage_transitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_stage_transitions
    ADD CONSTRAINT ae_stage_transitions_pkey PRIMARY KEY (id);


--
-- Name: ae_tasks ae_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_tasks
    ADD CONSTRAINT ae_tasks_pkey PRIMARY KEY (id);


--
-- Name: ae_zone_leases ae_zone_leases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_zone_leases
    ADD CONSTRAINT ae_zone_leases_pkey PRIMARY KEY (zone_id);


--
-- Name: aggregator_state aggregator_state_aggregation_type_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregator_state
    ADD CONSTRAINT aggregator_state_aggregation_type_unique UNIQUE (aggregation_type);


--
-- Name: aggregator_state aggregator_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.aggregator_state
    ADD CONSTRAINT aggregator_state_pkey PRIMARY KEY (id);


--
-- Name: ai_logs ai_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_logs
    ADD CONSTRAINT ai_logs_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: automation_config_documents automation_config_documents_ns_scope_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_documents
    ADD CONSTRAINT automation_config_documents_ns_scope_unique UNIQUE (namespace, scope_type, scope_id);


--
-- Name: automation_config_documents automation_config_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_documents
    ADD CONSTRAINT automation_config_documents_pkey PRIMARY KEY (id);


--
-- Name: automation_config_preset_versions automation_config_preset_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_preset_versions
    ADD CONSTRAINT automation_config_preset_versions_pkey PRIMARY KEY (id);


--
-- Name: automation_config_presets automation_config_presets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_presets
    ADD CONSTRAINT automation_config_presets_pkey PRIMARY KEY (id);


--
-- Name: automation_config_presets automation_config_presets_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_presets
    ADD CONSTRAINT automation_config_presets_slug_unique UNIQUE (slug);


--
-- Name: automation_config_versions automation_config_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_versions
    ADD CONSTRAINT automation_config_versions_pkey PRIMARY KEY (id);


--
-- Name: automation_config_violations automation_config_violations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_violations
    ADD CONSTRAINT automation_config_violations_pkey PRIMARY KEY (id);


--
-- Name: automation_effective_bundles automation_effective_bundles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_effective_bundles
    ADD CONSTRAINT automation_effective_bundles_pkey PRIMARY KEY (id);


--
-- Name: automation_effective_bundles automation_effective_bundles_scope_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_effective_bundles
    ADD CONSTRAINT automation_effective_bundles_scope_unique UNIQUE (scope_type, scope_id);


--
-- Name: cache_locks cache_locks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache_locks
    ADD CONSTRAINT cache_locks_pkey PRIMARY KEY (key);


--
-- Name: cache cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache
    ADD CONSTRAINT cache_pkey PRIMARY KEY (key);


--
-- Name: channel_bindings channel_bindings_node_channel_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings
    ADD CONSTRAINT channel_bindings_node_channel_unique UNIQUE (node_channel_id);


--
-- Name: channel_bindings channel_bindings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings
    ADD CONSTRAINT channel_bindings_pkey PRIMARY KEY (id);


--
-- Name: channel_bindings channel_bindings_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings
    ADD CONSTRAINT channel_bindings_unique UNIQUE (infrastructure_instance_id, node_channel_id);


--
-- Name: command_acks command_acks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_acks
    ADD CONSTRAINT command_acks_pkey PRIMARY KEY (id);


--
-- Name: command_audit command_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_audit
    ADD CONSTRAINT command_audit_pkey PRIMARY KEY (id);


--
-- Name: command_tracking command_tracking_cmd_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_tracking
    ADD CONSTRAINT command_tracking_cmd_id_unique UNIQUE (cmd_id);


--
-- Name: command_tracking command_tracking_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_tracking
    ADD CONSTRAINT command_tracking_pkey PRIMARY KEY (id);


--
-- Name: commands commands_partitioned_cmd_id_created_at_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands
    ADD CONSTRAINT commands_partitioned_cmd_id_created_at_unique UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_03 commands_partitioned_2026_03_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_03
    ADD CONSTRAINT commands_partitioned_2026_03_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_04 commands_partitioned_2026_04_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_04
    ADD CONSTRAINT commands_partitioned_2026_04_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_05 commands_partitioned_2026_05_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_05
    ADD CONSTRAINT commands_partitioned_2026_05_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_06 commands_partitioned_2026_06_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_06
    ADD CONSTRAINT commands_partitioned_2026_06_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_07 commands_partitioned_2026_07_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_07
    ADD CONSTRAINT commands_partitioned_2026_07_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_08 commands_partitioned_2026_08_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_08
    ADD CONSTRAINT commands_partitioned_2026_08_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_09 commands_partitioned_2026_09_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_09
    ADD CONSTRAINT commands_partitioned_2026_09_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_10 commands_partitioned_2026_10_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_10
    ADD CONSTRAINT commands_partitioned_2026_10_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_11 commands_partitioned_2026_11_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_11
    ADD CONSTRAINT commands_partitioned_2026_11_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2026_12 commands_partitioned_2026_12_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2026_12
    ADD CONSTRAINT commands_partitioned_2026_12_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2027_01 commands_partitioned_2027_01_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2027_01
    ADD CONSTRAINT commands_partitioned_2027_01_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2027_02 commands_partitioned_2027_02_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2027_02
    ADD CONSTRAINT commands_partitioned_2027_02_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2027_03 commands_partitioned_2027_03_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2027_03
    ADD CONSTRAINT commands_partitioned_2027_03_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: commands_partitioned_2027_04 commands_partitioned_2027_04_cmd_id_created_at_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands_partitioned_2027_04
    ADD CONSTRAINT commands_partitioned_2027_04_cmd_id_created_at_key UNIQUE (cmd_id, created_at);


--
-- Name: failed_jobs failed_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_pkey PRIMARY KEY (id);


--
-- Name: failed_jobs failed_jobs_uuid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_uuid_unique UNIQUE (uuid);


--
-- Name: firmware_files firmware_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.firmware_files
    ADD CONSTRAINT firmware_files_pkey PRIMARY KEY (id);


--
-- Name: greenhouse_types greenhouse_types_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouse_types
    ADD CONSTRAINT greenhouse_types_code_unique UNIQUE (code);


--
-- Name: greenhouse_types greenhouse_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouse_types
    ADD CONSTRAINT greenhouse_types_pkey PRIMARY KEY (id);


--
-- Name: greenhouses greenhouses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouses
    ADD CONSTRAINT greenhouses_pkey PRIMARY KEY (id);


--
-- Name: greenhouses greenhouses_provisioning_token_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouses
    ADD CONSTRAINT greenhouses_provisioning_token_unique UNIQUE (provisioning_token);


--
-- Name: greenhouses greenhouses_uid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouses
    ADD CONSTRAINT greenhouses_uid_unique UNIQUE (uid);


--
-- Name: grow_cycle_phase_steps grow_cycle_phase_steps_phase_step_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phase_steps
    ADD CONSTRAINT grow_cycle_phase_steps_phase_step_unique UNIQUE (grow_cycle_phase_id, step_index);


--
-- Name: grow_cycle_phase_steps grow_cycle_phase_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phase_steps
    ADD CONSTRAINT grow_cycle_phase_steps_pkey PRIMARY KEY (id);


--
-- Name: grow_cycle_phases grow_cycle_phases_cycle_phase_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_cycle_phase_unique UNIQUE (grow_cycle_id, phase_index);


--
-- Name: grow_cycle_phases grow_cycle_phases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_pkey PRIMARY KEY (id);


--
-- Name: grow_cycle_transitions grow_cycle_transitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_pkey PRIMARY KEY (id);


--
-- Name: grow_cycles grow_cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_pkey PRIMARY KEY (id);


--
-- Name: grow_stage_templates grow_stage_templates_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_stage_templates
    ADD CONSTRAINT grow_stage_templates_code_unique UNIQUE (code);


--
-- Name: grow_stage_templates grow_stage_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_stage_templates
    ADD CONSTRAINT grow_stage_templates_pkey PRIMARY KEY (id);


--
-- Name: harvests harvests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.harvests
    ADD CONSTRAINT harvests_pkey PRIMARY KEY (id);


--
-- Name: infrastructure_instances infrastructure_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.infrastructure_instances
    ADD CONSTRAINT infrastructure_instances_pkey PRIMARY KEY (id);


--
-- Name: job_batches job_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_batches
    ADD CONSTRAINT job_batches_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: laravel_scheduler_active_tasks laravel_scheduler_active_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_active_tasks
    ADD CONSTRAINT laravel_scheduler_active_tasks_pkey PRIMARY KEY (id);


--
-- Name: laravel_scheduler_active_tasks laravel_scheduler_active_tasks_task_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_active_tasks
    ADD CONSTRAINT laravel_scheduler_active_tasks_task_id_unique UNIQUE (task_id);


--
-- Name: laravel_scheduler_cycle_duration_aggregates laravel_scheduler_cycle_duration_aggregates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_aggregates
    ADD CONSTRAINT laravel_scheduler_cycle_duration_aggregates_pkey PRIMARY KEY (id);


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts laravel_scheduler_cycle_duration_bucket_counts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_bucket_counts
    ADD CONSTRAINT laravel_scheduler_cycle_duration_bucket_counts_pkey PRIMARY KEY (id);


--
-- Name: laravel_scheduler_dispatch_metric_totals laravel_scheduler_dispatch_metric_totals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_dispatch_metric_totals
    ADD CONSTRAINT laravel_scheduler_dispatch_metric_totals_pkey PRIMARY KEY (id);


--
-- Name: laravel_scheduler_zone_cursors laravel_scheduler_zone_cursors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_zone_cursors
    ADD CONSTRAINT laravel_scheduler_zone_cursors_pkey PRIMARY KEY (zone_id);


--
-- Name: laravel_scheduler_cycle_duration_aggregates ls_cycle_duration_agg_mode_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_aggregates
    ADD CONSTRAINT ls_cycle_duration_agg_mode_unique UNIQUE (dispatch_mode);


--
-- Name: laravel_scheduler_cycle_duration_bucket_counts ls_cycle_duration_bucket_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_cycle_duration_bucket_counts
    ADD CONSTRAINT ls_cycle_duration_bucket_unique UNIQUE (dispatch_mode, bucket_le);


--
-- Name: laravel_scheduler_dispatch_metric_totals ls_dispatch_metric_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_dispatch_metric_totals
    ADD CONSTRAINT ls_dispatch_metric_unique UNIQUE (zone_id, task_type, result);


--
-- Name: migrations migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (id);


--
-- Name: node_channels node_channels_node_id_channel_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_channels
    ADD CONSTRAINT node_channels_node_id_channel_unique UNIQUE (node_id, channel);


--
-- Name: node_channels node_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_channels
    ADD CONSTRAINT node_channels_pkey PRIMARY KEY (id);


--
-- Name: node_logs node_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_logs
    ADD CONSTRAINT node_logs_pkey PRIMARY KEY (id);


--
-- Name: nodes nodes_hardware_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_hardware_id_unique UNIQUE (hardware_id);


--
-- Name: nodes nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_pkey PRIMARY KEY (id);


--
-- Name: nodes nodes_uid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_uid_unique UNIQUE (uid);


--
-- Name: nutrient_products nutrient_products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nutrient_products
    ADD CONSTRAINT nutrient_products_pkey PRIMARY KEY (id);


--
-- Name: nutrient_products nutrient_products_unique_name_idx; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nutrient_products
    ADD CONSTRAINT nutrient_products_unique_name_idx UNIQUE (manufacturer, name, component);


--
-- Name: parameter_predictions parameter_predictions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parameter_predictions
    ADD CONSTRAINT parameter_predictions_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (email);


--
-- Name: pending_alerts_dlq pending_alerts_dlq_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_alerts_dlq
    ADD CONSTRAINT pending_alerts_dlq_pkey PRIMARY KEY (id);


--
-- Name: pending_alerts pending_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_alerts
    ADD CONSTRAINT pending_alerts_pkey PRIMARY KEY (id);


--
-- Name: pending_status_updates pending_status_updates_cmd_status_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_status_updates
    ADD CONSTRAINT pending_status_updates_cmd_status_unique UNIQUE (cmd_id, status);


--
-- Name: pending_status_updates_dlq pending_status_updates_dlq_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_status_updates_dlq
    ADD CONSTRAINT pending_status_updates_dlq_pkey PRIMARY KEY (id);


--
-- Name: pending_status_updates pending_status_updates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_status_updates
    ADD CONSTRAINT pending_status_updates_pkey PRIMARY KEY (id);


--
-- Name: personal_access_tokens personal_access_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_access_tokens
    ADD CONSTRAINT personal_access_tokens_pkey PRIMARY KEY (id);


--
-- Name: personal_access_tokens personal_access_tokens_token_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.personal_access_tokens
    ADD CONSTRAINT personal_access_tokens_token_unique UNIQUE (token);


--
-- Name: pid_state pid_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pid_state
    ADD CONSTRAINT pid_state_pkey PRIMARY KEY (zone_id, pid_type);


--
-- Name: plant_cost_items plant_cost_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_cost_items
    ADD CONSTRAINT plant_cost_items_pkey PRIMARY KEY (id);


--
-- Name: plant_price_versions plant_price_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_price_versions
    ADD CONSTRAINT plant_price_versions_pkey PRIMARY KEY (id);


--
-- Name: plant_recipe plant_recipe_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_recipe
    ADD CONSTRAINT plant_recipe_pkey PRIMARY KEY (id);


--
-- Name: plant_recipe plant_recipe_plant_id_recipe_id_season_site_type_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_recipe
    ADD CONSTRAINT plant_recipe_plant_id_recipe_id_season_site_type_unique UNIQUE (plant_id, recipe_id, season, site_type);


--
-- Name: plant_sale_prices plant_sale_prices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_sale_prices
    ADD CONSTRAINT plant_sale_prices_pkey PRIMARY KEY (id);


--
-- Name: plant_zone plant_zone_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_zone
    ADD CONSTRAINT plant_zone_pkey PRIMARY KEY (id);


--
-- Name: plant_zone plant_zone_plant_id_zone_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_zone
    ADD CONSTRAINT plant_zone_plant_id_zone_id_unique UNIQUE (plant_id, zone_id);


--
-- Name: plants plants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_pkey PRIMARY KEY (id);


--
-- Name: plants plants_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plants
    ADD CONSTRAINT plants_slug_unique UNIQUE (slug);


--
-- Name: presets presets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_pkey PRIMARY KEY (id);


--
-- Name: pump_calibrations pump_calibrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pump_calibrations
    ADD CONSTRAINT pump_calibrations_pkey PRIMARY KEY (id);


--
-- Name: recipe_analytics recipe_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_analytics
    ADD CONSTRAINT recipe_analytics_pkey PRIMARY KEY (id);


--
-- Name: recipe_revision_phase_steps recipe_revision_phase_steps_phase_step_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phase_steps
    ADD CONSTRAINT recipe_revision_phase_steps_phase_step_unique UNIQUE (phase_id, step_index);


--
-- Name: recipe_revision_phase_steps recipe_revision_phase_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phase_steps
    ADD CONSTRAINT recipe_revision_phase_steps_pkey PRIMARY KEY (id);


--
-- Name: recipe_revision_phases recipe_revision_phases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_pkey PRIMARY KEY (id);


--
-- Name: recipe_revision_phases recipe_revision_phases_revision_phase_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_revision_phase_unique UNIQUE (recipe_revision_id, phase_index);


--
-- Name: recipe_revisions recipe_revisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revisions
    ADD CONSTRAINT recipe_revisions_pkey PRIMARY KEY (id);


--
-- Name: recipe_revisions recipe_revisions_recipe_revision_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revisions
    ADD CONSTRAINT recipe_revisions_recipe_revision_unique UNIQUE (recipe_id, revision_number);


--
-- Name: recipes recipes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipes
    ADD CONSTRAINT recipes_pkey PRIMARY KEY (id);


--
-- Name: scheduler_logs scheduler_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scheduler_logs
    ADD CONSTRAINT scheduler_logs_pkey PRIMARY KEY (id);


--
-- Name: sensor_calibrations sensor_calibrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT sensor_calibrations_pkey PRIMARY KEY (id);


--
-- Name: sensors sensors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: simulation_events simulation_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_events
    ADD CONSTRAINT simulation_events_pkey PRIMARY KEY (id);


--
-- Name: simulation_reports simulation_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_reports
    ADD CONSTRAINT simulation_reports_pkey PRIMARY KEY (id);


--
-- Name: simulation_reports simulation_reports_simulation_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_reports
    ADD CONSTRAINT simulation_reports_simulation_id_unique UNIQUE (simulation_id);


--
-- Name: substrates substrates_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.substrates
    ADD CONSTRAINT substrates_code_unique UNIQUE (code);


--
-- Name: substrates substrates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.substrates
    ADD CONSTRAINT substrates_pkey PRIMARY KEY (id);


--
-- Name: system_logs system_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_logs
    ADD CONSTRAINT system_logs_pkey PRIMARY KEY (id);


--
-- Name: telemetry_agg_1h telemetry_agg_1h_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1h
    ADD CONSTRAINT telemetry_agg_1h_pkey PRIMARY KEY (id);


--
-- Name: telemetry_agg_1h telemetry_agg_1h_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1h
    ADD CONSTRAINT telemetry_agg_1h_unique UNIQUE (zone_id, node_id, channel, metric_type, ts);


--
-- Name: telemetry_agg_1m telemetry_agg_1m_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1m
    ADD CONSTRAINT telemetry_agg_1m_pkey PRIMARY KEY (id);


--
-- Name: telemetry_agg_1m telemetry_agg_1m_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1m
    ADD CONSTRAINT telemetry_agg_1m_unique UNIQUE (zone_id, node_id, channel, metric_type, ts);


--
-- Name: telemetry_daily telemetry_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_daily
    ADD CONSTRAINT telemetry_daily_pkey PRIMARY KEY (id);


--
-- Name: telemetry_daily telemetry_daily_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_daily
    ADD CONSTRAINT telemetry_daily_unique UNIQUE (zone_id, node_id, channel, metric_type, date);


--
-- Name: telemetry_last telemetry_last_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_last
    ADD CONSTRAINT telemetry_last_pkey PRIMARY KEY (sensor_id);


--
-- Name: telemetry_samples telemetry_samples_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_samples
    ADD CONSTRAINT telemetry_samples_pkey PRIMARY KEY (id);


--
-- Name: unassigned_node_errors_archive unassigned_node_errors_archive_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors_archive
    ADD CONSTRAINT unassigned_node_errors_archive_pkey PRIMARY KEY (id);


--
-- Name: unassigned_node_errors unassigned_node_errors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors
    ADD CONSTRAINT unassigned_node_errors_pkey PRIMARY KEY (id);


--
-- Name: sensor_calibrations uniq_sensor_cal_point1_cmd; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT uniq_sensor_cal_point1_cmd UNIQUE (node_channel_id, point_1_command_id);


--
-- Name: sensor_calibrations uniq_sensor_cal_point2_cmd; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT uniq_sensor_cal_point2_cmd UNIQUE (node_channel_id, point_2_command_id);


--
-- Name: user_greenhouses user_greenhouses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_greenhouses
    ADD CONSTRAINT user_greenhouses_pkey PRIMARY KEY (id);


--
-- Name: user_greenhouses user_greenhouses_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_greenhouses
    ADD CONSTRAINT user_greenhouses_unique UNIQUE (user_id, greenhouse_id);


--
-- Name: user_zones user_zones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zones
    ADD CONSTRAINT user_zones_pkey PRIMARY KEY (id);


--
-- Name: user_zones user_zones_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zones
    ADD CONSTRAINT user_zones_unique UNIQUE (user_id, zone_id);


--
-- Name: users users_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_unique UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: zone_automation_intents zone_automation_intents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_intents
    ADD CONSTRAINT zone_automation_intents_pkey PRIMARY KEY (id);


--
-- Name: zone_automation_presets zone_automation_presets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets
    ADD CONSTRAINT zone_automation_presets_pkey PRIMARY KEY (id);


--
-- Name: zone_automation_presets zone_automation_presets_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets
    ADD CONSTRAINT zone_automation_presets_slug_unique UNIQUE (slug);


--
-- Name: zone_automation_state zone_automation_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_state
    ADD CONSTRAINT zone_automation_state_pkey PRIMARY KEY (zone_id);


--
-- Name: zone_config_changes zone_config_changes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_config_changes
    ADD CONSTRAINT zone_config_changes_pkey PRIMARY KEY (id);


--
-- Name: zone_config_changes zone_config_changes_zone_id_revision_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_config_changes
    ADD CONSTRAINT zone_config_changes_zone_id_revision_unique UNIQUE (zone_id, revision);


--
-- Name: zone_correction_presets zone_correction_presets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_correction_presets
    ADD CONSTRAINT zone_correction_presets_pkey PRIMARY KEY (id);


--
-- Name: zone_correction_presets zone_correction_presets_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_correction_presets
    ADD CONSTRAINT zone_correction_presets_slug_unique UNIQUE (slug);


--
-- Name: zone_events zone_events_partitioned_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events
    ADD CONSTRAINT zone_events_partitioned_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_03 zone_events_partitioned_2026_03_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_03
    ADD CONSTRAINT zone_events_partitioned_2026_03_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_04 zone_events_partitioned_2026_04_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_04
    ADD CONSTRAINT zone_events_partitioned_2026_04_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_05 zone_events_partitioned_2026_05_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_05
    ADD CONSTRAINT zone_events_partitioned_2026_05_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_06 zone_events_partitioned_2026_06_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_06
    ADD CONSTRAINT zone_events_partitioned_2026_06_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_07 zone_events_partitioned_2026_07_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_07
    ADD CONSTRAINT zone_events_partitioned_2026_07_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_08 zone_events_partitioned_2026_08_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_08
    ADD CONSTRAINT zone_events_partitioned_2026_08_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_09 zone_events_partitioned_2026_09_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_09
    ADD CONSTRAINT zone_events_partitioned_2026_09_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_10 zone_events_partitioned_2026_10_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_10
    ADD CONSTRAINT zone_events_partitioned_2026_10_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_11 zone_events_partitioned_2026_11_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_11
    ADD CONSTRAINT zone_events_partitioned_2026_11_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2026_12 zone_events_partitioned_2026_12_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2026_12
    ADD CONSTRAINT zone_events_partitioned_2026_12_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2027_01 zone_events_partitioned_2027_01_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2027_01
    ADD CONSTRAINT zone_events_partitioned_2027_01_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2027_02 zone_events_partitioned_2027_02_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2027_02
    ADD CONSTRAINT zone_events_partitioned_2027_02_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2027_03 zone_events_partitioned_2027_03_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2027_03
    ADD CONSTRAINT zone_events_partitioned_2027_03_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_events_partitioned_2027_04 zone_events_partitioned_2027_04_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_events_partitioned_2027_04
    ADD CONSTRAINT zone_events_partitioned_2027_04_pkey PRIMARY KEY (id, created_at);


--
-- Name: zone_model_params zone_model_params_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_model_params
    ADD CONSTRAINT zone_model_params_pkey PRIMARY KEY (id);


--
-- Name: zone_model_params zone_model_params_zone_id_model_type_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_model_params
    ADD CONSTRAINT zone_model_params_zone_id_model_type_unique UNIQUE (zone_id, model_type);


--
-- Name: zone_simulations zone_simulations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_simulations
    ADD CONSTRAINT zone_simulations_pkey PRIMARY KEY (id);


--
-- Name: zone_workflow_state zone_workflow_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_workflow_state
    ADD CONSTRAINT zone_workflow_state_pkey PRIMARY KEY (zone_id);


--
-- Name: zones zones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_pkey PRIMARY KEY (id);


--
-- Name: zones zones_uid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_uid_unique UNIQUE (uid);


--
-- Name: ae_commands_external_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_commands_external_id_idx ON public.ae_commands USING btree (external_id) WHERE (external_id IS NOT NULL);


--
-- Name: ae_commands_stage_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_commands_stage_idx ON public.ae_commands USING btree (task_id, stage_name) WHERE (stage_name IS NOT NULL);


--
-- Name: ae_stage_transitions_task_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_stage_transitions_task_idx ON public.ae_stage_transitions USING btree (task_id, triggered_at);


--
-- Name: ae_tasks_active_zone_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ae_tasks_active_zone_unique ON public.ae_tasks USING btree (zone_id) WHERE ((status)::text = ANY ((ARRAY['pending'::character varying, 'claimed'::character varying, 'running'::character varying, 'waiting_command'::character varying])::text[]));


--
-- Name: ae_tasks_deadline_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_tasks_deadline_idx ON public.ae_tasks USING btree (stage_deadline_at) WHERE ((stage_deadline_at IS NOT NULL) AND ((status)::text = ANY ((ARRAY['running'::character varying, 'waiting_command'::character varying])::text[])));


--
-- Name: ae_tasks_pending_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_tasks_pending_idx ON public.ae_tasks USING btree (due_at, created_at) WHERE ((status)::text = 'pending'::text);


--
-- Name: ae_tasks_topology_stage_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_tasks_topology_stage_idx ON public.ae_tasks USING btree (topology, current_stage) WHERE ((status)::text = ANY ((ARRAY['running'::character varying, 'waiting_command'::character varying])::text[]));


--
-- Name: ae_tasks_zone_idempotency_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ae_tasks_zone_idempotency_unique ON public.ae_tasks USING btree (zone_id, idempotency_key);


--
-- Name: ae_tasks_zone_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ae_tasks_zone_status_idx ON public.ae_tasks USING btree (zone_id, status);


--
-- Name: aggregator_state_aggregation_type_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX aggregator_state_aggregation_type_index ON public.aggregator_state USING btree (aggregation_type);


--
-- Name: ai_logs_action_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ai_logs_action_idx ON public.ai_logs USING btree (action);


--
-- Name: ai_logs_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ai_logs_created_at_idx ON public.ai_logs USING btree (created_at);


--
-- Name: ai_logs_zone_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ai_logs_zone_created_idx ON public.ai_logs USING btree (zone_id, created_at);


--
-- Name: alerts_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_category_idx ON public.alerts USING btree (category);


--
-- Name: alerts_hardware_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_hardware_id_idx ON public.alerts USING btree (hardware_id);


--
-- Name: alerts_node_uid_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_node_uid_idx ON public.alerts USING btree (node_uid);


--
-- Name: alerts_severity_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_severity_idx ON public.alerts USING btree (severity);


--
-- Name: alerts_source_code_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_source_code_status_idx ON public.alerts USING btree (source, code, status);


--
-- Name: alerts_zone_status_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_zone_status_category_idx ON public.alerts USING btree (zone_id, status, category);


--
-- Name: alerts_zone_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_zone_status_idx ON public.alerts USING btree (zone_id, status);


--
-- Name: alerts_zone_status_severity_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX alerts_zone_status_severity_idx ON public.alerts USING btree (zone_id, status, severity);


--
-- Name: automation_config_documents_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX automation_config_documents_scope_idx ON public.automation_config_documents USING btree (scope_type, scope_id);


--
-- Name: automation_config_presets_ns_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX automation_config_presets_ns_scope_idx ON public.automation_config_presets USING btree (namespace, scope);


--
-- Name: automation_config_versions_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX automation_config_versions_scope_idx ON public.automation_config_versions USING btree (namespace, scope_type, scope_id);


--
-- Name: automation_config_violations_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX automation_config_violations_scope_idx ON public.automation_config_violations USING btree (scope_type, scope_id);


--
-- Name: automation_effective_bundles_revision_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX automation_effective_bundles_revision_idx ON public.automation_effective_bundles USING btree (bundle_revision);


--
-- Name: channel_bindings_infrastructure_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX channel_bindings_infrastructure_idx ON public.channel_bindings USING btree (infrastructure_instance_id);


--
-- Name: command_acks_command_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX command_acks_command_idx ON public.command_acks USING btree (command_id);


--
-- Name: command_acks_command_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX command_acks_command_type_idx ON public.command_acks USING btree (command_id, ack_type);


--
-- Name: command_acks_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX command_acks_type_idx ON public.command_acks USING btree (ack_type);


--
-- Name: commands_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_cmd_id_idx ON ONLY public.commands USING btree (cmd_id);


--
-- Name: commands_partitioned_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_cmd_id_idx ON ONLY public.commands USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_03_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_03_cmd_id_idx ON public.commands_partitioned_2026_03 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_03_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_03_cmd_id_idx1 ON public.commands_partitioned_2026_03 USING btree (cmd_id);


--
-- Name: commands_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_status_idx ON ONLY public.commands USING btree (status);


--
-- Name: commands_partitioned_2026_03_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_03_status_idx ON public.commands_partitioned_2026_03 USING btree (status);


--
-- Name: commands_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_status_updated_at_idx ON ONLY public.commands USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_03_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_03_status_updated_at_idx ON public.commands_partitioned_2026_03 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_04_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_04_cmd_id_idx ON public.commands_partitioned_2026_04 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_04_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_04_cmd_id_idx1 ON public.commands_partitioned_2026_04 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_04_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_04_status_idx ON public.commands_partitioned_2026_04 USING btree (status);


--
-- Name: commands_partitioned_2026_04_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_04_status_updated_at_idx ON public.commands_partitioned_2026_04 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_05_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_05_cmd_id_idx ON public.commands_partitioned_2026_05 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_05_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_05_cmd_id_idx1 ON public.commands_partitioned_2026_05 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_05_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_05_status_idx ON public.commands_partitioned_2026_05 USING btree (status);


--
-- Name: commands_partitioned_2026_05_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_05_status_updated_at_idx ON public.commands_partitioned_2026_05 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_06_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_06_cmd_id_idx ON public.commands_partitioned_2026_06 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_06_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_06_cmd_id_idx1 ON public.commands_partitioned_2026_06 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_06_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_06_status_idx ON public.commands_partitioned_2026_06 USING btree (status);


--
-- Name: commands_partitioned_2026_06_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_06_status_updated_at_idx ON public.commands_partitioned_2026_06 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_07_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_07_cmd_id_idx ON public.commands_partitioned_2026_07 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_07_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_07_cmd_id_idx1 ON public.commands_partitioned_2026_07 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_07_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_07_status_idx ON public.commands_partitioned_2026_07 USING btree (status);


--
-- Name: commands_partitioned_2026_07_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_07_status_updated_at_idx ON public.commands_partitioned_2026_07 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_08_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_08_cmd_id_idx ON public.commands_partitioned_2026_08 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_08_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_08_cmd_id_idx1 ON public.commands_partitioned_2026_08 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_08_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_08_status_idx ON public.commands_partitioned_2026_08 USING btree (status);


--
-- Name: commands_partitioned_2026_08_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_08_status_updated_at_idx ON public.commands_partitioned_2026_08 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_09_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_09_cmd_id_idx ON public.commands_partitioned_2026_09 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_09_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_09_cmd_id_idx1 ON public.commands_partitioned_2026_09 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_09_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_09_status_idx ON public.commands_partitioned_2026_09 USING btree (status);


--
-- Name: commands_partitioned_2026_09_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_09_status_updated_at_idx ON public.commands_partitioned_2026_09 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_10_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_10_cmd_id_idx ON public.commands_partitioned_2026_10 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_10_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_10_cmd_id_idx1 ON public.commands_partitioned_2026_10 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_10_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_10_status_idx ON public.commands_partitioned_2026_10 USING btree (status);


--
-- Name: commands_partitioned_2026_10_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_10_status_updated_at_idx ON public.commands_partitioned_2026_10 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_11_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_11_cmd_id_idx ON public.commands_partitioned_2026_11 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_11_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_11_cmd_id_idx1 ON public.commands_partitioned_2026_11 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_11_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_11_status_idx ON public.commands_partitioned_2026_11 USING btree (status);


--
-- Name: commands_partitioned_2026_11_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_11_status_updated_at_idx ON public.commands_partitioned_2026_11 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2026_12_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_12_cmd_id_idx ON public.commands_partitioned_2026_12 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_12_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_12_cmd_id_idx1 ON public.commands_partitioned_2026_12 USING btree (cmd_id);


--
-- Name: commands_partitioned_2026_12_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_12_status_idx ON public.commands_partitioned_2026_12 USING btree (status);


--
-- Name: commands_partitioned_2026_12_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2026_12_status_updated_at_idx ON public.commands_partitioned_2026_12 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2027_01_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_01_cmd_id_idx ON public.commands_partitioned_2027_01 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_01_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_01_cmd_id_idx1 ON public.commands_partitioned_2027_01 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_01_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_01_status_idx ON public.commands_partitioned_2027_01 USING btree (status);


--
-- Name: commands_partitioned_2027_01_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_01_status_updated_at_idx ON public.commands_partitioned_2027_01 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2027_02_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_02_cmd_id_idx ON public.commands_partitioned_2027_02 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_02_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_02_cmd_id_idx1 ON public.commands_partitioned_2027_02 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_02_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_02_status_idx ON public.commands_partitioned_2027_02 USING btree (status);


--
-- Name: commands_partitioned_2027_02_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_02_status_updated_at_idx ON public.commands_partitioned_2027_02 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2027_03_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_03_cmd_id_idx ON public.commands_partitioned_2027_03 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_03_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_03_cmd_id_idx1 ON public.commands_partitioned_2027_03 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_03_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_03_status_idx ON public.commands_partitioned_2027_03 USING btree (status);


--
-- Name: commands_partitioned_2027_03_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_03_status_updated_at_idx ON public.commands_partitioned_2027_03 USING btree (status, updated_at DESC);


--
-- Name: commands_partitioned_2027_04_cmd_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_04_cmd_id_idx ON public.commands_partitioned_2027_04 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_04_cmd_id_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_04_cmd_id_idx1 ON public.commands_partitioned_2027_04 USING btree (cmd_id);


--
-- Name: commands_partitioned_2027_04_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_04_status_idx ON public.commands_partitioned_2027_04 USING btree (status);


--
-- Name: commands_partitioned_2027_04_status_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX commands_partitioned_2027_04_status_updated_at_idx ON public.commands_partitioned_2027_04 USING btree (status, updated_at DESC);


--
-- Name: firmware_files_checksum_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX firmware_files_checksum_idx ON public.firmware_files USING btree (checksum_sha256);


--
-- Name: firmware_files_node_type_version_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX firmware_files_node_type_version_idx ON public.firmware_files USING btree (node_type, version);


--
-- Name: grow_cycle_phase_steps_phase_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_phase_steps_phase_idx ON public.grow_cycle_phase_steps USING btree (grow_cycle_phase_id);


--
-- Name: grow_cycle_phase_steps_revision_step_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_phase_steps_revision_step_idx ON public.grow_cycle_phase_steps USING btree (recipe_revision_phase_step_id);


--
-- Name: grow_cycle_phases_cycle_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_phases_cycle_idx ON public.grow_cycle_phases USING btree (grow_cycle_id);


--
-- Name: grow_cycle_phases_nutrient_program_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_phases_nutrient_program_idx ON public.grow_cycle_phases USING btree (nutrient_program_code);


--
-- Name: grow_cycle_phases_revision_phase_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_phases_revision_phase_idx ON public.grow_cycle_phases USING btree (recipe_revision_phase_id);


--
-- Name: grow_cycle_transitions_cycle_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_transitions_cycle_created_idx ON public.grow_cycle_transitions USING btree (grow_cycle_id, created_at);


--
-- Name: grow_cycle_transitions_cycle_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_transitions_cycle_idx ON public.grow_cycle_transitions USING btree (grow_cycle_id);


--
-- Name: grow_cycle_transitions_trigger_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycle_transitions_trigger_type_idx ON public.grow_cycle_transitions USING btree (trigger_type);


--
-- Name: grow_cycles_current_phase_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_current_phase_idx ON public.grow_cycles USING btree (current_phase_id);


--
-- Name: grow_cycles_current_step_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_current_step_idx ON public.grow_cycles USING btree (current_step_id);


--
-- Name: grow_cycles_greenhouse_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_greenhouse_id_idx ON public.grow_cycles USING btree (greenhouse_id);


--
-- Name: grow_cycles_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_status_idx ON public.grow_cycles USING btree (status);


--
-- Name: grow_cycles_status_phase_started_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_status_phase_started_idx ON public.grow_cycles USING btree (status, phase_started_at);


--
-- Name: grow_cycles_zone_active_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX grow_cycles_zone_active_unique ON public.grow_cycles USING btree (zone_id) WHERE ((status)::text = ANY ((ARRAY['PLANNED'::character varying, 'RUNNING'::character varying, 'PAUSED'::character varying])::text[]));


--
-- Name: grow_cycles_zone_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_zone_id_idx ON public.grow_cycles USING btree (zone_id);


--
-- Name: grow_cycles_zone_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_cycles_zone_status_idx ON public.grow_cycles USING btree (zone_id, status);


--
-- Name: grow_stage_templates_code_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_stage_templates_code_idx ON public.grow_stage_templates USING btree (code);


--
-- Name: grow_stage_templates_order_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX grow_stage_templates_order_idx ON public.grow_stage_templates USING btree (order_index);


--
-- Name: harvests_recipe_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX harvests_recipe_id_index ON public.harvests USING btree (recipe_id);


--
-- Name: harvests_zone_id_harvest_date_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX harvests_zone_id_harvest_date_index ON public.harvests USING btree (zone_id, harvest_date);


--
-- Name: idx_alerts_dlq_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_dlq_code ON public.pending_alerts_dlq USING btree (code);


--
-- Name: idx_alerts_dlq_failed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_dlq_failed_at ON public.pending_alerts_dlq USING btree (failed_at);


--
-- Name: idx_alerts_dlq_zone_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_dlq_zone_id ON public.pending_alerts_dlq USING btree (zone_id);


--
-- Name: idx_command_audit_command_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_audit_command_type ON public.command_audit USING btree (command_type);


--
-- Name: idx_command_audit_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_audit_created_at ON public.command_audit USING btree (created_at);


--
-- Name: idx_command_audit_zone_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_audit_zone_id ON public.command_audit USING btree (zone_id);


--
-- Name: idx_command_tracking_cmd_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_tracking_cmd_id ON public.command_tracking USING btree (cmd_id);


--
-- Name: idx_command_tracking_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_tracking_sent_at ON public.command_tracking USING btree (sent_at);


--
-- Name: idx_command_tracking_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_tracking_status ON public.command_tracking USING btree (status);


--
-- Name: idx_command_tracking_zone_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_tracking_zone_id ON public.command_tracking USING btree (zone_id);


--
-- Name: idx_node_channels_last_seen_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_channels_last_seen_at ON public.node_channels USING btree (last_seen_at);


--
-- Name: idx_node_channels_node_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_channels_node_active ON public.node_channels USING btree (node_id, is_active);


--
-- Name: idx_pending_alerts_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_alerts_retry ON public.pending_alerts USING btree (next_retry_at) WHERE (next_retry_at IS NOT NULL);


--
-- Name: idx_pending_alerts_zone_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_alerts_zone_id ON public.pending_alerts USING btree (zone_id);


--
-- Name: idx_pending_status_cmd_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_status_cmd_id ON public.pending_status_updates USING btree (cmd_id);


--
-- Name: idx_pending_status_retry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_status_retry ON public.pending_status_updates USING btree (next_retry_at) WHERE (next_retry_at IS NOT NULL);


--
-- Name: idx_pid_state_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pid_state_updated_at ON public.pid_state USING btree (updated_at);


--
-- Name: idx_pid_state_zone_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pid_state_zone_id ON public.pid_state USING btree (zone_id);


--
-- Name: idx_pump_calibration_node_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pump_calibration_node_active ON public.pump_calibrations USING btree (node_channel_id, is_active);


--
-- Name: idx_pump_calibration_node_mode_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pump_calibration_node_mode_active ON public.pump_calibrations USING btree (node_channel_id, mode, is_active);


--
-- Name: idx_pump_calibration_node_valid_from; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pump_calibration_node_valid_from ON public.pump_calibrations USING btree (node_channel_id, valid_from);


--
-- Name: idx_sensor_cal_channel_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sensor_cal_channel_status_created ON public.sensor_calibrations USING btree (node_channel_id, status, created_at);


--
-- Name: idx_sensor_cal_zone_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sensor_cal_zone_type_created ON public.sensor_calibrations USING btree (zone_id, sensor_type, created_at);


--
-- Name: idx_status_dlq_cmd_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_status_dlq_cmd_id ON public.pending_status_updates_dlq USING btree (cmd_id);


--
-- Name: idx_status_dlq_failed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_status_dlq_failed_at ON public.pending_status_updates_dlq USING btree (failed_at);


--
-- Name: infrastructure_instances_owner_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX infrastructure_instances_owner_idx ON public.infrastructure_instances USING btree (owner_type, owner_id);


--
-- Name: infrastructure_instances_owner_required_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX infrastructure_instances_owner_required_idx ON public.infrastructure_instances USING btree (owner_type, owner_id, required);


--
-- Name: infrastructure_instances_owner_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX infrastructure_instances_owner_type_idx ON public.infrastructure_instances USING btree (owner_type, owner_id, asset_type);


--
-- Name: jobs_queue_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_queue_index ON public.jobs USING btree (queue);


--
-- Name: ls_cycle_duration_bucket_mode_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ls_cycle_duration_bucket_mode_idx ON public.laravel_scheduler_cycle_duration_bucket_counts USING btree (dispatch_mode);


--
-- Name: ls_dispatch_metric_task_result_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ls_dispatch_metric_task_result_idx ON public.laravel_scheduler_dispatch_metric_totals USING btree (task_type, result);


--
-- Name: lsat_corr_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lsat_corr_idx ON public.laravel_scheduler_active_tasks USING btree (correlation_id);


--
-- Name: lsat_expires_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lsat_expires_at_idx ON public.laravel_scheduler_active_tasks USING btree (expires_at);


--
-- Name: lsat_sched_key_updated_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lsat_sched_key_updated_idx ON public.laravel_scheduler_active_tasks USING btree (schedule_key, updated_at);


--
-- Name: lsat_terminal_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lsat_terminal_at_idx ON public.laravel_scheduler_active_tasks USING btree (terminal_at);


--
-- Name: lsat_zone_status_updated_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lsat_zone_status_updated_idx ON public.laravel_scheduler_active_tasks USING btree (zone_id, status, updated_at);


--
-- Name: lszc_cursor_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX lszc_cursor_at_idx ON public.laravel_scheduler_zone_cursors USING btree (cursor_at);


--
-- Name: node_logs_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX node_logs_created_at_idx ON public.node_logs USING btree (created_at);


--
-- Name: node_logs_level_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX node_logs_level_idx ON public.node_logs USING btree (level);


--
-- Name: node_logs_node_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX node_logs_node_created_idx ON public.node_logs USING btree (node_id, created_at);


--
-- Name: nodes_hardware_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_hardware_id_idx ON public.nodes USING btree (hardware_id);


--
-- Name: nodes_last_seen_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_last_seen_at_idx ON public.nodes USING btree (last_seen_at) WHERE (last_seen_at IS NOT NULL);


--
-- Name: nodes_lifecycle_state_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_lifecycle_state_idx ON public.nodes USING btree (lifecycle_state);


--
-- Name: nodes_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_status_idx ON public.nodes USING btree (status);


--
-- Name: nodes_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_type_idx ON public.nodes USING btree (type) WHERE (type IS NOT NULL);


--
-- Name: nodes_unassigned_status_lifecycle_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_unassigned_status_lifecycle_idx ON public.nodes USING btree (status, lifecycle_state) WHERE (zone_id IS NULL);


--
-- Name: nodes_zone_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_zone_id_idx ON public.nodes USING btree (zone_id) WHERE (zone_id IS NOT NULL);


--
-- Name: nodes_zone_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_zone_idx ON public.nodes USING btree (zone_id);


--
-- Name: nodes_zone_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_zone_status_idx ON public.nodes USING btree (zone_id, status) WHERE (zone_id IS NOT NULL);


--
-- Name: nodes_zone_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_zone_type_idx ON public.nodes USING btree (zone_id, type) WHERE ((zone_id IS NOT NULL) AND (type IS NOT NULL));


--
-- Name: nodes_zone_uid_hardware_status_lifecycle_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nodes_zone_uid_hardware_status_lifecycle_idx ON public.nodes USING btree (zone_id, uid, hardware_id, status, lifecycle_state) WHERE (zone_id IS NOT NULL);


--
-- Name: nutrient_products_component_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX nutrient_products_component_idx ON public.nutrient_products USING btree (component);


--
-- Name: parameter_predictions_zone_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parameter_predictions_zone_id_created_at_index ON public.parameter_predictions USING btree (zone_id, created_at);


--
-- Name: parameter_predictions_zone_id_metric_type_predicted_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX parameter_predictions_zone_id_metric_type_predicted_at_index ON public.parameter_predictions USING btree (zone_id, metric_type, predicted_at);


--
-- Name: pending_alerts_next_retry_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX pending_alerts_next_retry_at_idx ON public.pending_alerts USING btree (next_retry_at);


--
-- Name: pending_alerts_retry_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX pending_alerts_retry_idx ON public.pending_alerts USING btree (status, attempts, last_attempt_at);


--
-- Name: pending_alerts_status_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX pending_alerts_status_created_idx ON public.pending_alerts USING btree (status, created_at);


--
-- Name: personal_access_tokens_tokenable_type_tokenable_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX personal_access_tokens_tokenable_type_tokenable_id_index ON public.personal_access_tokens USING btree (tokenable_type, tokenable_id);


--
-- Name: plant_price_versions_plant_id_effective_from_effective_to_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX plant_price_versions_plant_id_effective_from_effective_to_index ON public.plant_price_versions USING btree (plant_id, effective_from, effective_to);


--
-- Name: plant_sale_prices_plant_id_channel_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX plant_sale_prices_plant_id_channel_index ON public.plant_sale_prices USING btree (plant_id, channel);


--
-- Name: plants_growing_system_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX plants_growing_system_index ON public.plants USING btree (growing_system);


--
-- Name: plants_substrate_type_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX plants_substrate_type_index ON public.plants USING btree (substrate_type);


--
-- Name: recipe_analytics_recipe_id_zone_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_analytics_recipe_id_zone_id_index ON public.recipe_analytics USING btree (recipe_id, zone_id);


--
-- Name: recipe_analytics_start_date_end_date_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_analytics_start_date_end_date_index ON public.recipe_analytics USING btree (start_date, end_date);


--
-- Name: recipe_revision_phase_steps_phase_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_revision_phase_steps_phase_idx ON public.recipe_revision_phase_steps USING btree (phase_id);


--
-- Name: recipe_revision_phases_nutrient_program_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_revision_phases_nutrient_program_idx ON public.recipe_revision_phases USING btree (nutrient_program_code);


--
-- Name: recipe_revision_phases_revision_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_revision_phases_revision_idx ON public.recipe_revision_phases USING btree (recipe_revision_id);


--
-- Name: recipe_revision_phases_stage_template_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_revision_phases_stage_template_idx ON public.recipe_revision_phases USING btree (stage_template_id);


--
-- Name: recipe_revisions_recipe_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX recipe_revisions_recipe_status_idx ON public.recipe_revisions USING btree (recipe_id, status);


--
-- Name: scheduler_logs_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_created_at_idx ON public.scheduler_logs USING btree (created_at);


--
-- Name: scheduler_logs_details_task_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_details_task_id_idx ON public.scheduler_logs USING btree (((details ->> 'task_id'::text))) WHERE ((details ->> 'task_id'::text) IS NOT NULL);


--
-- Name: scheduler_logs_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_status_idx ON public.scheduler_logs USING btree (status);


--
-- Name: scheduler_logs_task_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_task_created_idx ON public.scheduler_logs USING btree (task_name, created_at);


--
-- Name: scheduler_logs_task_zone_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_task_zone_created_idx ON public.scheduler_logs USING btree (task_name, ((details ->> 'zone_id'::text)), created_at DESC, id DESC);


--
-- Name: scheduler_logs_zone_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX scheduler_logs_zone_created_idx ON public.scheduler_logs USING btree (((details ->> 'zone_id'::text)), created_at DESC, id DESC) WHERE ((task_name)::text ~~ 'ae_scheduler_task_st-%'::text);


--
-- Name: sensors_active_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_active_idx ON public.sensors USING btree (is_active);


--
-- Name: sensors_greenhouse_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_greenhouse_scope_idx ON public.sensors USING btree (greenhouse_id, scope);


--
-- Name: sensors_greenhouse_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_greenhouse_type_idx ON public.sensors USING btree (greenhouse_id, type);


--
-- Name: sensors_identity_unique_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX sensors_identity_unique_idx ON public.sensors USING btree (zone_id, node_id, scope, type, label);


--
-- Name: sensors_node_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_node_idx ON public.sensors USING btree (node_id);


--
-- Name: sensors_zone_active_type_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_zone_active_type_id_idx ON public.sensors USING btree (zone_id, type, id DESC) WHERE (is_active = true);


--
-- Name: sensors_zone_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sensors_zone_idx ON public.sensors USING btree (zone_id);


--
-- Name: sessions_last_activity_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_last_activity_index ON public.sessions USING btree (last_activity);


--
-- Name: sessions_user_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_user_id_index ON public.sessions USING btree (user_id);


--
-- Name: simulation_events_service_stage_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_events_service_stage_idx ON public.simulation_events USING btree (service, stage);


--
-- Name: simulation_events_sim_id_occurred_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_events_sim_id_occurred_idx ON public.simulation_events USING btree (simulation_id, occurred_at);


--
-- Name: simulation_events_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_events_status_idx ON public.simulation_events USING btree (status);


--
-- Name: simulation_events_zone_id_occurred_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_events_zone_id_occurred_idx ON public.simulation_events USING btree (zone_id, occurred_at);


--
-- Name: simulation_reports_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_reports_status_index ON public.simulation_reports USING btree (status);


--
-- Name: simulation_reports_zone_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX simulation_reports_zone_id_index ON public.simulation_reports USING btree (zone_id);


--
-- Name: system_logs_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX system_logs_created_at_idx ON public.system_logs USING btree (created_at);


--
-- Name: system_logs_level_created_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX system_logs_level_created_idx ON public.system_logs USING btree (level, created_at);


--
-- Name: system_logs_service_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX system_logs_service_idx ON public.system_logs USING btree (COALESCE((context ->> 'service'::text), (context ->> 'source'::text), 'system'::text));


--
-- Name: telemetry_agg_1h_node_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1h_node_ts_idx ON public.telemetry_agg_1h USING btree (node_id, ts);


--
-- Name: telemetry_agg_1h_ts_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1h_ts_index ON public.telemetry_agg_1h USING btree (ts);


--
-- Name: telemetry_agg_1h_zone_metric_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1h_zone_metric_ts_idx ON public.telemetry_agg_1h USING btree (zone_id, metric_type, ts);


--
-- Name: telemetry_agg_1m_node_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1m_node_ts_idx ON public.telemetry_agg_1m USING btree (node_id, ts);


--
-- Name: telemetry_agg_1m_ts_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1m_ts_index ON public.telemetry_agg_1m USING btree (ts);


--
-- Name: telemetry_agg_1m_zone_metric_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_agg_1m_zone_metric_ts_idx ON public.telemetry_agg_1m USING btree (zone_id, metric_type, ts);


--
-- Name: telemetry_daily_date_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_daily_date_index ON public.telemetry_daily USING btree (date);


--
-- Name: telemetry_daily_node_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_daily_node_date_idx ON public.telemetry_daily USING btree (node_id, date);


--
-- Name: telemetry_daily_zone_metric_date_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_daily_zone_metric_date_idx ON public.telemetry_daily USING btree (zone_id, metric_type, date);


--
-- Name: telemetry_last_sensor_updated_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_last_sensor_updated_at_idx ON public.telemetry_last USING btree (sensor_id, updated_at DESC);


--
-- Name: telemetry_last_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_last_ts_idx ON public.telemetry_last USING btree (last_ts);


--
-- Name: telemetry_samples_cycle_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_samples_cycle_ts_idx ON public.telemetry_samples USING btree (cycle_id, ts);


--
-- Name: telemetry_samples_quality_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_samples_quality_idx ON public.telemetry_samples USING btree (quality);


--
-- Name: telemetry_samples_sensor_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_samples_sensor_ts_idx ON public.telemetry_samples USING btree (sensor_id, ts);


--
-- Name: telemetry_samples_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_samples_ts_idx ON public.telemetry_samples USING btree (ts);


--
-- Name: telemetry_samples_zone_ts_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX telemetry_samples_zone_ts_idx ON public.telemetry_samples USING btree (zone_id, ts);


--
-- Name: unassigned_errors_archive_archived_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_archive_archived_at_idx ON public.unassigned_node_errors_archive USING btree (archived_at);


--
-- Name: unassigned_errors_archive_hardware_code_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_archive_hardware_code_idx ON public.unassigned_node_errors_archive USING btree (hardware_id, error_code);


--
-- Name: unassigned_errors_archive_hardware_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_archive_hardware_id_idx ON public.unassigned_node_errors_archive USING btree (hardware_id);


--
-- Name: unassigned_errors_archive_node_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_archive_node_id_idx ON public.unassigned_node_errors_archive USING btree (node_id);


--
-- Name: unassigned_errors_hardware_code_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_hardware_code_idx ON public.unassigned_node_errors USING btree (hardware_id, error_code);


--
-- Name: unassigned_errors_hardware_code_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX unassigned_errors_hardware_code_unique ON public.unassigned_node_errors USING btree (hardware_id, COALESCE(error_code, ''::character varying));


--
-- Name: unassigned_errors_hardware_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_hardware_id_idx ON public.unassigned_node_errors USING btree (hardware_id);


--
-- Name: unassigned_errors_last_seen_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_last_seen_idx ON public.unassigned_node_errors USING btree (last_seen_at);


--
-- Name: unassigned_errors_node_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_errors_node_id_idx ON public.unassigned_node_errors USING btree (node_id);


--
-- Name: unassigned_node_errors_archive_hardware_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_node_errors_archive_hardware_id_index ON public.unassigned_node_errors_archive USING btree (hardware_id);


--
-- Name: unassigned_node_errors_hardware_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX unassigned_node_errors_hardware_id_index ON public.unassigned_node_errors USING btree (hardware_id);


--
-- Name: uniq_sensor_cal_active_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_sensor_cal_active_channel ON public.sensor_calibrations USING btree (node_channel_id) WHERE ((status)::text <> ALL ((ARRAY['completed'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[]));


--
-- Name: user_greenhouses_greenhouse_user_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_greenhouses_greenhouse_user_idx ON public.user_greenhouses USING btree (greenhouse_id, user_id);


--
-- Name: user_zones_zone_user_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_zones_zone_user_idx ON public.user_zones USING btree (zone_id, user_id);


--
-- Name: zone_automation_intents_status_not_before_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_automation_intents_status_not_before_idx ON public.zone_automation_intents USING btree (status, not_before);


--
-- Name: zone_automation_intents_zone_idempotency_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX zone_automation_intents_zone_idempotency_unique ON public.zone_automation_intents USING btree (zone_id, idempotency_key);


--
-- Name: zone_automation_intents_zone_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_automation_intents_zone_status_idx ON public.zone_automation_intents USING btree (zone_id, status);


--
-- Name: zone_automation_presets_compat_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_automation_presets_compat_idx ON public.zone_automation_presets USING btree (tanks_count, irrigation_system_type);


--
-- Name: zone_automation_presets_scope_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_automation_presets_scope_idx ON public.zone_automation_presets USING btree (scope);


--
-- Name: zone_config_changes_zone_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_config_changes_zone_id_created_at_index ON public.zone_config_changes USING btree (zone_id, created_at);


--
-- Name: zone_config_changes_zone_id_namespace_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_config_changes_zone_id_namespace_index ON public.zone_config_changes USING btree (zone_id, namespace);


--
-- Name: zone_events_partitioned_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_type_idx ON ONLY public.zone_events USING btree (type);


--
-- Name: zone_events_partitioned_2026_03_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_03_type_idx ON public.zone_events_partitioned_2026_03 USING btree (type);


--
-- Name: zone_events_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_type_idx ON ONLY public.zone_events USING btree (type);


--
-- Name: zone_events_partitioned_2026_03_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_03_type_idx1 ON public.zone_events_partitioned_2026_03 USING btree (type);


--
-- Name: zone_events_partitioned_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_zone_id_created_at_idx ON ONLY public.zone_events USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_03_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_03_zone_id_created_at_idx ON public.zone_events_partitioned_2026_03 USING btree (zone_id, created_at);


--
-- Name: zone_events_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_zone_id_created_at_idx ON ONLY public.zone_events USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_03_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_03_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_03 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_04_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_04_type_idx ON public.zone_events_partitioned_2026_04 USING btree (type);


--
-- Name: zone_events_partitioned_2026_04_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_04_type_idx1 ON public.zone_events_partitioned_2026_04 USING btree (type);


--
-- Name: zone_events_partitioned_2026_04_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_04_zone_id_created_at_idx ON public.zone_events_partitioned_2026_04 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_04_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_04_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_04 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_05_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_05_type_idx ON public.zone_events_partitioned_2026_05 USING btree (type);


--
-- Name: zone_events_partitioned_2026_05_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_05_type_idx1 ON public.zone_events_partitioned_2026_05 USING btree (type);


--
-- Name: zone_events_partitioned_2026_05_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_05_zone_id_created_at_idx ON public.zone_events_partitioned_2026_05 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_05_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_05_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_05 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_06_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_06_type_idx ON public.zone_events_partitioned_2026_06 USING btree (type);


--
-- Name: zone_events_partitioned_2026_06_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_06_type_idx1 ON public.zone_events_partitioned_2026_06 USING btree (type);


--
-- Name: zone_events_partitioned_2026_06_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_06_zone_id_created_at_idx ON public.zone_events_partitioned_2026_06 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_06_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_06_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_06 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_07_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_07_type_idx ON public.zone_events_partitioned_2026_07 USING btree (type);


--
-- Name: zone_events_partitioned_2026_07_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_07_type_idx1 ON public.zone_events_partitioned_2026_07 USING btree (type);


--
-- Name: zone_events_partitioned_2026_07_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_07_zone_id_created_at_idx ON public.zone_events_partitioned_2026_07 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_07_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_07_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_07 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_08_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_08_type_idx ON public.zone_events_partitioned_2026_08 USING btree (type);


--
-- Name: zone_events_partitioned_2026_08_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_08_type_idx1 ON public.zone_events_partitioned_2026_08 USING btree (type);


--
-- Name: zone_events_partitioned_2026_08_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_08_zone_id_created_at_idx ON public.zone_events_partitioned_2026_08 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_08_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_08_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_08 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_09_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_09_type_idx ON public.zone_events_partitioned_2026_09 USING btree (type);


--
-- Name: zone_events_partitioned_2026_09_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_09_type_idx1 ON public.zone_events_partitioned_2026_09 USING btree (type);


--
-- Name: zone_events_partitioned_2026_09_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_09_zone_id_created_at_idx ON public.zone_events_partitioned_2026_09 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_09_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_09_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_09 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_10_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_10_type_idx ON public.zone_events_partitioned_2026_10 USING btree (type);


--
-- Name: zone_events_partitioned_2026_10_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_10_type_idx1 ON public.zone_events_partitioned_2026_10 USING btree (type);


--
-- Name: zone_events_partitioned_2026_10_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_10_zone_id_created_at_idx ON public.zone_events_partitioned_2026_10 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_10_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_10_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_10 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_11_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_11_type_idx ON public.zone_events_partitioned_2026_11 USING btree (type);


--
-- Name: zone_events_partitioned_2026_11_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_11_type_idx1 ON public.zone_events_partitioned_2026_11 USING btree (type);


--
-- Name: zone_events_partitioned_2026_11_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_11_zone_id_created_at_idx ON public.zone_events_partitioned_2026_11 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_11_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_11_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_11 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_12_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_12_type_idx ON public.zone_events_partitioned_2026_12 USING btree (type);


--
-- Name: zone_events_partitioned_2026_12_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_12_type_idx1 ON public.zone_events_partitioned_2026_12 USING btree (type);


--
-- Name: zone_events_partitioned_2026_12_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_12_zone_id_created_at_idx ON public.zone_events_partitioned_2026_12 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2026_12_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2026_12_zone_id_created_at_idx1 ON public.zone_events_partitioned_2026_12 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_01_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_01_type_idx ON public.zone_events_partitioned_2027_01 USING btree (type);


--
-- Name: zone_events_partitioned_2027_01_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_01_type_idx1 ON public.zone_events_partitioned_2027_01 USING btree (type);


--
-- Name: zone_events_partitioned_2027_01_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_01_zone_id_created_at_idx ON public.zone_events_partitioned_2027_01 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_01_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_01_zone_id_created_at_idx1 ON public.zone_events_partitioned_2027_01 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_02_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_02_type_idx ON public.zone_events_partitioned_2027_02 USING btree (type);


--
-- Name: zone_events_partitioned_2027_02_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_02_type_idx1 ON public.zone_events_partitioned_2027_02 USING btree (type);


--
-- Name: zone_events_partitioned_2027_02_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_02_zone_id_created_at_idx ON public.zone_events_partitioned_2027_02 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_02_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_02_zone_id_created_at_idx1 ON public.zone_events_partitioned_2027_02 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_03_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_03_type_idx ON public.zone_events_partitioned_2027_03 USING btree (type);


--
-- Name: zone_events_partitioned_2027_03_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_03_type_idx1 ON public.zone_events_partitioned_2027_03 USING btree (type);


--
-- Name: zone_events_partitioned_2027_03_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_03_zone_id_created_at_idx ON public.zone_events_partitioned_2027_03 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_03_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_03_zone_id_created_at_idx1 ON public.zone_events_partitioned_2027_03 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_04_type_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_04_type_idx ON public.zone_events_partitioned_2027_04 USING btree (type);


--
-- Name: zone_events_partitioned_2027_04_type_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_04_type_idx1 ON public.zone_events_partitioned_2027_04 USING btree (type);


--
-- Name: zone_events_partitioned_2027_04_zone_id_created_at_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_04_zone_id_created_at_idx ON public.zone_events_partitioned_2027_04 USING btree (zone_id, created_at);


--
-- Name: zone_events_partitioned_2027_04_zone_id_created_at_idx1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_events_partitioned_2027_04_zone_id_created_at_idx1 ON public.zone_events_partitioned_2027_04 USING btree (zone_id, created_at);


--
-- Name: zone_model_params_zone_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_model_params_zone_id_index ON public.zone_model_params USING btree (zone_id);


--
-- Name: zone_simulations_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_simulations_status_index ON public.zone_simulations USING btree (status);


--
-- Name: zone_simulations_zone_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_simulations_zone_id_created_at_index ON public.zone_simulations USING btree (zone_id, created_at);


--
-- Name: zone_workflow_state_scheduler_task_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_workflow_state_scheduler_task_id_index ON public.zone_workflow_state USING btree (scheduler_task_id);


--
-- Name: zone_workflow_state_updated_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_workflow_state_updated_at_index ON public.zone_workflow_state USING btree (updated_at);


--
-- Name: zone_workflow_state_workflow_phase_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zone_workflow_state_workflow_phase_index ON public.zone_workflow_state USING btree (workflow_phase);


--
-- Name: zones_automation_runtime_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zones_automation_runtime_idx ON public.zones USING btree (automation_runtime);


--
-- Name: zones_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX zones_status_idx ON public.zones USING btree (status);


--
-- Name: commands_partitioned_2026_03_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_03_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_03_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_03_cmd_id_idx;


--
-- Name: commands_partitioned_2026_03_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_03_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_03_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_03_status_idx;


--
-- Name: commands_partitioned_2026_03_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_03_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_04_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_04_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_04_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_04_cmd_id_idx;


--
-- Name: commands_partitioned_2026_04_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_04_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_04_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_04_status_idx;


--
-- Name: commands_partitioned_2026_04_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_04_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_05_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_05_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_05_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_05_cmd_id_idx;


--
-- Name: commands_partitioned_2026_05_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_05_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_05_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_05_status_idx;


--
-- Name: commands_partitioned_2026_05_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_05_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_06_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_06_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_06_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_06_cmd_id_idx;


--
-- Name: commands_partitioned_2026_06_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_06_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_06_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_06_status_idx;


--
-- Name: commands_partitioned_2026_06_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_06_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_07_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_07_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_07_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_07_cmd_id_idx;


--
-- Name: commands_partitioned_2026_07_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_07_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_07_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_07_status_idx;


--
-- Name: commands_partitioned_2026_07_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_07_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_08_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_08_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_08_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_08_cmd_id_idx;


--
-- Name: commands_partitioned_2026_08_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_08_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_08_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_08_status_idx;


--
-- Name: commands_partitioned_2026_08_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_08_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_09_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_09_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_09_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_09_cmd_id_idx;


--
-- Name: commands_partitioned_2026_09_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_09_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_09_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_09_status_idx;


--
-- Name: commands_partitioned_2026_09_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_09_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_10_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_10_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_10_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_10_cmd_id_idx;


--
-- Name: commands_partitioned_2026_10_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_10_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_10_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_10_status_idx;


--
-- Name: commands_partitioned_2026_10_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_10_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_11_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_11_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_11_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_11_cmd_id_idx;


--
-- Name: commands_partitioned_2026_11_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_11_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_11_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_11_status_idx;


--
-- Name: commands_partitioned_2026_11_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_11_status_updated_at_idx;


--
-- Name: commands_partitioned_2026_12_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2026_12_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2026_12_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_12_cmd_id_idx;


--
-- Name: commands_partitioned_2026_12_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2026_12_cmd_id_idx1;


--
-- Name: commands_partitioned_2026_12_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2026_12_status_idx;


--
-- Name: commands_partitioned_2026_12_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2026_12_status_updated_at_idx;


--
-- Name: commands_partitioned_2027_01_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2027_01_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2027_01_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_01_cmd_id_idx;


--
-- Name: commands_partitioned_2027_01_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_01_cmd_id_idx1;


--
-- Name: commands_partitioned_2027_01_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2027_01_status_idx;


--
-- Name: commands_partitioned_2027_01_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2027_01_status_updated_at_idx;


--
-- Name: commands_partitioned_2027_02_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2027_02_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2027_02_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_02_cmd_id_idx;


--
-- Name: commands_partitioned_2027_02_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_02_cmd_id_idx1;


--
-- Name: commands_partitioned_2027_02_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2027_02_status_idx;


--
-- Name: commands_partitioned_2027_02_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2027_02_status_updated_at_idx;


--
-- Name: commands_partitioned_2027_03_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2027_03_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2027_03_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_03_cmd_id_idx;


--
-- Name: commands_partitioned_2027_03_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_03_cmd_id_idx1;


--
-- Name: commands_partitioned_2027_03_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2027_03_status_idx;


--
-- Name: commands_partitioned_2027_03_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2027_03_status_updated_at_idx;


--
-- Name: commands_partitioned_2027_04_cmd_id_created_at_key; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_created_at_unique ATTACH PARTITION public.commands_partitioned_2027_04_cmd_id_created_at_key;


--
-- Name: commands_partitioned_2027_04_cmd_id_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_partitioned_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_04_cmd_id_idx;


--
-- Name: commands_partitioned_2027_04_cmd_id_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_cmd_id_idx ATTACH PARTITION public.commands_partitioned_2027_04_cmd_id_idx1;


--
-- Name: commands_partitioned_2027_04_status_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_idx ATTACH PARTITION public.commands_partitioned_2027_04_status_idx;


--
-- Name: commands_partitioned_2027_04_status_updated_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.commands_status_updated_at_idx ATTACH PARTITION public.commands_partitioned_2027_04_status_updated_at_idx;


--
-- Name: zone_events_partitioned_2026_03_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_03_pkey;


--
-- Name: zone_events_partitioned_2026_03_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_03_type_idx;


--
-- Name: zone_events_partitioned_2026_03_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_03_type_idx1;


--
-- Name: zone_events_partitioned_2026_03_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_03_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_03_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_03_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_04_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_04_pkey;


--
-- Name: zone_events_partitioned_2026_04_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_04_type_idx;


--
-- Name: zone_events_partitioned_2026_04_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_04_type_idx1;


--
-- Name: zone_events_partitioned_2026_04_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_04_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_04_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_04_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_05_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_05_pkey;


--
-- Name: zone_events_partitioned_2026_05_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_05_type_idx;


--
-- Name: zone_events_partitioned_2026_05_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_05_type_idx1;


--
-- Name: zone_events_partitioned_2026_05_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_05_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_05_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_05_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_06_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_06_pkey;


--
-- Name: zone_events_partitioned_2026_06_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_06_type_idx;


--
-- Name: zone_events_partitioned_2026_06_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_06_type_idx1;


--
-- Name: zone_events_partitioned_2026_06_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_06_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_06_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_06_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_07_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_07_pkey;


--
-- Name: zone_events_partitioned_2026_07_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_07_type_idx;


--
-- Name: zone_events_partitioned_2026_07_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_07_type_idx1;


--
-- Name: zone_events_partitioned_2026_07_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_07_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_07_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_07_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_08_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_08_pkey;


--
-- Name: zone_events_partitioned_2026_08_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_08_type_idx;


--
-- Name: zone_events_partitioned_2026_08_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_08_type_idx1;


--
-- Name: zone_events_partitioned_2026_08_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_08_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_08_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_08_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_09_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_09_pkey;


--
-- Name: zone_events_partitioned_2026_09_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_09_type_idx;


--
-- Name: zone_events_partitioned_2026_09_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_09_type_idx1;


--
-- Name: zone_events_partitioned_2026_09_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_09_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_09_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_09_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_10_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_10_pkey;


--
-- Name: zone_events_partitioned_2026_10_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_10_type_idx;


--
-- Name: zone_events_partitioned_2026_10_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_10_type_idx1;


--
-- Name: zone_events_partitioned_2026_10_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_10_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_10_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_10_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_11_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_11_pkey;


--
-- Name: zone_events_partitioned_2026_11_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_11_type_idx;


--
-- Name: zone_events_partitioned_2026_11_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_11_type_idx1;


--
-- Name: zone_events_partitioned_2026_11_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_11_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_11_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_11_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2026_12_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2026_12_pkey;


--
-- Name: zone_events_partitioned_2026_12_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_12_type_idx;


--
-- Name: zone_events_partitioned_2026_12_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2026_12_type_idx1;


--
-- Name: zone_events_partitioned_2026_12_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_12_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2026_12_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2026_12_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2027_01_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2027_01_pkey;


--
-- Name: zone_events_partitioned_2027_01_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_01_type_idx;


--
-- Name: zone_events_partitioned_2027_01_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_01_type_idx1;


--
-- Name: zone_events_partitioned_2027_01_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_01_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2027_01_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_01_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2027_02_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2027_02_pkey;


--
-- Name: zone_events_partitioned_2027_02_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_02_type_idx;


--
-- Name: zone_events_partitioned_2027_02_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_02_type_idx1;


--
-- Name: zone_events_partitioned_2027_02_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_02_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2027_02_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_02_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2027_03_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2027_03_pkey;


--
-- Name: zone_events_partitioned_2027_03_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_03_type_idx;


--
-- Name: zone_events_partitioned_2027_03_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_03_type_idx1;


--
-- Name: zone_events_partitioned_2027_03_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_03_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2027_03_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_03_zone_id_created_at_idx1;


--
-- Name: zone_events_partitioned_2027_04_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_pkey ATTACH PARTITION public.zone_events_partitioned_2027_04_pkey;


--
-- Name: zone_events_partitioned_2027_04_type_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_04_type_idx;


--
-- Name: zone_events_partitioned_2027_04_type_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_type_idx ATTACH PARTITION public.zone_events_partitioned_2027_04_type_idx1;


--
-- Name: zone_events_partitioned_2027_04_zone_id_created_at_idx; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_partitioned_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_04_zone_id_created_at_idx;


--
-- Name: zone_events_partitioned_2027_04_zone_id_created_at_idx1; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.zone_events_zone_id_created_at_idx ATTACH PARTITION public.zone_events_partitioned_2027_04_zone_id_created_at_idx1;


--
-- Name: commands trg_ae_command_status_notify; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ae_command_status_notify AFTER INSERT OR UPDATE OF status, updated_at ON public.commands FOR EACH ROW EXECUTE FUNCTION public.ae_notify_command_status();


--
-- Name: telemetry_last trg_ae_signal_update_telemetry_last; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ae_signal_update_telemetry_last AFTER INSERT OR UPDATE OF last_value, last_ts, updated_at ON public.telemetry_last FOR EACH ROW EXECUTE FUNCTION public.ae_notify_signal_update();


--
-- Name: zone_events trg_ae_signal_update_zone_events; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_ae_signal_update_zone_events AFTER INSERT OR UPDATE ON public.zone_events FOR EACH ROW EXECUTE FUNCTION public.ae_notify_signal_update();


--
-- Name: zone_automation_intents trg_intent_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_intent_terminal AFTER UPDATE ON public.zone_automation_intents FOR EACH ROW EXECUTE FUNCTION public.notify_intent_terminal();


--
-- Name: ae_commands ae_commands_task_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_commands
    ADD CONSTRAINT ae_commands_task_id_foreign FOREIGN KEY (task_id) REFERENCES public.ae_tasks(id) ON DELETE CASCADE;


--
-- Name: ae_stage_transitions ae_stage_transitions_task_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_stage_transitions
    ADD CONSTRAINT ae_stage_transitions_task_id_foreign FOREIGN KEY (task_id) REFERENCES public.ae_tasks(id) ON DELETE CASCADE;


--
-- Name: ae_tasks ae_tasks_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_tasks
    ADD CONSTRAINT ae_tasks_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: ae_zone_leases ae_zone_leases_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ae_zone_leases
    ADD CONSTRAINT ae_zone_leases_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: ai_logs ai_logs_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_logs
    ADD CONSTRAINT ai_logs_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: automation_config_documents automation_config_documents_updated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_documents
    ADD CONSTRAINT automation_config_documents_updated_by_foreign FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: automation_config_preset_versions automation_config_preset_versions_changed_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_preset_versions
    ADD CONSTRAINT automation_config_preset_versions_changed_by_foreign FOREIGN KEY (changed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: automation_config_preset_versions automation_config_preset_versions_preset_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_preset_versions
    ADD CONSTRAINT automation_config_preset_versions_preset_id_foreign FOREIGN KEY (preset_id) REFERENCES public.automation_config_presets(id) ON DELETE CASCADE;


--
-- Name: automation_config_presets automation_config_presets_updated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_presets
    ADD CONSTRAINT automation_config_presets_updated_by_foreign FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: automation_config_versions automation_config_versions_changed_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_versions
    ADD CONSTRAINT automation_config_versions_changed_by_foreign FOREIGN KEY (changed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: automation_config_versions automation_config_versions_document_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.automation_config_versions
    ADD CONSTRAINT automation_config_versions_document_id_foreign FOREIGN KEY (document_id) REFERENCES public.automation_config_documents(id) ON DELETE CASCADE;


--
-- Name: channel_bindings channel_bindings_infrastructure_instance_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings
    ADD CONSTRAINT channel_bindings_infrastructure_instance_id_foreign FOREIGN KEY (infrastructure_instance_id) REFERENCES public.infrastructure_instances(id) ON DELETE CASCADE;


--
-- Name: channel_bindings channel_bindings_node_channel_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.channel_bindings
    ADD CONSTRAINT channel_bindings_node_channel_id_foreign FOREIGN KEY (node_channel_id) REFERENCES public.node_channels(id) ON DELETE CASCADE;


--
-- Name: command_audit command_audit_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_audit
    ADD CONSTRAINT command_audit_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: command_tracking command_tracking_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_tracking
    ADD CONSTRAINT command_tracking_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: commands commands_partitioned_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.commands
    ADD CONSTRAINT commands_partitioned_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: commands commands_partitioned_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.commands
    ADD CONSTRAINT commands_partitioned_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: greenhouses greenhouses_greenhouse_type_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.greenhouses
    ADD CONSTRAINT greenhouses_greenhouse_type_id_foreign FOREIGN KEY (greenhouse_type_id) REFERENCES public.greenhouse_types(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phase_steps grow_cycle_phase_steps_grow_cycle_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phase_steps
    ADD CONSTRAINT grow_cycle_phase_steps_grow_cycle_phase_id_foreign FOREIGN KEY (grow_cycle_phase_id) REFERENCES public.grow_cycle_phases(id) ON DELETE CASCADE;


--
-- Name: grow_cycle_phase_steps grow_cycle_phase_steps_recipe_revision_phase_step_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phase_steps
    ADD CONSTRAINT grow_cycle_phase_steps_recipe_revision_phase_step_id_foreign FOREIGN KEY (recipe_revision_phase_step_id) REFERENCES public.recipe_revision_phase_steps(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phases grow_cycle_phases_grow_cycle_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_grow_cycle_id_foreign FOREIGN KEY (grow_cycle_id) REFERENCES public.grow_cycles(id) ON DELETE CASCADE;


--
-- Name: grow_cycle_phases grow_cycle_phases_nutrient_calcium_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_nutrient_calcium_product_id_foreign FOREIGN KEY (nutrient_calcium_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phases grow_cycle_phases_nutrient_magnesium_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_nutrient_magnesium_product_id_foreign FOREIGN KEY (nutrient_magnesium_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phases grow_cycle_phases_nutrient_micro_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_nutrient_micro_product_id_foreign FOREIGN KEY (nutrient_micro_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phases grow_cycle_phases_nutrient_npk_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_nutrient_npk_product_id_foreign FOREIGN KEY (nutrient_npk_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_phases grow_cycle_phases_recipe_revision_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_phases
    ADD CONSTRAINT grow_cycle_phases_recipe_revision_phase_id_foreign FOREIGN KEY (recipe_revision_phase_id) REFERENCES public.recipe_revision_phases(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_from_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_from_phase_id_foreign FOREIGN KEY (from_phase_id) REFERENCES public.recipe_revision_phases(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_from_step_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_from_step_id_foreign FOREIGN KEY (from_step_id) REFERENCES public.recipe_revision_phase_steps(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_grow_cycle_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_grow_cycle_id_foreign FOREIGN KEY (grow_cycle_id) REFERENCES public.grow_cycles(id) ON DELETE CASCADE;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_to_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_to_phase_id_foreign FOREIGN KEY (to_phase_id) REFERENCES public.recipe_revision_phases(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_to_step_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_to_step_id_foreign FOREIGN KEY (to_step_id) REFERENCES public.recipe_revision_phase_steps(id) ON DELETE SET NULL;


--
-- Name: grow_cycle_transitions grow_cycle_transitions_triggered_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycle_transitions
    ADD CONSTRAINT grow_cycle_transitions_triggered_by_foreign FOREIGN KEY (triggered_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: grow_cycles grow_cycles_current_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_current_phase_id_foreign FOREIGN KEY (current_phase_id) REFERENCES public.grow_cycle_phases(id) ON DELETE SET NULL;


--
-- Name: grow_cycles grow_cycles_current_step_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_current_step_id_foreign FOREIGN KEY (current_step_id) REFERENCES public.grow_cycle_phase_steps(id) ON DELETE SET NULL;


--
-- Name: grow_cycles grow_cycles_greenhouse_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_greenhouse_id_foreign FOREIGN KEY (greenhouse_id) REFERENCES public.greenhouses(id) ON DELETE CASCADE;


--
-- Name: grow_cycles grow_cycles_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE SET NULL;


--
-- Name: grow_cycles grow_cycles_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_recipe_id_foreign FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE SET NULL;


--
-- Name: grow_cycles grow_cycles_recipe_revision_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_recipe_revision_id_foreign FOREIGN KEY (recipe_revision_id) REFERENCES public.recipe_revisions(id) ON DELETE CASCADE;


--
-- Name: grow_cycles grow_cycles_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grow_cycles
    ADD CONSTRAINT grow_cycles_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: harvests harvests_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.harvests
    ADD CONSTRAINT harvests_recipe_id_foreign FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE SET NULL;


--
-- Name: harvests harvests_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.harvests
    ADD CONSTRAINT harvests_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: laravel_scheduler_active_tasks laravel_scheduler_active_tasks_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_active_tasks
    ADD CONSTRAINT laravel_scheduler_active_tasks_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: laravel_scheduler_zone_cursors laravel_scheduler_zone_cursors_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.laravel_scheduler_zone_cursors
    ADD CONSTRAINT laravel_scheduler_zone_cursors_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: node_channels node_channels_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_channels
    ADD CONSTRAINT node_channels_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE CASCADE;


--
-- Name: node_logs node_logs_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_logs
    ADD CONSTRAINT node_logs_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE CASCADE;


--
-- Name: nodes nodes_pending_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_pending_zone_id_foreign FOREIGN KEY (pending_zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: nodes nodes_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: parameter_predictions parameter_predictions_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parameter_predictions
    ADD CONSTRAINT parameter_predictions_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: pending_alerts pending_alerts_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_alerts
    ADD CONSTRAINT pending_alerts_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: pid_state pid_state_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pid_state
    ADD CONSTRAINT pid_state_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: plant_cost_items plant_cost_items_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_cost_items
    ADD CONSTRAINT plant_cost_items_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE CASCADE;


--
-- Name: plant_cost_items plant_cost_items_plant_price_version_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_cost_items
    ADD CONSTRAINT plant_cost_items_plant_price_version_id_foreign FOREIGN KEY (plant_price_version_id) REFERENCES public.plant_price_versions(id) ON DELETE CASCADE;


--
-- Name: plant_price_versions plant_price_versions_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_price_versions
    ADD CONSTRAINT plant_price_versions_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE CASCADE;


--
-- Name: plant_recipe plant_recipe_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_recipe
    ADD CONSTRAINT plant_recipe_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE CASCADE;


--
-- Name: plant_recipe plant_recipe_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_recipe
    ADD CONSTRAINT plant_recipe_recipe_id_foreign FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: plant_sale_prices plant_sale_prices_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_sale_prices
    ADD CONSTRAINT plant_sale_prices_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE CASCADE;


--
-- Name: plant_sale_prices plant_sale_prices_plant_price_version_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_sale_prices
    ADD CONSTRAINT plant_sale_prices_plant_price_version_id_foreign FOREIGN KEY (plant_price_version_id) REFERENCES public.plant_price_versions(id) ON DELETE CASCADE;


--
-- Name: plant_zone plant_zone_plant_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_zone
    ADD CONSTRAINT plant_zone_plant_id_foreign FOREIGN KEY (plant_id) REFERENCES public.plants(id) ON DELETE CASCADE;


--
-- Name: plant_zone plant_zone_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plant_zone
    ADD CONSTRAINT plant_zone_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: presets presets_default_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_default_recipe_id_foreign FOREIGN KEY (default_recipe_id) REFERENCES public.recipes(id) ON DELETE SET NULL;


--
-- Name: pump_calibrations pump_calibrations_node_channel_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pump_calibrations
    ADD CONSTRAINT pump_calibrations_node_channel_id_foreign FOREIGN KEY (node_channel_id) REFERENCES public.node_channels(id) ON DELETE CASCADE;


--
-- Name: recipe_analytics recipe_analytics_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_analytics
    ADD CONSTRAINT recipe_analytics_recipe_id_foreign FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: recipe_analytics recipe_analytics_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_analytics
    ADD CONSTRAINT recipe_analytics_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: recipe_revision_phase_steps recipe_revision_phase_steps_phase_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phase_steps
    ADD CONSTRAINT recipe_revision_phase_steps_phase_id_foreign FOREIGN KEY (phase_id) REFERENCES public.recipe_revision_phases(id) ON DELETE CASCADE;


--
-- Name: recipe_revision_phases recipe_revision_phases_nutrient_calcium_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_nutrient_calcium_product_id_foreign FOREIGN KEY (nutrient_calcium_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: recipe_revision_phases recipe_revision_phases_nutrient_magnesium_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_nutrient_magnesium_product_id_foreign FOREIGN KEY (nutrient_magnesium_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: recipe_revision_phases recipe_revision_phases_nutrient_micro_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_nutrient_micro_product_id_foreign FOREIGN KEY (nutrient_micro_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: recipe_revision_phases recipe_revision_phases_nutrient_npk_product_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_nutrient_npk_product_id_foreign FOREIGN KEY (nutrient_npk_product_id) REFERENCES public.nutrient_products(id) ON DELETE SET NULL;


--
-- Name: recipe_revision_phases recipe_revision_phases_recipe_revision_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_recipe_revision_id_foreign FOREIGN KEY (recipe_revision_id) REFERENCES public.recipe_revisions(id) ON DELETE CASCADE;


--
-- Name: recipe_revision_phases recipe_revision_phases_stage_template_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revision_phases
    ADD CONSTRAINT recipe_revision_phases_stage_template_id_foreign FOREIGN KEY (stage_template_id) REFERENCES public.grow_stage_templates(id) ON DELETE SET NULL;


--
-- Name: recipe_revisions recipe_revisions_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revisions
    ADD CONSTRAINT recipe_revisions_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: recipe_revisions recipe_revisions_recipe_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recipe_revisions
    ADD CONSTRAINT recipe_revisions_recipe_id_foreign FOREIGN KEY (recipe_id) REFERENCES public.recipes(id) ON DELETE CASCADE;


--
-- Name: sensor_calibrations sensor_calibrations_calibrated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT sensor_calibrations_calibrated_by_foreign FOREIGN KEY (calibrated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: sensor_calibrations sensor_calibrations_node_channel_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT sensor_calibrations_node_channel_id_foreign FOREIGN KEY (node_channel_id) REFERENCES public.node_channels(id) ON DELETE CASCADE;


--
-- Name: sensor_calibrations sensor_calibrations_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensor_calibrations
    ADD CONSTRAINT sensor_calibrations_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: sensors sensors_greenhouse_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_greenhouse_id_foreign FOREIGN KEY (greenhouse_id) REFERENCES public.greenhouses(id) ON DELETE CASCADE;


--
-- Name: sensors sensors_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: sensors sensors_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sensors
    ADD CONSTRAINT sensors_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: simulation_events simulation_events_simulation_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_events
    ADD CONSTRAINT simulation_events_simulation_id_foreign FOREIGN KEY (simulation_id) REFERENCES public.zone_simulations(id) ON DELETE CASCADE;


--
-- Name: simulation_events simulation_events_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_events
    ADD CONSTRAINT simulation_events_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: simulation_reports simulation_reports_simulation_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_reports
    ADD CONSTRAINT simulation_reports_simulation_id_foreign FOREIGN KEY (simulation_id) REFERENCES public.zone_simulations(id) ON DELETE CASCADE;


--
-- Name: simulation_reports simulation_reports_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_reports
    ADD CONSTRAINT simulation_reports_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: telemetry_agg_1h telemetry_agg_1h_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1h
    ADD CONSTRAINT telemetry_agg_1h_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: telemetry_agg_1h telemetry_agg_1h_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1h
    ADD CONSTRAINT telemetry_agg_1h_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: telemetry_agg_1m telemetry_agg_1m_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1m
    ADD CONSTRAINT telemetry_agg_1m_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: telemetry_agg_1m telemetry_agg_1m_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_agg_1m
    ADD CONSTRAINT telemetry_agg_1m_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: telemetry_daily telemetry_daily_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_daily
    ADD CONSTRAINT telemetry_daily_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: telemetry_daily telemetry_daily_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_daily
    ADD CONSTRAINT telemetry_daily_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: telemetry_last telemetry_last_sensor_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_last
    ADD CONSTRAINT telemetry_last_sensor_id_foreign FOREIGN KEY (sensor_id) REFERENCES public.sensors(id) ON DELETE CASCADE;


--
-- Name: telemetry_samples telemetry_samples_cycle_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_samples
    ADD CONSTRAINT telemetry_samples_cycle_id_foreign FOREIGN KEY (cycle_id) REFERENCES public.grow_cycles(id) ON DELETE SET NULL;


--
-- Name: telemetry_samples telemetry_samples_sensor_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_samples
    ADD CONSTRAINT telemetry_samples_sensor_id_foreign FOREIGN KEY (sensor_id) REFERENCES public.sensors(id) ON DELETE CASCADE;


--
-- Name: telemetry_samples telemetry_samples_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.telemetry_samples
    ADD CONSTRAINT telemetry_samples_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: unassigned_node_errors_archive unassigned_node_errors_archive_attached_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors_archive
    ADD CONSTRAINT unassigned_node_errors_archive_attached_zone_id_foreign FOREIGN KEY (attached_zone_id) REFERENCES public.zones(id) ON DELETE SET NULL;


--
-- Name: unassigned_node_errors_archive unassigned_node_errors_archive_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors_archive
    ADD CONSTRAINT unassigned_node_errors_archive_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: unassigned_node_errors unassigned_node_errors_node_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unassigned_node_errors
    ADD CONSTRAINT unassigned_node_errors_node_id_foreign FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE SET NULL;


--
-- Name: user_greenhouses user_greenhouses_greenhouse_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_greenhouses
    ADD CONSTRAINT user_greenhouses_greenhouse_id_foreign FOREIGN KEY (greenhouse_id) REFERENCES public.greenhouses(id) ON DELETE CASCADE;


--
-- Name: user_greenhouses user_greenhouses_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_greenhouses
    ADD CONSTRAINT user_greenhouses_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_zones user_zones_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zones
    ADD CONSTRAINT user_zones_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_zones user_zones_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_zones
    ADD CONSTRAINT user_zones_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_automation_intents zone_automation_intents_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_intents
    ADD CONSTRAINT zone_automation_intents_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_automation_presets zone_automation_presets_correction_preset_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets
    ADD CONSTRAINT zone_automation_presets_correction_preset_id_foreign FOREIGN KEY (correction_preset_id) REFERENCES public.automation_config_presets(id) ON DELETE SET NULL;


--
-- Name: zone_automation_presets zone_automation_presets_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets
    ADD CONSTRAINT zone_automation_presets_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: zone_automation_presets zone_automation_presets_updated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_presets
    ADD CONSTRAINT zone_automation_presets_updated_by_foreign FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: zone_automation_state zone_automation_state_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_automation_state
    ADD CONSTRAINT zone_automation_state_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_config_changes zone_config_changes_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_config_changes
    ADD CONSTRAINT zone_config_changes_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: zone_config_changes zone_config_changes_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_config_changes
    ADD CONSTRAINT zone_config_changes_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_correction_presets zone_correction_presets_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_correction_presets
    ADD CONSTRAINT zone_correction_presets_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: zone_correction_presets zone_correction_presets_updated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_correction_presets
    ADD CONSTRAINT zone_correction_presets_updated_by_foreign FOREIGN KEY (updated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: zone_events zone_events_partitioned_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.zone_events
    ADD CONSTRAINT zone_events_partitioned_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_model_params zone_model_params_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_model_params
    ADD CONSTRAINT zone_model_params_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_simulations zone_simulations_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_simulations
    ADD CONSTRAINT zone_simulations_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zone_workflow_state zone_workflow_state_zone_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zone_workflow_state
    ADD CONSTRAINT zone_workflow_state_zone_id_foreign FOREIGN KEY (zone_id) REFERENCES public.zones(id) ON DELETE CASCADE;


--
-- Name: zones zones_config_mode_changed_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_config_mode_changed_by_foreign FOREIGN KEY (config_mode_changed_by) REFERENCES public.users(id);


--
-- Name: zones zones_greenhouse_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_greenhouse_id_foreign FOREIGN KEY (greenhouse_id) REFERENCES public.greenhouses(id) ON DELETE CASCADE;


--
-- Name: zones zones_preset_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.zones
    ADD CONSTRAINT zones_preset_id_foreign FOREIGN KEY (preset_id) REFERENCES public.presets(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict 7Bu3CzYpaCjGLHzw5Arb3bcdEENof5MygKAPH3QYNIfqmSNkRayNgBsFC12ZZKN

