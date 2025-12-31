#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

from services.zone_automation_service import ZONE_CHECKS, CHECK_LAT
from infrastructure.command_bus import COMMANDS_SENT, MQTT_PUBLISH_ERRORS
from main import CONFIG_FETCH_SUCCESS, CONFIG_FETCH_ERRORS, LOOP_ERRORS
import random

# Zone checks
for _ in range(100):
    ZONE_CHECKS.inc()
    CHECK_LAT.observe(random.uniform(0.01, 0.5))

# Commands
for _ in range(200):
    zone_id = random.choice([1, 2, 3, 4, 5])
    metric = random.choice(['PH', 'EC', 'TEMPERATURE', 'HUMIDITY'])
    COMMANDS_SENT.labels(zone_id=zone_id, metric=metric).inc()

# Config fetch
for _ in range(50):
    CONFIG_FETCH_SUCCESS.inc()

# Errors
for _ in range(5):
    CONFIG_FETCH_ERRORS.labels(error_type='timeout').inc()

for _ in range(3):
    LOOP_ERRORS.labels(error_type='config_error').inc()

for _ in range(2):
    MQTT_PUBLISH_ERRORS.labels(error_type='connection_error').inc()

print('✓ Данные добавлены: zone_checks=100, commands=200, config_fetch=50, errors=10')
