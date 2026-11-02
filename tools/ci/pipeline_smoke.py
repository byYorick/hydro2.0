"""Laravel ScheduleDispatcher -> real AE -> real HL -> MQTT -> simulated device ACK.

Reuses the canonical E95 database fixture and assertions. The CI-only adapters
replace its hand-written intent and SQL DONE with the real scheduler and MQTT.
"""
import asyncio
import json
import hashlib
import hmac
import secrets
import os
from pathlib import Path
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/e2e'))
sys.path.append(str(ROOT / 'backend/services'))
from common.hmac_utils import canonical_json_payload
from runner.e2e_runner import E2ERunner


class PipelineRunner(E2ERunner):
    def _ensure_infra_started(self):
        # The shell driver starts an isolated compose project explicitly.
        pass

    async def _execute_action_step(self, step_type, cfg, raw):
        if step_type == 'ci_laravel_dispatch':
            zone_id = int(self.context['zone_id'])
            self.node_secret = secrets.token_hex(32)
            self.db.execute(
                "UPDATE nodes SET config = jsonb_set(COALESCE(config, '{}'::jsonb), "
                "'{node_secret}', to_jsonb(CAST(:secret AS text))) WHERE id = :node_id",
                {'secret': self.node_secret, 'node_id': int(self.context['node_id'])})
            script = (ROOT / 'tools/ci/dispatch_schedule.php').read_text()
            result = await asyncio.to_thread(subprocess.run,
                ['docker', 'exec', '-i', os.environ['CI_LARAVEL_CONTAINER'],
                 'php', '/dev/stdin', str(zone_id)],
                input=script, text=True, capture_output=True, check=False, timeout=30)
            marker = 'CI_SCHEDULER_RESULT='
            lines = [line for line in result.stdout.splitlines() if line.startswith(marker)]
            if result.returncode != 0 or len(lines) != 1:
                diagnostic = (result.stdout + result.stderr)[-4000:]
                for key in ('PY_API_TOKEN', 'CI_PIPELINE_API_TOKEN'):
                    diagnostic = diagnostic.replace(os.environ.get(key) or 'not-a-token', '[redacted]')
                raise RuntimeError('Laravel scheduler driver failed: ' + diagnostic)
            self.context.update(json.loads(lines[0].removeprefix(marker)))
            return
        if step_type == 'ci_device_done':
            row = self.context['ae_command_row'][0]
            message = await self.mqtt.wait_message(timeout=30, condition=lambda msg:
                msg['topic'].endswith('/command') and
                isinstance(msg['payload'], dict) and msg['payload'].get('cmd_id') == row['cmd_id'])
            if message is None:
                raise AssertionError('HL accepted the command but it never reached the broker')
            signed = dict(message['payload'])
            signature = signed.pop('sig', '')
            expected = hmac.new(self.node_secret.encode(),
                                canonical_json_payload(signed).encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise AssertionError('Device rejected an invalid command HMAC')
            self.mqtt.publish_json(message['topic'].removesuffix('/command') + '/command_response',
                {'cmd_id': row['cmd_id'], 'status': 'DONE', 'ts': int(time.time())})
            return
        return await super()._execute_action_step(step_type, cfg, raw)


async def main():
    scenario = yaml.safe_load((ROOT / 'tests/e2e/scenarios/ae3lite/E95_ae3_start_cycle_done_completed.yaml').read_text())
    actions = []
    for action in scenario['actions']:
        name = action['step']
        if name == 'insert_scheduler_like_intent':
            actions.append({'step': 'dispatch_real_laravel_schedule', 'type': 'ci_laravel_dispatch'})
        elif name == 'mark_legacy_command_done':
            actions.append({'step': 'receive_command_and_ack_over_mqtt', 'type': 'ci_device_done'})
        elif name not in ('start_cycle_http', 'set_task_id'):
            actions.append(action)
    scenario['actions'] = actions
    # The PHP driver validates the real dispatch result; no synthetic HTTP response.
    scenario['assertions'] = [a for a in scenario['assertions']
                              if a['name'] not in ('start_cycle_http_200', 'start_cycle_response_active')]
    runner = PipelineRunner({'api_token': os.environ['CI_PIPELINE_API_TOKEN']})
    try:
        await runner.setup()
        now_s = int(time.time())
        runner.context.update(TIMESTAMP_S=now_s, TIMESTAMP_MS=now_s * 1000)
        if not runner.mqtt.connected:
            raise AssertionError('MQTT must be connected for pipeline smoke')
        runner.mqtt.subscribe('hydro/#')
        if not await runner._run_actions_scenario(scenario, 'ci_real_scheduler_pipeline'):
            raise AssertionError('Pipeline scenario failed')
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
