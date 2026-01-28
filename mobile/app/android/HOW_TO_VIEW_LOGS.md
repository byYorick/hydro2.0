# Как просмотреть логи Android приложения

## Способ 1: Android Studio Logcat (Рекомендуется)

1. **Откройте Android Studio**
2. **Запустите приложение** на эмуляторе или устройстве
3. **Откройте вкладку Logcat** (внизу экрана)
4. **Настройте фильтры:**

### Фильтры для просмотра логов приложения:

```
tag:ConfigLoader OR tag:NetworkModule OR tag:AuthRepository
```

Или для всех логов приложения:

```
package:com.hydro.app.dev
```

### Фильтры для ошибок:

```
level:ERROR OR level:WARN
```

### Фильтры для сетевых запросов:

```
OkHttp
```

## Способ 2: ADB logcat (через терминал)

Если ADB установлен:

```bash
# Установка ADB (если не установлен)
sudo apt install adb

# Просмотр всех логов приложения
adb logcat -s ConfigLoader NetworkModule AuthRepository

# Просмотр только ошибок
adb logcat *:E

# Просмотр логов с фильтром по тегам
adb logcat -s ConfigLoader:D NetworkModule:D AuthRepository:D *:E

# Сохранение логов в файл
adb logcat > android_logs.txt
```

## Способ 3: Через Android Studio Device File Explorer

1. **View → Tool Windows → Device File Explorer**
2. Перейдите в `/data/data/com.hydro.app.dev/logs/` (если логи сохраняются там)

## Что искать в логах

### При проблемах с сетью:

1. **ConfigLoader** - должен показать:
   ```
   D/ConfigLoader: Loading config from: configs/env.dev.json
   D/ConfigLoader: Loaded config: API_BASE_URL=http://10.0.2.2:8080, ENV=DEV
   ```

2. **NetworkModule** - должен показать:
   ```
   D/NetworkModule: Base URL configured: http://10.0.2.2:8080
   D/NetworkModule: Creating Retrofit with base URL: http://10.0.2.2:8080
   ```

3. **AuthRepository** - должен показать:
   ```
   D/AuthRepository: Attempting login for: admin@example.com
   D/AuthRepository: Login successful for: admin@example.com
   ```

### При ошибках входа:

Ищите строки с:
- `E/AuthRepository` - ошибки авторизации
- `HTTP error` - ошибки HTTP запросов
- `Connection error` - проблемы с подключением
- `Timeout error` - таймауты

### Примеры ошибок:

```
E/AuthRepository: Connection error: Cannot connect to server
E/AuthRepository: HTTP error 401: Invalid credentials
E/AuthRepository: Timeout error: Connection timeout
```

## Способ 4: Логи бэкенда Laravel

Проверьте логи бэкенда на наличие запросов от приложения:

```bash
cd backend/laravel
tail -f storage/logs/laravel.log | grep -E "(POST|GET|api/auth)"
```

Или просмотрите последние записи:

```bash
tail -100 storage/logs/laravel.log
```

## Полезные команды ADB

```bash
# Список подключенных устройств
adb devices

# Очистка логов
adb logcat -c

# Просмотр логов в реальном времени
adb logcat -s ConfigLoader NetworkModule AuthRepository

# Просмотр только ошибок и предупреждений
adb logcat *:E *:W

# Экспорт логов
adb logcat -d > logs.txt
```

## Настройка уровня логирования

В коде приложения логи настроены следующим образом:

- **DEBUG** - детальная информация (ConfigLoader, NetworkModule)
- **ERROR** - только ошибки (AuthRepository при ошибках)

В production сборке логирование отключено для безопасности.

