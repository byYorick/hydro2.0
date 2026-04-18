"""MQTT message handlers — splits mqtt_handlers.py by responsibility.

Модули:
    _shared          — константы, helpers, pending config reports, trace context
    node_hello       — registration handler (ESP32 → Laravel API через common.db)
    heartbeat_status — heartbeat / status / LWT / monitor_offline_nodes
    diagnostics_error — diagnostics + error messages от узлов
    node_event       — node_event → zone_events (IRR snapshot, level switches)
    config_report    — node config acknowledgement + sync_node_channels_from_payload
    command_response — ACK/DONE/ERROR от узла → commands table + Laravel correlation
    time_request     — ответ на hydro/time/request
"""
