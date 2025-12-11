# Hydro Android App (Kotlin + Jetpack Compose)

Полнофункциональное Android-приложение для Hydro 2.0.

## Стек технологий

- **Kotlin** — язык программирования
- **Jetpack Compose** — современный UI toolkit
- **Hilt** — Dependency Injection
- **Retrofit + OkHttp** — HTTP клиент
- **Moshi** — JSON парсинг
- **Room** — локальная база данных для кэширования
- **DataStore** — хранение настроек и токенов
- **Navigation Compose** — навигация между экранами

## Требования

- **Android Studio** Hedgehog (2023.1.1) или новее
- **JDK 17** или новее
- **Android SDK** 34 (API Level 34)
- **Min SDK** 24 (Android 7.0)
- **Target SDK** 34

## Первоначальная настройка

### 1. Открытие проекта

1. Запустите Android Studio
2. Выберите **File → Open**
3. Перейдите в папку `mobile/app/android`
4. Дождитесь синхронизации Gradle (может занять несколько минут при первом запуске)

### 2. Проверка конфигурации

Убедитесь, что конфигурационные файлы находятся в правильном месте:
- `app/src/main/assets/configs/env.dev.json`
- `app/src/main/assets/configs/env.staging.json`
- `app/src/main/assets/configs/env.prod.json`

Если файлов нет, они будут скопированы автоматически при сборке из `mobile/configs/`.

### 3. Настройка SDK

1. Откройте **File → Project Structure** (или `Ctrl+Alt+Shift+S`)
2. В разделе **SDK Location** убедитесь, что указан правильный путь к Android SDK
3. В разделе **Project** выберите **Gradle JDK** версии 17 или новее

## Сборка проекта

### Вариант 1: Через Android Studio UI

1. **Выбор flavor (окружения):**
   - В верхней панели найдите выпадающий список с конфигурациями (рядом с кнопкой Run)
   - Выберите нужный вариант:
     - `app-devDebug` — для разработки
     - `app-stagingDebug` — для staging окружения
     - `app-prodDebug` — для production (debug версия)
     - `app-prodRelease` — для production (release версия)

2. **Сборка:**
   - **Build → Make Project** (`Ctrl+F9`) — сборка проекта
   - **Build → Rebuild Project** — полная пересборка
   - **Run → Run 'app'** (`Shift+F10`) — сборка и запуск на эмуляторе/устройстве

### Вариант 2: Через Gradle

Откройте терминал в Android Studio (**View → Tool Windows → Terminal**) и выполните:

```bash
# Сборка debug версии для dev окружения
./gradlew assembleDevDebug

# Сборка debug версии для staging окружения
./gradlew assembleStagingDebug

# Сборка debug версии для production
./gradlew assembleProdDebug

# Сборка release версии для production
./gradlew assembleProdRelease

# Установка на подключенное устройство (dev)
./gradlew installDevDebug

# Установка на подключенное устройство (staging)
./gradlew installStagingDebug

# Установка на подключенное устройство (production)
./gradlew installProdDebug
```

### Вариант 3: Через командную строку (Linux/Mac)

```bash
cd mobile/app/android
./gradlew assembleDevDebug
```

Для Windows:
```cmd
cd mobile\app\android
gradlew.bat assembleDevDebug
```

## Product Flavors

Проект использует три окружения (flavors):

### Dev
- **Application ID:** `com.hydro.app.dev`
- **Config:** `env.dev.json`
- **Base URL:** `http://localhost:8080` (по умолчанию)
- Используется для локальной разработки

### Staging
- **Application ID:** `com.hydro.app.staging`
- **Config:** `env.staging.json`
- **Base URL:** настраивается в конфиге
- Используется для тестирования

### Prod
- **Application ID:** `com.hydro.app`
- **Config:** `env.prod.json`
- **Base URL:** настраивается в конфиге
- Используется для production

**Важно:** Все три flavor могут быть установлены одновременно на одном устройстве, так как имеют разные Application ID.

## Настройка конфигурационных файлов

Конфигурационные файлы находятся в `mobile/configs/` и автоматически копируются в `app/src/main/assets/configs/` при сборке.

Формат конфига:
```json
{
  "API_BASE_URL": "https://your-backend.example.com",
  "ENV": "PROD"
}
```

Для изменения URL backend отредактируйте соответствующий файл в `mobile/configs/`.

## Запуск на эмуляторе

1. **Создание эмулятора:**
   - **Tools → Device Manager**
   - Нажмите **Create Device**
   - Выберите устройство (например, Pixel 5)
   - Выберите системный образ (рекомендуется API 34)
   - Завершите создание

2. **Запуск:**
   - Выберите созданный эмулятор в списке устройств
   - Нажмите **Run** (`Shift+F10`)

## Запуск на физическом устройстве

1. **Включите режим разработчика:**
   - Перейдите в **Настройки → О телефоне**
   - Нажмите 7 раз на **Номер сборки**

2. **Включите отладку по USB:**
   - **Настройки → Для разработчиков → Отладка по USB**

3. **Подключите устройство:**
   - Подключите устройство через USB
   - Разрешите отладку по USB на устройстве (появится диалог)

4. **Запуск:**
   - Выберите устройство в списке устройств в Android Studio
   - Нажмите **Run**

## Решение проблем

### Ошибка "SDK not found"
- Убедитесь, что Android SDK установлен и путь указан правильно
- **File → Project Structure → SDK Location**

### Ошибка "Gradle sync failed"
- Проверьте подключение к интернету (Gradle загружает зависимости)
- Попробуйте **File → Invalidate Caches / Restart**
- Убедитесь, что используется JDK 17+

### Ошибка "Config file not found"
- Убедитесь, что файлы конфигов находятся в `app/src/main/assets/configs/`
- Если их нет, скопируйте из `mobile/configs/`:
  ```bash
  mkdir -p app/src/main/assets/configs
  cp ../../../configs/*.json app/src/main/assets/configs/
  ```

### Ошибка компиляции Kotlin
- Убедитесь, что версия Kotlin совместима (1.9.24)
- Попробуйте **Build → Clean Project**, затем **Build → Rebuild Project**

### Проблемы с Hilt
- Убедитесь, что все классы помечены правильными аннотациями (`@HiltAndroidApp`, `@AndroidEntryPoint`)
- Проверьте, что `kapt` плагин подключен в `build.gradle.kts`

## Структура проекта

```
app/
├── src/
│   ├── main/
│   │   ├── java/com/hydro/app/
│   │   │   ├── core/           # Основные компоненты
│   │   │   │   ├── config/     # Загрузка конфигов
│   │   │   │   ├── data/       # API и репозитории
│   │   │   │   ├── database/   # Room entities и DAOs
│   │   │   │   ├── di/         # Hilt модули
│   │   │   │   ├── domain/     # Domain models
│   │   │   │   ├── network/    # Сетевой слой
│   │   │   │   ├── prefs/      # DataStore
│   │   │   │   └── realtime/   # WebSocket/Polling
│   │   │   ├── features/       # Функциональные модули
│   │   │   │   ├── auth/       # Авторизация
│   │   │   │   ├── greenhouses/# Теплицы
│   │   │   │   ├── zones/      # Зоны
│   │   │   │   ├── alerts/     # Алерты
│   │   │   │   └── provisioning/# Настройка узлов
│   │   │   ├── ui/             # UI компоненты
│   │   │   │   ├── screens/    # Экраны
│   │   │   │   └── components/ # Переиспользуемые компоненты
│   │   │   ├── MainActivity.kt
│   │   │   └── HydroApp.kt
│   │   ├── res/                # Ресурсы
│   │   └── AndroidManifest.xml
│   └── test/                   # Unit тесты
├── build.gradle.kts
└── proguard-rules.pro
```

## Дополнительная информация

- **API документация:** `doc_ai/12_ANDROID_APP/ANDROID_APP_API_INTEGRATION.md`
- **Экраны:** `doc_ai/12_ANDROID_APP/ANDROID_APP_SCREENS.md`
- **Backend API:** `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`

## Поддержка

При возникновении проблем проверьте:
1. Логи в **View → Tool Windows → Logcat**
2. Ошибки сборки в **View → Tool Windows → Build**
3. Gradle sync статус в правом нижнем углу Android Studio
