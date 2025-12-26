#!/bin/bash
set -e

# Скрипт для запуска Playwright тестов в контейнере Laravel
# Использование: ./run-tests-in-container.sh [project]
# project: smoke (по умолчанию), chromium, firefox, etc.

CONTAINER_NAME="e2e-laravel-1"
TEST_DIR="/app/tests/e2e/browser"

# Проект для запуска (smoke по умолчанию)
PROJECT_TO_RUN="${1:-smoke}"

# Переменные окружения
export LARAVEL_URL="${LARAVEL_URL:-http://localhost:80}"
export E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL:-admin@hydro.local}"
export E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD:-password}"
export HEADLESS="${HEADLESS:-true}"

echo "Запуск тестов в контейнере ${CONTAINER_NAME}..."
echo "LARAVEL_URL: ${LARAVEL_URL}"
echo "HEADLESS: ${HEADLESS}"
echo "PROJECT: ${PROJECT_TO_RUN}"

# Копируем файлы тестов в контейнер (если нужно)
# docker cp tests/e2e/browser ${CONTAINER_NAME}:/app/tests/e2e/

# Запускаем setup для создания storageState (только если не smoke)
if [ "${PROJECT_TO_RUN}" != "smoke" ]; then
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
fi

# Запускаем тесты выбранного проекта
echo "Запуск тестов проекта '${PROJECT_TO_RUN}'..."
    docker exec -e LARAVEL_URL="${LARAVEL_URL}" \
      -e E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL}" \
      -e E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD}" \
      -e HEADLESS="${HEADLESS}" \
      -e SKIP_WEBSERVER=true \
      -w "${TEST_DIR}" \
      "${CONTAINER_NAME}" \
      sh -c "npx playwright test --config=playwright.config.ts --project=${PROJECT_TO_RUN} --reporter=list"

echo "Тесты завершены."


