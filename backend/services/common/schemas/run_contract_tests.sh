#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p common/schemas/test-results
# Chaos runs separately with its declared dependencies and infrastructure.
pytest common/schemas/test_contracts.py common/schemas/test_protocol_contracts.py \
  common/schemas/test_websocket_events.py -v --tb=short \
  --junitxml=common/schemas/test-results.xml
