from prometheus_client import Counter, Histogram, Gauge

from common.redis_queue import QUEUE_SIZE as TELEMETRY_QUEUE_SIZE

TELEM_RECEIVED = Counter(
    "telemetry_received_total",
    "Total telemetry messages received",
)
TELEM_PROCESSED = Counter(
    "telemetry_processed_total",
    "Total telemetry messages processed",
)
TELEM_BATCH_SIZE = Histogram(
    "telemetry_batch_size",
    "Size of telemetry batches processed",
)
HEARTBEAT_RECEIVED = Counter(
    "heartbeat_received_total",
    "Total heartbeat messages received",
    ["node_uid"],
)
STATUS_RECEIVED = Counter(
    "status_received_total",
    "Total status messages received",
    ["node_uid", "status"],
)
DIAGNOSTICS_RECEIVED = Counter(
    "diagnostics_received_total",
    "Total diagnostics messages received",
    ["node_uid"],
)
ERROR_RECEIVED = Counter(
    "error_received_total",
    "Total error messages received",
    ["node_uid", "level"],
)
NODE_EVENT_RECEIVED = Counter(
    "node_event_received_total",
    "Total node event messages received",
    ["event_code"],
)
NODE_EVENT_UNKNOWN = Counter(
    "node_event_unknown_total",
    "Total node event messages mapped to OTHER metric label",
)
NODE_EVENT_ERROR = Counter(
    "node_event_error_total",
    "Total errors while processing node event messages",
    ["reason"],
)
NODE_HELLO_RECEIVED = Counter(
    "node_hello_received_total",
    "Total node_hello messages received",
)
NODE_HELLO_REGISTERED = Counter(
    "node_hello_registered_total",
    "Total nodes registered from node_hello",
)
NODE_HELLO_ERRORS = Counter(
    "node_hello_errors_total",
    "Total errors processing node_hello",
    ["error_type"],
)
CONFIG_REPORT_RECEIVED = Counter(
    "config_report_received_total",
    "Total config_report messages received",
)
CONFIG_REPORT_PROCESSED = Counter(
    "config_report_processed_total",
    "Total config_report messages processed",
)
CONFIG_REPORT_ERROR = Counter(
    "config_report_error_total",
    "Total error config_report messages",
    ["node_uid"],
)
CONFIG_REPORT_ACK_FAILED = Counter(
    "config_report_ack_failed_total",
    "config_report stored locally but Laravel config-report-observed ACK failed",
    ["node_uid"],
)
CONFIG_REPORT_CHANNEL_SYNC_FAILED = Counter(
    "config_report_channel_sync_failed_total",
    "config_report channel sync failed before marking processed",
    ["node_uid"],
)
MQTT_HANDLER_ERROR = Counter(
    "mqtt_handler_error_total",
    "MQTT handler failures surfaced via done_callback or handler guard",
    ["handler"],
)
NODE_UPDATE_ZERO_ROWS = Counter(
    "node_update_zero_rows_total",
    "Node UPDATE affected zero rows (unknown or stale node_uid)",
    ["handler"],
)
CONFIG_REPORT_BUFFER_EXPIRED = Counter(
    "config_report_buffer_expired_total",
    "Buffered config_report entries dropped after TTL expiry",
)
CONFIG_REPORT_BUFFER_OVERFLOW = Counter(
    "config_report_buffer_overflow_total",
    "Buffered config_report entries dropped due to buffer capacity",
)
COMMAND_RESPONSE_RECEIVED = Counter(
    "command_response_received_total",
    "Total command_response messages received",
)
COMMAND_RESPONSE_ERROR = Counter(
    "command_response_error_total",
    "Total error command_response messages",
)
COMMANDS_SENT = Counter(
    "commands_sent_total",
    "Total commands sent via REST API",
    ["zone_id", "metric"],
)
MQTT_PUBLISH_ERRORS = Counter(
    "mqtt_publish_errors_total",
    "MQTT publish errors",
    ["error_type"],
)
COMMANDS_PUBLISH_UNCONFIRMED = Counter(
    "commands_published_unconfirmed_total",
    "MQTT command publishes without PUBACK confirmation",
)
COMMAND_STATUS_DELIVERY_DROPPED = Counter(
    "command_status_delivery_dropped_total",
    "Command status updates dropped after delivery retries exhausted",
)
COMMAND_STATUS_DLQ_MOVED = Counter(
    "command_status_dlq_moved_total",
    "Command status updates moved to DLQ after retry exhaustion",
)
COMMAND_QUEUE_DRAIN_SCANNED = Counter(
    "command_queue_drain_scanned_total",
    "Queued commands scanned by drain worker",
)
COMMAND_QUEUE_DRAIN_SUCCEEDED = Counter(
    "command_queue_drain_succeeded_total",
    "Queued commands successfully republished by drain worker",
)
COMMAND_QUEUE_DRAIN_SKIPPED = Counter(
    "command_queue_drain_skipped_total",
    "Queued commands skipped by drain worker (non-republishable)",
)
COMMAND_QUEUE_DRAIN_FAILED = Counter(
    "command_queue_drain_failed_total",
    "Queued command drain republish failures",
)
TELEMETRY_DESERIALIZE_FAILED = Counter(
    "telemetry_deserialize_failed_total",
    "Telemetry queue items moved to dead list after deserialize failure",
)
TELEMETRY_PG_WRITE_FAILED = Counter(
    "telemetry_pg_write_failed_total",
    "Failed PostgreSQL writes during telemetry batch processing",
    ["stage"],
)
TELEMETRY_QUEUE_ORPHANED = Counter(
    "telemetry_queue_orphaned_total",
    "Processing-list move failed because raw item was not found",
)
TELEMETRY_SAMPLES_JOIN_MISMATCH = Counter(
    "telemetry_samples_join_mismatch_total",
    "telemetry_samples batch insert dropped rows due to sensors JOIN mismatch",
)
TELEMETRY_PROCESSING_RECLAIMED = Counter(
    "telemetry_processing_reclaimed_total",
    "Telemetry items reclaimed from processing list back to queue",
)
TELEMETRY_PROCESSING_STUCK = Counter(
    "telemetry_processing_stuck_total",
    "Telemetry processing-list ack/requeue operations with incomplete removal",
)
TELEMETRY_PROCESSING_SIZE = Gauge(
    "telemetry_processing_size",
    "Current size of hydro:telemetry:processing Redis list",
)
TELEMETRY_REQUEUE_DUPLICATE_RISK = Counter(
    "telemetry_requeue_duplicate_risk_total",
    "telemetry_samples requeue after samples were already committed",
)
TELEMETRY_DEAD_LIST_SIZE = Gauge(
    "telemetry_dead_list_size",
    "Current size of hydro:telemetry:dead Redis list",
)
COMMAND_STATUS_DLQ_SIZE = Gauge(
    "command_status_dlq_size",
    "Current size of command status DLQ",
)
ALERT_DLQ_SIZE = Gauge(
    "alert_dlq_size",
    "Current size of alert DLQ",
)
NODE_LAST_SEEN_AGE_SECONDS = Gauge(
    "node_last_seen_age_seconds",
    "Seconds since node last_seen_at (or fallback heartbeat timestamp)",
    ["node_uid", "zone_id"],
)
TELEMETRY_LAST_AGE_SECONDS = Gauge(
    "telemetry_last_age_seconds",
    "Seconds since newest telemetry_last update in zone",
    ["zone_id"],
)
SOLUTION_TEMP_BREACH_ACTIVE = Gauge(
    "solution_temp_breach_active",
    "1 when zone solution temperature is outside recipe thresholds (alert active)",
    ["zone_id", "direction"],
)

TELEMETRY_QUEUE_AGE = Gauge(
    "telemetry_queue_age_seconds",
    "Age of oldest item in queue in seconds",
)
REALTIME_QUEUE_LEN = Gauge(
    "realtime_queue_len",
    "Current realtime updates queue length",
)
REALTIME_DROPPED_UPDATES = Counter(
    "dropped_updates_count",
    "Total dropped realtime updates",
    ["reason"],
)
REALTIME_FLUSH_LATENCY_MS = Histogram(
    "flush_latency_ms",
    "Realtime telemetry flush latency in milliseconds",
    buckets=[25, 50, 100, 250, 500, 1000, 2000, 5000],
)
TELEMETRY_PROCESSING_DURATION = Histogram(
    "telemetry_processing_duration_seconds",
    "Time to process telemetry batch",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
)
LARAVEL_API_DURATION = Histogram(
    "laravel_api_request_duration_seconds",
    "Laravel API request duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)
REDIS_OPERATION_DURATION = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation duration",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
)
TELEMETRY_DROPPED = Counter(
    "telemetry_dropped_total",
    "Total dropped telemetry messages",
    ["reason"],
)
DATABASE_ERRORS = Counter(
    "database_errors_total",
    "Total database errors",
    ["error_type"],
)
INGEST_AUTH_FAILED = Counter(
    "ingest_auth_failed_total",
    "Total failed authentication attempts for HTTP ingest",
)
INGEST_RATE_LIMITED = Counter(
    "ingest_rate_limited_total",
    "Total rate limited requests for HTTP ingest",
)
INGEST_REQUESTS = Counter(
    "ingest_requests_total",
    "Total HTTP ingest requests",
    ["status"],
)

WS_BROADCAST_TOTAL = Counter(
    "ws_broadcast_total",
    "Total WebSocket broadcasts dispatched",
    ["event_type"],
)

WS_AUTH_TOTAL = Counter(
    "ws_auth_total",
    "Total WebSocket channel auth attempts",
    ["channel_type", "result"],
)


def initialize_counter_series() -> None:
    """Pre-register counter series for known static label combinations.

    Creates child counters with value 0 so Grafana rate()/timeseries queries
    render baseline "0" instead of "No data" before the first real increment.
    Covers only labels with a known static set (explicit string literals in
    handlers). Fully dynamic labels (node_uid, http_<status>, arbitrary
    exception class names) stay lazy.
    """
    for error_type in (
        "invalid_json",
        "missing_hardware_id",
        "parse_error",
        "config_missing",
        "token_missing",
        "exception",
        "unauthorized",
        "timeout",
        "request_error",
        "max_retries_exceeded",
    ):
        NODE_HELLO_ERRORS.labels(error_type=error_type)

    for error_type in (
        "IntegrityError",
        "OperationalError",
        "DataError",
        "ProgrammingError",
        "ForeignKeyViolation",
        "UniqueViolation",
        "DatabaseError",
    ):
        DATABASE_ERRORS.labels(error_type=error_type)

    for stage in ("last", "samples"):
        TELEMETRY_PG_WRITE_FAILED.labels(stage=stage)

    for handler in (
        "heartbeat",
        "status",
        "lwt",
        "diagnostics",
        "error",
        "config_report",
    ):
        MQTT_HANDLER_ERROR.labels(handler=handler)


def register_mqtt_async_handler_error_callback() -> None:
    """Wire history-logger metrics into common MQTT async done_callback."""
    try:
        from common.mqtt import register_async_handler_error_callback
    except ImportError:
        return

    def _on_async_handler_error(handler_name: str, topic: str, exc: BaseException) -> None:
        MQTT_HANDLER_ERROR.labels(handler=handler_name).inc()

    register_async_handler_error_callback(_on_async_handler_error)


register_mqtt_async_handler_error_callback()
