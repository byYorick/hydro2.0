#!/bin/bash
# Скрипт для исправления прав доступа на файлы test-results и reports
# Эти файлы создаются Docker контейнерами от имени root

set -e

echo "Исправление прав доступа на файлы тестов..."

# Изменяем владельца файлов на текущего пользователя
sudo chown -R $(whoami):$(whoami) backend/laravel/test-results/ 2>/dev/null || true
sudo chown -R $(whoami):$(whoami) backend/laravel/tests/e2e/reports/ 2>/dev/null || true

# Удаляем проблемные файлы, если они все еще существуют
sudo rm -f backend/laravel/test-results/.last-run.json 2>/dev/null || true
sudo rm -f backend/laravel/tests/e2e/reports/playwright/index.html 2>/dev/null || true
sudo rm -f backend/laravel/tests/e2e/reports/playwright/junit.xml 2>/dev/null || true

echo "Права доступа исправлены. Теперь можно выполнить: git pull --tags origin ref"

