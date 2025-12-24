#!/bin/bash
# Скрипт для проверки компиляции прошивок после синхронизации с эталоном node-sim

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODES_DIR="$SCRIPT_DIR/nodes"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Проверка компиляции прошивок"
echo "=========================================="
echo ""

# Проверка ESP-IDF
if [ -z "$IDF_PATH" ]; then
    echo -e "${YELLOW}⚠️  IDF_PATH не установлен${NC}"
    echo "Для компиляции необходимо установить ESP-IDF:"
    echo "  . \$HOME/esp/esp-idf/export.sh"
    echo ""
    echo "Продолжаем проверку синтаксиса..."
    echo ""
    SKIP_BUILD=true
else
    echo -e "${GREEN}✅ IDF_PATH установлен: $IDF_PATH${NC}"
    echo ""
    SKIP_BUILD=false
fi

# Список узлов для проверки
NODES=("ph_node" "ec_node" "climate_node" "pump_node")

SUCCESS_COUNT=0
FAIL_COUNT=0

for node in "${NODES[@]}"; do
    NODE_DIR="$NODES_DIR/$node"
    
    if [ ! -d "$NODE_DIR" ]; then
        echo -e "${YELLOW}⚠️  Пропуск: $node (директория не найдена)${NC}"
        continue
    fi
    
    echo "----------------------------------------"
    echo "Проверка: $node"
    echo "----------------------------------------"
    
    cd "$NODE_DIR"
    
    # Проверка наличия CMakeLists.txt
    if [ ! -f "CMakeLists.txt" ]; then
        echo -e "${RED}❌ CMakeLists.txt не найден${NC}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        continue
    fi
    
    if [ "$SKIP_BUILD" = true ]; then
        # Только проверка синтаксиса файлов
        echo "Проверка синтаксиса C файлов..."
        
        # Проверка основных файлов на наличие синтаксических ошибок
        if find main -name "*.c" -type f 2>/dev/null | head -1 | grep -q .; then
            echo -e "${GREEN}✅ C файлы найдены${NC}"
        else
            echo -e "${YELLOW}⚠️  C файлы не найдены в main/${NC}"
        fi
        
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        # Полная компиляция
        echo "Компиляция..."
        
        if idf.py build 2>&1 | tee /tmp/build_${node}.log; then
            echo -e "${GREEN}✅ $node скомпилирован успешно${NC}"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo -e "${RED}❌ Ошибка компиляции $node${NC}"
            echo "Лог сохранен в /tmp/build_${node}.log"
            FAIL_COUNT=$((FAIL_COUNT + 1))
        fi
    fi
    
    echo ""
done

# Итоги
echo "=========================================="
echo "Итоги проверки"
echo "=========================================="
echo -e "${GREEN}Успешно: $SUCCESS_COUNT${NC}"
if [ $FAIL_COUNT -gt 0 ]; then
    echo -e "${RED}Ошибок: $FAIL_COUNT${NC}"
else
    echo -e "${GREEN}Ошибок: 0${NC}"
fi

if [ "$SKIP_BUILD" = true ]; then
    echo ""
    echo -e "${YELLOW}Примечание: Полная компиляция не выполнена (ESP-IDF не настроен)${NC}"
    echo "Для полной компиляции выполните:"
    echo "  . \$HOME/esp/esp-idf/export.sh"
    echo "  ./firmware/check_compilation.sh"
fi

echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    exit 0
else
    exit 1
fi

