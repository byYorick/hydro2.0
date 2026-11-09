# Быстрый старт: Мониторинг системы

## 🚀 За 2 минуты

### 1. Откройте Grafana

```
http://localhost:3000
```

**Вход:**
- Логин: `admin` (или `GRAFANA_ADMIN_USER`)
- Пароль: `GRAFANA_ADMIN_PASSWORD` из `backend/.env` (`make ensure-dev-secrets` / `make prod-setup`). Публичного пароля `admin` в compose нет.

### 2. Откройте Dashboard

**Вариант А: Автоматический импорт (если настроен provisioning)**
- Dashboards должны появиться автоматически после перезапуска Grafana
- В меню слева: **Dashboards** → найдите:
  - **History Logger Service** - для мониторинга телеметрии
  - **Automation Engine Service** - для мониторинга автоматизации

**Вариант Б: Ручной импорт (если dashboards не видны)**
1. В меню слева: **Dashboards** → **Import**
2. Нажмите **Upload JSON file**
3. Выберите файл из `backend/configs/dev/grafana/dashboards/`:
   - `history-logger.json`
   - `automation-engine.json`
4. Нажмите **Load** → **Import**

**Примечание:** После первого запуска Grafana может потребоваться несколько секунд для автоматического импорта dashboards.

### 3. Проверьте статус

🟢 **UP** = всё работает  
🔴 **DOWN** = проблема, проверьте логи

---

## 📊 Что смотреть

### History Logger
- ✅ **Queue Size** < 5000 - норма
- ⚠️ **Queue Size** 5000-10000 - внимание
- 🔴 **Queue Size** > 10000 - критично

### Automation Engine
- ✅ **Zone Checks Rate** > 0 - работает
- ✅ **Commands Sent** - активность автоматизации
- ⚠️ **Errors** > 0 - проверьте детали

---

## 🚨 Алерты

**Prometheus:** `http://localhost:9090/alerts`

Красные алерты = требуется внимание

---

## 📖 Подробнее

Полное руководство: `../doc_ai/08_SECURITY_AND_OPS/MONITORING_USER_GUIDE.md`
