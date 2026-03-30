# 08_SECURITY_AND_OPS — Безопасность и эксплуатация

Этот раздел содержит документацию по безопасности, аутентификации, мониторингу и эксплуатации системы.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 📋 Документы раздела

### Безопасность

#### [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md)
**Архитектура безопасности**
- Общие принципы безопасности
- Угрозы и риски
- Защитные механизмы

#### [AUTH_SYSTEM.md](AUTH_SYSTEM.md)
**Система аутентификации**
- Аутентификация пользователей
- Авторизация и роли
- Токены и сессии

#### [FULL_SYSTEM_SECURITY.md](FULL_SYSTEM_SECURITY.md)
**Полная безопасность системы**
- Безопасность на всех уровнях
- Шифрование
- Защита данных

### Эксплуатация

#### [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)
**Руководство по эксплуатации**
- Ежедневные операции
- Еженедельные операции
- Ежемесячные операции
- Процедуры обновления

#### [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)
**Резервное копирование и восстановление**
- Стратегия бэкапов
- Процедуры восстановления
- Ротация бэкапов

#### [RUNBOOKS.md](RUNBOOKS.md)
**Процедуры восстановления**
- Runbook для различных сценариев
- Диагностика проблем
- Процедуры восстановления

#### [SYSTEM_FAILURE_RECOVERY.md](SYSTEM_FAILURE_RECOVERY.md)
**Восстановление после сбоев**
- Типы сбоев
- Процедуры восстановления
- Предотвращение сбоев

### Мониторинг и логирование

#### [LOGGING_AND_MONITORING.md](LOGGING_AND_MONITORING.md)
**Логирование и мониторинг**
- Стратегия логирования
- Мониторинг системы
- Алерты и уведомления

#### [MONITORING_USER_GUIDE.md](MONITORING_USER_GUIDE.md)
**Grafana для оператора**
- доступ и учётные записи
- основные дашборды dev/prod

#### [TESTING_AND_CICD_STRATEGY.md](TESTING_AND_CICD_STRATEGY.md)
**Стратегия тестирования и CI/CD**
- Автоматизированное тестирование
- CI/CD конвейер
- Стратегия деплоя

---

## 🔗 Связанные разделы

- **[01_SYSTEM](../01_SYSTEM/)** — системная архитектура
- **[04_BACKEND_CORE](../04_BACKEND_CORE/)** — backend архитектура
- **[07_FRONTEND](../07_FRONTEND/)** — фронтенд безопасность

---

## 🎯 С чего начать

1. **Безопасность?** → Изучите [SECURITY_ARCHITECTURE.md](SECURITY_ARCHITECTURE.md)
2. **Аутентификация?** → См. [AUTH_SYSTEM.md](AUTH_SYSTEM.md)
3. **Эксплуатация?** → Прочитайте [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md)
4. **Бэкапы?** → См. [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md)

---

**См. также:** [Главный индекс документации](../INDEX.md)
