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

TELEMETRY_QUEUE_AGE = Gauge(
    "telemetry_queue_age_seconds",
    "Age of oldest item in queue in seconds",
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
