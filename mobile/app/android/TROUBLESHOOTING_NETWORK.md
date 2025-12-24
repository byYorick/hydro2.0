# Устранение проблем с сетью

## Диагностика ошибок сети

### 1. Проверка бэкенда

Убедитесь, что бэкенд запущен и доступен:

```bash
# Проверка, что сервер запущен
curl http://localhost:8080/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'

# Должен вернуть JSON с токеном
```

### 2. Проверка конфигурации

В Android Studio Logcat найдите логи с тегами:
- `ConfigLoader` - покажет загруженный URL
- `NetworkModule` - покажет базовый URL для Retrofit
- `AuthRepository` - покажет детали попытки входа

**Ожидаемый URL для эмулятора:** `http://10.0.2.2:8080`

### 3. Типичные ошибки и решения

#### "Cannot connect to server"
- **Причина:** Бэкенд не запущен или недоступен
- **Решение:** 
  ```bash
  cd backend/laravel
  php artisan serve --host=0.0.0.0 --port=8080
  ```

#### "Connection timeout"
- **Причина:** Сервер слишком долго отвечает или недоступен
- **Решение:** Проверьте, что бэкенд запущен и отвечает

#### "Cannot resolve server address"
- **Причина:** Неправильный URL в конфигурации
- **Решение:** Проверьте `env.dev.json` - должен быть `http://10.0.2.2:8080` для эмулятора

#### "HTTP error 404"
- **Причина:** Неправильный endpoint
- **Решение:** Проверьте, что используется `/api/auth/login`

#### "HTTP error 500"
- **Причина:** Ошибка на сервере
- **Решение:** Проверьте логи Laravel: `tail -f storage/logs/laravel.log`

### 4. Для реального устройства

Если используете реальное Android устройство:

1. Узнайте IP адрес вашего компьютера:
   ```bash
   # Linux/Mac
   ip addr show | grep "inet " | grep -v 127.0.0.1
   
   # Windows
   ipconfig
   ```

2. Обновите `env.dev.json`:
   ```json
   {
     "API_BASE_URL": "http://192.168.1.XXX:8080",
     "ENV": "DEV"
   }
   ```
   (Замените XXX на ваш IP)

3. Убедитесь, что устройство и компьютер в одной сети

4. Убедитесь, что бэкенд слушает на `0.0.0.0:8080`:
   ```bash
   php artisan serve --host=0.0.0.0 --port=8080
   ```

### 5. Альтернатива: ADB port forwarding

Если не хотите менять конфигурацию, используйте port forwarding:

```bash
adb reverse tcp:8080 tcp:8080
```

После этого в приложении можно использовать `http://localhost:8080` в конфигурации.

### 6. Проверка логов

В Android Studio:
1. Откройте Logcat
2. Фильтр: `tag:ConfigLoader OR tag:NetworkModule OR tag:AuthRepository`
3. Ищите ошибки и предупреждения

### 7. Тестирование подключения из эмулятора

```bash
# Подключитесь к эмулятору через ADB shell
adb shell

# Проверьте доступность сервера
curl http://10.0.2.2:8080/api/auth/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password"}'
```

Если curl не установлен в эмуляторе, используйте `wget` или проверьте через браузер эмулятора.

