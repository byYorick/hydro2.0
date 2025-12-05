#!/bin/bash
# Скрипт для запуска ESP-IDF flash с правильными правами доступа к последовательному порту

# Проверяем, в группе ли пользователь dialout
if groups | grep -q dialout; then
    echo "Пользователь уже в группе dialout, запускаем обычную команду..."
    idf.py flash "$@"
else
    echo "Пользователь не в группе dialout, используем sg dialout..."
    sg dialout -c "idf.py flash $*"
fi

