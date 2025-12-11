# Инструкция по сборке Android приложения

## Быстрый старт

### 1. Открытие в Android Studio

1. Запустите **Android Studio**
2. **File → Open** → выберите папку `mobile/app/android`
3. Дождитесь завершения синхронизации Gradle (первый раз может занять 5-10 минут)

### 2. Выбор конфигурации сборки

В верхней панели Android Studio выберите конфигурацию:

- **app-devDebug** — для разработки (localhost:8080)
- **app-stagingDebug** — для staging окружения
- **app-prodDebug** — для production (debug версия)
- **app-prodRelease** — для production (release версия)

### 3. Сборка и запуск

**Способ 1: Через меню**
- **Build → Make Project** (`Ctrl+F9`) — сборка
- **Run → Run 'app'** (`Shift+F10`) — сборка и запуск

**Способ 2: Через Gradle панель**
- Откройте **View → Tool Windows → Gradle**
- Разверните **Hydro → Tasks → build**
- Дважды кликните на `assembleDevDebug` (или другой вариант)

**Способ 3: Через терминал (если есть gradlew)**
```bash
cd mobile/app/android
./gradlew assembleDevDebug
./gradlew installDevDebug  # для установки на устройство
```

## Важные моменты

### Конфигурационные файлы

Убедитесь, что файлы конфигов находятся в:
```
app/src/main/assets/configs/
├── env.dev.json
├── env.staging.json
└── env.prod.json
```

Если их нет, скопируйте из `mobile/configs/`:
```bash
mkdir -p mobile/app/android/app/src/main/assets/configs
cp mobile/configs/*.json mobile/app/android/app/src/main/assets/configs/
```

### Требования

- **Android Studio** Hedgehog (2023.1.1) или новее
- **JDK 17+**
- **Android SDK 34**
- **Min SDK:** 24 (Android 7.0)

### Настройка JDK

1. **File → Project Structure** (`Ctrl+Alt+Shift+S`)
2. **Project → SDK** → выберите **JDK 17** или новее
3. **Gradle JDK** → выберите **JDK 17** или новее

## Решение проблем

### Gradle sync failed

1. **File → Invalidate Caches / Restart**
2. Проверьте подключение к интернету
3. Убедитесь, что JDK 17 установлен

### Config file not found

Скопируйте конфиги вручную:
```bash
cd mobile/app/android
mkdir -p app/src/main/assets/configs
cp ../../../configs/*.json app/src/main/assets/configs/
```

### Ошибки компиляции

1. **Build → Clean Project**
2. **Build → Rebuild Project**
3. Проверьте логи в **View → Tool Windows → Build**

### Проблемы с зависимостями

1. **File → Sync Project with Gradle Files**
2. Проверьте, что репозитории доступны (google(), mavenCentral())

## Проверка сборки

После успешной сборки APK файлы будут находиться в:
```
app/build/outputs/apk/
├── dev/debug/app-dev-debug.apk
├── staging/debug/app-staging-debug.apk
└── prod/debug/app-prod-debug.apk
```

## Запуск на устройстве

### Эмулятор

1. **Tools → Device Manager**
2. **Create Device** → выберите устройство и образ API 34
3. Запустите эмулятор
4. Выберите его в списке устройств и нажмите **Run**

### Физическое устройство

1. Включите **Режим разработчика** на устройстве
2. Включите **Отладку по USB**
3. Подключите устройство через USB
4. Разрешите отладку на устройстве
5. Выберите устройство в Android Studio и нажмите **Run**

## Дополнительно

Подробная документация: `README.md`

