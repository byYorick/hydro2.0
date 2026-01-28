#!/bin/bash
# Скрипт для быстрого запуска приложения

echo "=== Запуск Hydro Android приложения ==="
echo ""

# Проверка подключения
if ! adb devices | grep -q "emulator"; then
    echo "❌ Эмулятор не подключен!"
    echo "Запустите эмулятор в Android Studio"
    exit 1
fi

# Проверка бэкенда
if ! netstat -tlnp 2>/dev/null | grep -q ":8080" && ! ss -tlnp 2>/dev/null | grep -q ":8080"; then
    echo "⚠️  Бэкенд не запущен на порту 8080"
    echo "Запускаю бэкенд..."
    cd /home/georgiy/esp/hydro/hydro2.0/backend/laravel
    php artisan serve --host=0.0.0.0 --port=8080 > /tmp/laravel_serve.log 2>&1 &
    sleep 2
    echo "✅ Бэкенд запущен"
fi

# Установка приложения
echo ""
echo "Установка приложения на эмулятор..."
cd /home/georgiy/esp/hydro/hydro2.0/mobile/app/android
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH

./gradlew installDevDebug --no-daemon 2>&1 | tail -5

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Приложение установлено!"
    echo ""
    echo "=== Готово к использованию ==="
    echo ""
    echo "Учетные данные для входа:"
    echo "  Email: admin@example.com"
    echo "  Пароль: password"
    echo ""
    echo "Для просмотра логов запустите в другом терминале:"
    echo "  adb logcat -s ConfigLoader NetworkModule AuthRepository OkHttp"
    echo ""
    echo "Или для мониторинга ошибок:"
    echo "  adb logcat *:E | grep -E '(ConfigLoader|NetworkModule|AuthRepository|com.hydro.app)'"
else
    echo ""
    echo "❌ Ошибка установки приложения"
    echo "Проверьте логи выше"
    exit 1
fi

