#!/bin/bash
# Скрипт для запуска монитора ph_node на /dev/ttyUSB0

set -e

# Переходим в директорию проекта
cd "$(dirname "$0")"

# Активируем ESP-IDF окружение
. $HOME/esp/esp-idf/export.sh

# Проверяем наличие TTY
if [ ! -c /dev/ttyUSB0 ]; then
    echo "Ошибка: /dev/ttyUSB0 не найден"
    exit 1
fi

# Запускаем монитор
# idf.py monitor требует интерактивный терминал
# Используем script для создания псевдо-TTY, если запущено не из интерактивного терминала
if [ -t 0 ] && [ -t 1 ]; then
    # Если запущено из интерактивного терминала, запускаем напрямую
    idf.py -p /dev/ttyUSB0 monitor
else
    # Если запущено не из интерактивного терминала, используем script для создания псевдо-TTY
    # Используем временный файл для вывода script
    TMP_LOG=$(mktemp)
    trap "rm -f $TMP_LOG" EXIT
    script -f -c "idf.py -p /dev/ttyUSB0 monitor" "$TMP_LOG" &
    SCRIPT_PID=$!
    # Ждем завершения
    wait $SCRIPT_PID
fi

