"""Command publish pipeline (history-logger) — splits command_routes by responsibility.

Public modules:
    constants    — command status tuples (final / non-republishable / allowed)
    validation   — request-contract / node_secret / status normalisation
    resolution   — gh_uid / zone_uid / node-zone assignment guards
    alerts       — infra alerts for send-failed and node/zone mismatch
    lifecycle    — DB state machine: ensure QUEUED row + post-publish status check
    publisher    — DRY publish loop с retry, mark_sent, send_status_to_laravel
"""
