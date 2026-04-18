"""Telemetry pipeline helpers. Чистые helpers вынесены; критичные функции
с module-state (``process_telemetry_batch``, ``handle_telemetry``, realtime queue,
caches) остаются в ``telemetry_processing.py`` — ломать test patches невыгодно.

Модули:
    helpers        — pure normalisation / keys / FK helpers (без module-state)
    anomaly_alerts — ``_emit_telemetry_anomaly_alert`` + resolved counterpart
"""
