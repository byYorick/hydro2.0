#!/usr/bin/env python3
"""
Простой тест для проверки формата ответов на команды согласно эталону node-sim.
"""

import json
import sys
import jsonschema
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "command_response.schema.json"


def validate_command_response(message_str):
    """Валидация ответа на команду."""
    try:
        message = json.loads(message_str)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except FileNotFoundError:
        return False, f"Schema not found: {SCHEMA_PATH}"
    
    try:
        jsonschema.validate(instance=message, schema=schema)
        return True, "OK"
    except jsonschema.ValidationError as e:
        return False, f"Schema validation error: {e.message}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_command_response_format.py <json_file_or_stdin>")
        print("  Use '-' for stdin")
        sys.exit(1)
    
    source = sys.argv[1]
    
    if source == "-":
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            is_valid, message = validate_command_response(line)
            if is_valid:
                print(f"✅ Valid: {line[:80]}...")
            else:
                print(f"❌ Invalid: {message}")
                print(f"   Message: {line[:80]}...")
    else:
        with open(source) as f:
            content = f.read()
        
        is_valid, message = validate_command_response(content)
        if is_valid:
            print("✅ Command response is valid")
            sys.exit(0)
        else:
            print(f"❌ Command response is invalid: {message}")
            sys.exit(1)


if __name__ == "__main__":
    main()
