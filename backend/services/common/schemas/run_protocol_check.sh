#!/bin/bash
# Скрипт для запуска контрактных тестов протокола
# Используется в CI для проверки совместимости payload'ов

set -e

echo "🔍 Running protocol contract tests..."

# Переходим в директорию с тестами
cd "$(dirname "$0")/../.."

# Проверяем наличие зависимостей
if ! python3 -c "import jsonschema" 2>/dev/null; then
    echo "❌ jsonschema not installed. Installing..."
    pip install jsonschema
fi

if ! python3 -c "import pytest" 2>/dev/null; then
    echo "❌ pytest not installed. Installing..."
    pip install pytest
fi

# Устанавливаем PYTHONPATH для импорта модулей
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/history-logger:$(pwd)/common"

# Запускаем контрактные тесты
echo "📋 Running protocol contract tests..."
python3 -m pytest \
    services/common/schemas/test_protocol_contracts.py \
    -v \
    --tb=short \
    --color=yes \
    -W ignore::DeprecationWarning

if [ $? -eq 0 ]; then
    echo "✅ Protocol contract tests passed!"
    exit 0
else
    echo "❌ Protocol contract tests failed!"
    exit 1
fi

