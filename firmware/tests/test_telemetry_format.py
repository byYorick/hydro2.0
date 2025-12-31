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
        
        # Дополнительные проверки
        errors = []
        
        # Проверка обязательных полей
        required_fields = ["metric_type", "value", "ts"]
        for field in required_fields:
            if field not in message:
                errors.append(f"Missing required field: {field}")
        
        # Проверка запрещенных полей
        forbidden_fields = ["node_id", "channel"]
        for field in forbidden_fields:
            if field in message:
                errors.append(f"Forbidden field present: {field}")
        
        # Проверка формата metric_type (UPPERCASE)
        if "metric_type" in message:
            mt = message["metric_type"]
            if mt != mt.upper():
                errors.append(f"metric_type must be UPPERCASE, got: {mt}")
        
        # Проверка типа ts (должен быть int, не float)
        if "ts" in message:
            ts = message["ts"]
            if isinstance(ts, float):
                errors.append(f"ts must be integer, got float: {ts}")
        
        if errors:
            return False, "; ".join(errors)
        
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
