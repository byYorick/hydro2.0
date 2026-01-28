# Быстрый старт - Запуск приложения

## ✅ Текущий статус

- ✅ Эмулятор подключен
- ✅ Бэкенд работает на порту 8080
- ✅ API отвечает корректно
- ✅ Конфигурация правильная (http://10.0.2.2:8080)
- ✅ Разрешения INTERNET в манифесте

## 🚀 Запуск приложения

### 1. Убедитесь, что бэкенд запущен

```bash
cd backend/laravel
php artisan serve --host=0.0.0.0 --port=8080
```

Или проверьте, что порт слушается:
```bash
netstat -tlnp | grep :8080
```

### 2. Запустите приложение в Android Studio

- Откройте проект: `mobile/app/android`
- Выберите конфигурацию: **devDebug**
- Запустите на эмуляторе: **Run → Run 'app'**

### 3. Войдите в приложение

**Учетные данные:**
- Email: `admin@example.com`
- Пароль: `password`

## 📊 Мониторинг логов

### В реальном времени:

```bash
adb logcat -s ConfigLoader NetworkModule AuthRepository OkHttp
```

### Только ошибки:

```bash
adb logcat *:E | grep -E "(ConfigLoader|NetworkModule|AuthRepository|com.hydro.app)"
```

### Очистка и мониторинг:

```bash
adb logcat -c
# Попробуйте войти в приложение
adb logcat -d -s ConfigLoader NetworkModule AuthRepository OkHttp *:E
```

## 🔍 Что искать в логах

### Успешная загрузка конфигурации:
```
D/ConfigLoader: Loading config from: configs/env.dev.json
D/ConfigLoader: Loaded config: API_BASE_URL=http://10.0.2.2:8080, ENV=DEV
D/NetworkModule: Base URL configured: http://10.0.2.2:8080
D/NetworkModule: Creating Retrofit with base URL: http://10.0.2.2:8080
```

### Успешный вход:
```
D/AuthRepository: Attempting login for: admin@example.com
D/AuthRepository: Login successful for: admin@example.com
```

### Ошибки подключения:
```
E/AuthRepository: Connection error: Cannot connect to server
E/AuthRepository: HTTP error 401: Invalid credentials
E/AuthRepository: Timeout error: Connection timeout
```

## 🛠️ Тестирование подключения

Запустите скрипт проверки:
```bash
cd /home/georgiy/esp/hydro/hydro2.0
./mobile/app/android/test_connection.sh
```

## 📝 Полезные команды

### Проверка подключения эмулятора:
```bash
adb devices
```

### Проверка доступности API:
```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'
```

### Мониторинг запросов к бэкенду:
```bash
tail -f backend/laravel/storage/logs/laravel.log | grep -E "(POST|GET|api/auth)"
```

## ❗ Решение проблем

### "Cannot connect to server"
- Проверьте, что бэкенд запущен: `php artisan serve --host=0.0.0.0 --port=8080`
- Проверьте, что порт слушается: `netstat -tlnp | grep :8080`

### "Connection timeout"
- Проверьте, что бэкенд отвечает: `curl http://localhost:8080/api/auth/login`
- Перезапустите эмулятор

### "Cannot resolve server address"
- Проверьте конфигурацию: `cat mobile/app/android/app/src/main/assets/configs/env.dev.json`
- Должно быть: `"API_BASE_URL": "http://10.0.2.2:8080"`

### Приложение не запускается
- Пересоберите проект: `./gradlew clean assembleDevDebug`
- Проверьте логи компиляции

