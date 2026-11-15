"""Generate production ACL from [{username, node_uid, hardware_id}] inventory.

Passwords belong in the separately managed Mosquitto password file. No wildcard
patterns are emitted: authorization is bound to authenticated usernames.
"""
import argparse
import json
import re
from pathlib import Path


def generate_acl(nodes: list[dict]) -> str:
    if not isinstance(nodes, list) or any(not isinstance(node, dict) or not {'username', 'node_uid', 'hardware_id'} <= node.keys() for node in nodes):
        raise ValueError('Inventory must be a list of complete node identities')
    lines = ['user history_logger', 'topic readwrite hydro/#', '', 'user mqtt_bridge']
    for suffix in ['status', 'lwt', 'heartbeat', '+/telemetry']:
        lines.append(f'topic read hydro/+/+/+/{suffix}')
    seen = {'history_logger', 'mqtt_bridge', 'esp32_node', 'python_service', 'automation_engine'}
    node_ids, hardware_ids = set(), set()
    for node in nodes:
        username, uid, hardware = (node[k] for k in ['username', 'node_uid', 'hardware_id'])
        for value in [username, uid, hardware]:
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
                raise ValueError('Invalid identity segment')
        if username in seen or uid in node_ids or hardware in hardware_ids:
            raise ValueError('Duplicate or reserved identity')
        seen.add(username); node_ids.add(uid); hardware_ids.add(hardware)
        lines += ['', f'user {username}', 'topic write hydro/node_hello',
                  'topic write hydro/time/request', 'topic read hydro/time/response']
        for address in [f'+/+/{uid}', f'gh-temp/zn-temp/{hardware}']:
            for suffix in ['config', '+/command']:
                lines.append(f'topic read hydro/{address}/{suffix}')
            for suffix in ['+/telemetry', 'status', 'heartbeat', 'lwt', 'diagnostics',
                           'error', 'config_report', 'node_hello', '+/command_response', '+/event']:
                lines.append(f'topic write hydro/{address}/{suffix}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(generate_acl(json.loads(args.inventory.read_text())))
