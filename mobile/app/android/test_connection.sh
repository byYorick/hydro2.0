#!/bin/bash
# Скрипт для тестирования подключения приложения к бэкенду

echo "=== Тест подключения Android приложения ==="
echo ""

# Проверка эмулятора
echo "1. Проверка подключения эмулятора..."
if adb devices | grep -q "emulator"; then
    echo "   ✅ Эмулятор подключен"
    DEVICE=$(adb devices | grep emulator | awk '{print $1}')
    echo "   Устройство: $DEVICE"
else
    echo "   ❌ Эмулятор не подключен"
    exit 1
fi

# Проверка бэкенда
echo ""
echo "2. Проверка бэкенда..."
if netstat -tlnp 2>/dev/null | grep -q ":8080" || ss -tlnp 2>/dev/null | grep -q ":8080"; then
    echo "   ✅ Порт 8080 слушается"
else
    echo "   ❌ Порт 8080 не слушается"
    echo "   Запустите: cd backend/laravel && php artisan serve --host=0.0.0.0 --port=8080"
    exit 1
fi

# Проверка API
echo ""
echo "3. Проверка API endpoint..."
RESPONSE=$(curl -s -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}')

if echo "$RESPONSE" | grep -q '"status":"ok"'; then
    echo "   ✅ API отвечает корректно"
else
    echo "   ❌ API не отвечает или возвращает ошибку"
    echo "   Ответ: $RESPONSE"
    exit 1
fi

# Проверка конфигурации
echo ""
echo "4. Проверка конфигурации приложения..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/app/src/main/assets/configs/env.dev.json"
if [ -f "$CONFIG_FILE" ]; then
    CONFIG=$(cat "$CONFIG_FILE")
    if echo "$CONFIG" | grep -q "10.0.2.2:8080"; then
        echo "   ✅ Конфигурация правильная"
    else
        echo "   ❌ Конфигурация неправильная"
        echo "   Текущая конфигурация:"
        echo "$CONFIG"
        exit 1
    fi
else
    echo "   ⚠️  Файл конфигурации не найден: $CONFIG_FILE"
    echo "   Проверьте путь к файлу"
fi

# Мониторинг логов
echo ""
echo "5. Мониторинг логов приложения..."
echo "   Очистка старых логов..."
adb logcat -c > /dev/null 2>&1

echo ""
echo "=== Готово! ==="
echo ""
echo "Теперь:"
echo "1. Откройте приложение в эмуляторе"
echo "2. Попробуйте войти (admin@example.com / password)"
echo "3. В другом терминале запустите:"
echo "   adb logcat -s ConfigLoader NetworkModule AuthRepository OkHttp *:E"
echo ""
echo "Или для мониторинга в реальном времени:"
echo "   adb logcat -s ConfigLoader NetworkModule AuthRepository OkHttp"

