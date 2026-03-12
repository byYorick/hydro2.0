#!/usr/bin/env python3
"""
Простой тест для проверки формата телеметрии согласно эталону node-sim.

Использование:
    python3 firmware/tests/test_telemetry_format.py <json_file>
    
Или для проверки через MQTT:
    mosquitto_sub -t 'hydro/+/+/+/+/telemetry' | python3 firmware/tests/test_telemetry_format.py -
"""

import json
import sys
import jsonschema
from pathlib import Path

# Путь к схеме
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "telemetry.schema.json"


def validate_telemetry(message_str):
    """Валидация сообщения телеметрии."""
    try:
        message = json.loads(message_str)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    
    # Загрузить схему
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except FileNotFoundError:
        return False, f"Schema not found: {SCHEMA_PATH}"
    
    # Валидация
    try:
        jsonschema.validate(instance=message, schema=schema)
        return True, "OK"
    except jsonschema.ValidationError as e:
        return False, f"Schema validation error: {e.message}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_telemetry_format.py <json_file_or_stdin>")
        print("  Use '-' for stdin (e.g., from MQTT)")
        sys.exit(1)
    
    source = sys.argv[1]
    
    if source == "-":
        # Читаем из stdin
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            
            is_valid, message = validate_telemetry(line)
            if is_valid:
                print(f"✅ Valid: {line[:80]}...")
            else:
                print(f"❌ Invalid: {message}")
                print(f"   Message: {line[:80]}...")
    else:
        # Читаем из файла
        with open(source) as f:
            content = f.read()
        
        is_valid, message = validate_telemetry(content)
        if is_valid:
            print("✅ Telemetry message is valid")
            sys.exit(0)
        else:
            print(f"❌ Telemetry message is invalid: {message}")
            sys.exit(1)


if __name__ == "__main__":
    main()
