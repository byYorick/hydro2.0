#!/bin/bash
set -e

# Скрипт для запуска Playwright тестов в контейнере Laravel

CONTAINER_NAME="e2e-laravel-1"
TEST_DIR="/app/tests/e2e/browser"

# Переменные окружения
export LARAVEL_URL="${LARAVEL_URL:-http://localhost:80}"
export E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL:-admin@hydro.local}"
export E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD:-password}"
export HEADLESS="${HEADLESS:-true}"

echo "Запуск тестов в контейнере ${CONTAINER_NAME}..."
echo "LARAVEL_URL: ${LARAVEL_URL}"
echo "HEADLESS: ${HEADLESS}"

# Копируем файлы тестов в контейнер (если нужно)
# docker cp tests/e2e/browser ${CONTAINER_NAME}:/app/tests/e2e/

# Запускаем setup для создания storageState
echo "Запуск setup для авторизации..."
docker exec -e LARAVEL_URL="${LARAVEL_URL}" \
  -e E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL}" \
  -e E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD}" \
  -e HEADLESS="${HEADLESS}" \
  -w "${TEST_DIR}" \
  "${CONTAINER_NAME}" \
  sh -c "npx playwright test --config=playwright.config.ts --project=setup" || {
  echo "Ошибка при запуске setup. Проверьте, что контейнер запущен и Laravel доступен."
  exit 1
}

# Запускаем основные тесты
echo "Запуск основных тестов..."
docker exec -e LARAVEL_URL="${LARAVEL_URL}" \
  -e E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL}" \
  -e E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD}" \
  -e HEADLESS="${HEADLESS}" \
  -w "${TEST_DIR}" \
  "${CONTAINER_NAME}" \
  sh -c "npx playwright test --config=playwright.config.ts --project=chromium --reporter=list"

echo "Тесты завершены."


