#!/bin/bash
# Скрипт для компиляции всех нод

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODES_DIR="$SCRIPT_DIR/nodes"
IDF_EXPORT="/home/georgiy/esp/esp-idf/export.sh"

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "Компиляция всех нод"
echo "=========================================="
echo ""

# Загрузка ESP-IDF окружения
if [ -f "$IDF_EXPORT" ]; then
    source "$IDF_EXPORT" >/dev/null 2>&1
    echo -e "${GREEN}✅ ESP-IDF окружение загружено${NC}"
    echo "   Версия: $(idf.py --version 2>&1 | head -1)"
    echo ""
else
    echo -e "${RED}❌ ESP-IDF не найден: $IDF_EXPORT${NC}"
    exit 1
fi

# Список нод для компиляции
NODES=("ph_node" "ec_node" "climate_node" "pump_node" "relay_node" "light_node")

SUCCESS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

for node in "${NODES[@]}"; do
    NODE_DIR="$NODES_DIR/$node"
    
    if [ ! -d "$NODE_DIR" ]; then
        echo -e "${YELLOW}⚠️  Пропуск: $node (директория не найдена)${NC}"
        SKIP_COUNT=$((SKIP_COUNT + 1))
        echo ""
        continue
    fi
    
    echo "----------------------------------------"
    echo "Компиляция: $node"
    echo "----------------------------------------"
    
    cd "$NODE_DIR"
    
    # Проверка наличия CMakeLists.txt
    if [ ! -f "CMakeLists.txt" ]; then
        echo -e "${RED}❌ CMakeLists.txt не найден${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo ""
        continue
    fi
    
    # Очистка предыдущей сборки (опционально)
    # rm -rf build
    
    # Компиляция
    echo "Запуск компиляции..."
    if idf.py build 2>&1 | tee "/tmp/build_${node}.log" | tail -30; then
        echo -e "${GREEN}✅ $node скомпилирован успешно${NC}"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        
        # Проверка наличия бинарника
        if [ -f "build/${node}.bin" ]; then
            SIZE=$(stat -c%s "build/${node}.bin" 2>/dev/null || echo "0")
            echo "   Размер бинарника: $((SIZE / 1024)) KB"
        fi
    else
        BUILD_EXIT_CODE=${PIPESTATUS[0]}
        if [ $BUILD_EXIT_CODE -ne 0 ]; then
            echo -e "${RED}❌ Ошибка компиляции $node${NC}"
            echo "   Лог сохранен в /tmp/build_${node}.log"
            
            # Проверяем тип ошибки
            if grep -q "overflowed\|does not fit" "/tmp/build_${node}.log"; then
                echo -e "${YELLOW}   Причина: Переполнение памяти (DRAM/IRAM)${NC}"
            elif grep -q "error:" "/tmp/build_${node}.log"; then
                echo -e "${RED}   Причина: Ошибка компиляции${NC}"
            fi
            
            FAIL_COUNT=$((FAIL_COUNT + 1))
        else
            echo -e "${GREEN}✅ $node скомпилирован успешно${NC}"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        fi
    fi
    
    echo ""
done

# Итоги
echo "=========================================="
echo "Итоги компиляции"
echo "=========================================="
echo -e "${GREEN}Успешно: $SUCCESS_COUNT${NC}"
if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${RED}Ошибок: $FAIL_COUNT${NC}"
else
    echo -e "${GREEN}Ошибок: 0${NC}"
fi
if [ $SKIP_COUNT -gt 0 ]; then
    echo -e "${YELLOW}Пропущено: $SKIP_COUNT${NC}"
fi
echo ""

if [ $FAIL_COUNT -eq 0 ] && [ $SUCCESS_COUNT -gt 0 ]; then
    echo -e "${GREEN}✅ Все ноды скомпилированы успешно!${NC}"
    exit 0
elif [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Некоторые ноды не скомпилированы${NC}"
    echo "Проверьте логи в /tmp/build_*.log"
    exit 1
else
    echo -e "${YELLOW}⚠️  Нет нод для компиляции${NC}"
    exit 1
fi

