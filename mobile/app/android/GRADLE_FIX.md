# Исправление ошибки Gradle

## Проблема
```
Failed to notify project evaluation listener.
'org.gradle.api.file.FileCollection org.gradle.api.artifacts.Configuration.fileCollection(org.gradle.api.specs.Spec)'
```

## Решение

### 1. Создан Gradle Wrapper
Создан gradle wrapper с версией 8.5, которая совместима с AGP 8.5.2.

### 2. Следующие шаги

**В Android Studio:**
1. **File → Sync Project with Gradle Files**
2. Если ошибка сохраняется:
   - **File → Invalidate Caches / Restart**
   - Выберите **Invalidate and Restart**
   - После перезапуска: **File → Sync Project with Gradle Files**

**Или через терминал:**
```bash
cd mobile/app/android
./gradlew clean
./gradlew build --refresh-dependencies
```

### 3. Если проблема не решена

Попробуйте обновить версию Hilt до последней стабильной:
```kotlin
id("com.google.dagger.hilt.android") version "2.52" apply false
```

Или временно отключите kapt и используйте KSP (требует изменений в коде):
- Замените `kapt` на `ksp` плагин
- Обновите зависимости

### 4. Проверка версий

Убедитесь, что версии совместимы:
- **Gradle:** 8.5 (через wrapper)
- **AGP:** 8.5.2
- **Kotlin:** 1.9.24
- **Hilt:** 2.51.1

### 5. Альтернативное решение

Если проблема сохраняется, можно попробовать:
1. Понизить версию AGP до 8.3.0
2. Или обновить до AGP 8.7.3 с Gradle 8.9

