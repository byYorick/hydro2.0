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
if [ "${PROJECT_TO_RUN}" = "smoke" ]; then
  LARAVEL_URL="${LARAVEL_URL:-http://localhost}"
else
  LARAVEL_URL="${LARAVEL_URL:-http://localhost:80}"
fi

# Playwright выполняется внутри контейнера laravel:
# внешний порт 8081 должен быть заменен на внутренний 80.
case "${LARAVEL_URL}" in
  http://localhost:8081|http://127.0.0.1:8081)
    LARAVEL_URL="http://localhost"
    ;;
esac

export LARAVEL_URL
export E2E_AUTH_EMAIL="${E2E_AUTH_EMAIL:-agronomist@example.com}"
export E2E_AUTH_PASSWORD="${E2E_AUTH_PASSWORD:-password}"
export HEADLESS="${HEADLESS:-true}"

echo "Запуск тестов в контейнере ${CONTAINER_NAME}..."
echo "LARAVEL_URL: ${LARAVEL_URL}"
echo "HEADLESS: ${HEADLESS}"
echo "PROJECT: ${PROJECT_TO_RUN}"

# Гарантируем, что Playwright Chromium установлен в контейнере.
ensure_playwright_chromium() {
  echo "Проверка браузера Playwright (chromium)..."

  if docker exec -w "${TEST_DIR}" "${CONTAINER_NAME}" sh -c 'ls ${HOME:-/root}/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell >/dev/null 2>&1'; then
    echo "Chromium уже установлен."
    return 0
  fi

  echo "Chromium не найден, выполняем установку..."
  docker exec -w "${TEST_DIR}" "${CONTAINER_NAME}" sh -c "npx playwright install chromium" || {
    echo "Ошибка установки Playwright Chromium."
    exit 1
  }
}

ensure_playwright_chromium

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
