"""Prepare an offline, private MQTT migration bundle; never connects to devices.

Service credentials JSON: {"history_logger": "...", "mqtt_bridge": "..."}.
Node inventory format is shared with generate_node_acl.py. Existing node secrets
are retained from --previous; rotation must name individual node_uids explicitly.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

from generate_node_acl import generate_acl


def read_private_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Secret input must be a regular private file (mode 0600)')
    return json.loads(path.read_text())


def password(value):
    if not isinstance(value, str) or not 32 <= len(value.encode()) <= 127 or any(ord(c) < 32 or ord(c) == 127 or c == ':' for c in value):
        raise ValueError('Credentials must be 32..127 bytes without control characters or colons')
    return value


def prepare(inventory, services, output: Path, *, previous=None, rotate=(), image='eclipse-mosquitto:2.0.22'):
    acl = generate_acl(inventory)  # Validate identities before creating files.
    if not isinstance(services, dict) or set(services) != {'history_logger', 'mqtt_bridge'}:
        raise ValueError('Exactly history_logger and mqtt_bridge service credentials required')
    services = {key: password(value) for key, value in services.items()}
    previous = previous or {}
    if not isinstance(previous, dict) or any(not isinstance(value, dict) for value in previous.values()):
        raise ValueError('Previous credential bundle must be a mapping')
    rotate = set(rotate)
    if rotate - {node['node_uid'] for node in inventory}:
        raise ValueError('Rotation refers to an unknown node')
    if output.exists():
        raise ValueError('Output already exists; choose a new versioned directory')
    nodes = {}
    for node in inventory:
        uid = node['node_uid']
        old = previous.get(uid)
        if old and uid not in rotate:
            if old.get('username') != node['username'] or old.get('hardware_id') != node['hardware_id']:
                raise ValueError('Identity change requires explicit node rotation')
            value = password(old['password'])
        else:
            value = secrets.token_urlsafe(32)
        nodes[uid] = dict(node, password=value)
    all_passwords = list(services.values()) + [node['password'] for node in nodes.values()]
    if len(set(all_passwords)) != len(all_passwords):
        raise ValueError('Every MQTT identity must have a distinct password')
    output = output.absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.mqtt-bundle-', dir=output.parent))
    def write(name, content, mode=0o600):
        path = staging / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
    try:
        write('.gitignore', '*\n')
        write('production.acl', acl, 0o644)
        write('node_credentials.json', json.dumps(nodes, indent=2)+'\n')
        write('node_passwords.json', json.dumps({uid: node['password'] for uid, node in nodes.items()}, indent=2)+'\n')
        entries = services | {node['username']: node['password'] for node in nodes.values()}
        write('passwords', ''.join(f'{user}:{value}\n' for user, value in entries.items()))
        # Hash in-place without passwords appearing in argv or subprocess output.
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
            '-v', f'{staging}:/bundle', '--entrypoint', 'mosquitto_passwd', image,
            '-U', '/bundle/passwords'], capture_output=True)
        if result.returncode:
            raise RuntimeError('Unable to hash MQTT password file')
        (staging / 'passwords').chmod(0o600)
        write('manifest.json', json.dumps({'format_version': 1, 'node_count': len(nodes),
            'rotated_nodes': sorted(rotate), 'removed_nodes': sorted(set(previous)-set(nodes))}, indent=2)+'\n')
        os.rename(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return len(nodes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('service_credentials', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--previous', type=Path, help='Previous bundle node_credentials.json')
    parser.add_argument('--rotate-node', action='append', default=[])
    args = parser.parse_args()
    try:
        count = prepare(json.loads(args.inventory.read_text()), read_private_json(args.service_credentials), args.output,
            previous=read_private_json(args.previous) if args.previous else None, rotate=args.rotate_node)
    except (ValueError, KeyError, OSError, RuntimeError, TypeError):
        parser.exit(1, 'MQTT bundle preparation failed; verify identities, private input files and Docker availability.\n')
    print(f'Prepared MQTT bundle for {count} nodes. Secrets were written to private files; no devices changed.')


if __name__ == '__main__':
    main()
