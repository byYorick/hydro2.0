#!/bin/bash
# Скрипт для проверки production build после исправления vite.config.js
# Проверяет отсутствие sourcemap и console.* в production bundle

set -e

BUILD_DIR="public/build"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Проверка production build"
echo "=========================================="
echo ""

# Очистка предыдущей сборки
echo "1. Очистка предыдущей сборки..."
rm -rf "$BUILD_DIR" || true
echo "   ✓ Очищено"
echo ""

# Запуск production build
echo "2. Запуск production build (mode=production)..."
NODE_ENV=production npm run build -- --mode production
echo "   ✓ Сборка завершена"
echo ""

# Проверка наличия директории build
if [ ! -d "$BUILD_DIR" ]; then
    echo "❌ ОШИБКА: Директория $BUILD_DIR не найдена!"
    exit 1
fi

echo "3. Проверка отсутствия sourcemap файлов..."
SOURCEMAP_COUNT=$(find "$BUILD_DIR" -name "*.map" -type f 2>/dev/null | wc -l)
if [ "$SOURCEMAP_COUNT" -eq 0 ]; then
    echo "   ✓ Sourcemap файлы отсутствуют (ожидалось)"
else
    echo "   ❌ НАЙДЕНО $SOURCEMAP_COUNT sourcemap файлов:"
    find "$BUILD_DIR" -name "*.map" -type f
    exit 1
fi
echo ""

echo "4. Проверка отсутствия inline sourcemap в JS файлах..."
INLINE_SOURCEMAP_COUNT=$(grep -r "sourceMappingURL" "$BUILD_DIR" --include="*.js" 2>/dev/null | wc -l)
if [ "$INLINE_SOURCEMAP_COUNT" -eq 0 ]; then
    echo "   ✓ Inline sourcemap отсутствуют в JS файлах (ожидалось)"
else
    echo "   ❌ НАЙДЕНО $INLINE_SOURCEMAP_COUNT упоминаний sourceMappingURL:"
    grep -r "sourceMappingURL" "$BUILD_DIR" --include="*.js" | head -5
    exit 1
fi
echo ""

echo "5. Проверка отсутствия console.* в production bundle..."
CONSOLE_COUNT=$(grep -r "console\." "$BUILD_DIR" --include="*.js" 2>/dev/null | wc -l)
if [ "$CONSOLE_COUNT" -eq 0 ]; then
    echo "   ✓ console.* отсутствуют в bundle (ожидалось)"
else
    echo "   ⚠️  НАЙДЕНО $CONSOLE_COUNT упоминаний console.* (возможно в vendor коде):"
    grep -r "console\." "$BUILD_DIR" --include="*.js" | head -10
    echo "   Примечание: некоторые vendor библиотеки могут содержать console.*"
fi
echo ""

echo "6. Проверка отсутствия debugger в production bundle..."
DEBUGGER_COUNT=$(grep -r "debugger" "$BUILD_DIR" --include="*.js" 2>/dev/null | wc -l)
if [ "$DEBUGGER_COUNT" -eq 0 ]; then
    echo "   ✓ debugger отсутствует в bundle (ожидалось)"
else
    echo "   ❌ НАЙДЕНО $DEBUGGER_COUNT упоминаний debugger:"
    grep -r "debugger" "$BUILD_DIR" --include="*.js" | head -5
    exit 1
fi
echo ""

echo "7. Информация о собранных файлах:"
echo "   JS файлы:"
find "$BUILD_DIR" -name "*.js" -type f -exec ls -lh {} \; | awk '{print "     " $9 " (" $5 ")"}'
echo ""
echo "   CSS файлы:"
find "$BUILD_DIR" -name "*.css" -type f -exec ls -lh {} \; | awk '{print "     " $9 " (" $5 ")"}'
echo ""

echo "=========================================="
echo "✓ Все проверки пройдены успешно!"
echo "=========================================="

