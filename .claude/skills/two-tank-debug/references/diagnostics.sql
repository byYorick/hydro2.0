\set ON_ERROR_STOP on
-- Provide --set=zone_id=<integer>. Run only against the selected environment.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';

SELECT w.zone_id, w.workflow_phase, w.started_at, w.updated_at
FROM zone_workflow_state w
WHERE w.zone_id = :'zone_id'::bigint;

SELECT t.id, t.task_type, t.status, t.current_stage, t.workflow_phase,
       t.claimed_by, t.stage_deadline_at, t.overall_deadline_at,
       t.error_code, t.updated_at
FROM ae_tasks t
WHERE t.zone_id = :'zone_id'::bigint
ORDER BY t.created_at DESC
LIMIT 10;

SELECT l.owner, l.leased_until, l.claim_generation, l.updated_at
FROM ae_zone_leases l
WHERE l.zone_id = :'zone_id'::bigint;

SELECT a.task_id, a.external_id, a.stage_name, a.planner_step,
       a.publish_status, a.terminal_status, a.updated_at
FROM ae_commands a
JOIN ae_tasks t ON t.id = a.task_id
WHERE t.zone_id = :'zone_id'::bigint
ORDER BY a.created_at DESC
LIMIT 20;

SELECT c.id, c.cmd_id, c.cmd, c.channel, c.status,
       n.uid AS node_uid, c.error_code, c.created_at, c.updated_at
FROM commands c
LEFT JOIN nodes n ON n.id = c.node_id
WHERE c.zone_id = :'zone_id'::bigint
ORDER BY c.created_at DESC
LIMIT 20;

SELECT s.id AS sensor_id, s.type, s.label,
       tl.last_value, tl.last_ts, tl.last_quality, tl.updated_at
FROM sensors s
LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
WHERE s.zone_id = :'zone_id'::bigint
ORDER BY s.id;

SELECT n.uid, n.type, n.status, n.lifecycle_state, n.last_seen_at
FROM nodes n
WHERE n.zone_id = :'zone_id'::bigint
ORDER BY n.uid;

SELECT e.id, e.type, e.created_at
FROM zone_events e
WHERE e.zone_id = :'zone_id'::bigint
ORDER BY e.created_at DESC
LIMIT 30;

ROLLBACK;
