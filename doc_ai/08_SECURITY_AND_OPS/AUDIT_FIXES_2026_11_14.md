# Исправления аудита Hydro 2.0

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

Исходная версия аудита: `579a2bd`. Изменения подготовлены локально, без развёртывания и изменения подключённых устройств.

## Изменения и статус

| Пункт | Реализация | Предел проверки / оставшаяся работа |
|---|---|---|
| F01 | Service middleware по умолчанию принимает только service token. Sanctum разрешён явно на двух смешанных маршрутах; внутренние mutation endpoints закрыты от пользовательских ролей | PHPUnit: viewer/operator/admin без service token отвергаются, положительные mutation tests используют service token; полный Laravel suite выполнен на PostgreSQL 16.14 / TimescaleDB 2.28.2 |
| F02 | Production generation паролей не создаёт неиспользуемые python_service/automation_engine с известными fallback паролями | Production требует подготовленный mounted password file и не генерирует fallback. Новый offline bundle содержит только активные сервисы и узлы; существующий парк требует rollout |
| F03 | Production требует явного per-user ACL; генератор ограничивает normal/pre-bind namespace конкретным node_uid/hardware_id. HL wrapping использует индивидуальные MQTT-пароли | Существующий парк устройств требует миграции username/password; Config HMAC не реализован и остаётся отдельным проектом |
| F04 | Drain не переотправляет mutating команды; безопасные диагностические/off команды допускаются только до 60 секунд. Непригодные команды переходят INVALID/DRAIN_ABANDON | Неопределённый физический результат требует reconciliation/оператора. Новый cmd_id не делает повтор безопасным |
| F05 | Общий advisory lock HTTP/drain. Перед mutating dispatch сохраняется внутренний маркер __hl_dispatch_started, повтор запрещён после сбоя и SEND_FAILED | Это at-most-once попытка на уровне application dispatch, а не гарантия exactly-once на устройстве. Транспортные повторы одного подписанного payload остаются |
| F06 | last_ts обновляется только вперёд. Samples и last projection записываются атомарным SQL statement и в batch, и в fallback | Реальный PostgreSQL 16.2: older/equal/newer и откат sample при ошибке projection. Старый realtime update всё ещё может приходить вне порядка; UI должен учитывать timestamp |
| F07 | Отсутствующий wrapping credential приводит к 503 вместо успеха с неполной конфигурацией. Production требует per-node secret mount | Перед rollout заполнить credentials каждого узла |
| F08 | Healthcheck брокера учитывает TLS-only listener | TCP probe проверяет listener; фактические сертификаты и все клиенты нужно проверить на стенде |
| F09 | Redis noeviction, maxmemory 384 MB при лимите контейнера 512 MB | Проверены AOF после SIGKILL, возврат in-flight, DLQ и отказ новой записи при noeviction без потери старой. Длительная нагрузка и подбор memory headroom остаются обязательны |
| F10 | Отдельный AP OkHttpClient, правильный POST /wifi/connect, DTO ssid/password/mqtt_host/mqtt_port, ограниченный cleartext 192.168.4.1, redirect запрещён. Есть ручной путь для уже подключённого узла | Android debug/release собраны, 35 JVM tests прошли. Добавлена привязка setup HTTP к физической WiFi Network; cellular/VPN fallback запрещён. Аппаратная проверка отложена по указанию пользователя |
| F11 | /health/live и /health/ready; последний возвращает 503 при degraded. Compose использует readiness | /health остаётся диагностическим для совместимости |
| F12 | Firmware cache допускает 128 ASCII байт cmd_id; command name buffer допускает 64 UTF-8 codepoint (256 байт). JSON schema не сужается | Полная матрица 8/8 собрана на ESP-IDF 5.5.0; flash partition size checks прошли. Обновление устройств и аппаратная проверка отложены |
| F13 | Vite 7 + совместимые Vue/Laravel плагины; исправленные minimatch/glob overrides. CI проверяет все зависимости, включая dev | После финальной установки npm audit: 0 vulnerabilities. Требуется Node >=20.19; тесты выполнялись в node:20 |
| F14 | CI PostgreSQL/TimescaleDB выровнен с production: 2.28.2-pg16. Настройки DB name/user согласованы. Добавлены индивидуальные PG_USER/PG_PASS overrides для сервисов | Добавлена миграция четырёх NOLOGIN capability roles, явные grants и команда проверки; матрица проверена на PostgreSQL 16.14 / TimescaleDB 2.28.2, включая повторное применение после restore. В production миграция и привязка индивидуальных login-учёток ещё не применены |
| F15 | Декомпозиция AE3, RecipeEditor view/state/draft persistence, MQTT/command scopes и telemetry runtime завершена. Совместимые фасады используют явные зависимости; foreign-module globals mutations удалены; venv removals сохранены | Текущие программные проверки и квалификация — раздел «Завершение F15» ниже. Production images/rollout и аппаратная приёмка требуют отдельных подтверждённых результатов, они не объявлены выполненными по unit suite |

## Миграция MQTT в production

1. Приостановить автоматизацию на время смены credentials. Зафиксировать результаты незавершённых команд: запрещено повторять дозирование с неизвестным результатом.
2. Составить inventory JSON (не содержит пароли):

```json
[{"username":"node_ph_1","node_uid":"nd-ph-1","hardware_id":"hardware-ph-1"}]
```

3. Выполнить `python tools/mqtt/generate_node_acl.py inventory.json /absolute/path/production.acl`. Указать абсолютный путь как `MQTT_PRODUCTION_ACL_FILE`. Имена пользователей, node_uid и hardware_id должны быть уникальны; wildcard и reserved usernames отклоняются.
4. Через `mosquitto_passwd` добавить каждому username отдельный пароль в production password file. Проверить наличие history_logger/mqtt_bridge с индивидуальными сервисными паролями. Удалить неиспользуемые fallback/shared accounts. Production password file уже смонтирован Compose; не коммитить его.
5. Установить эти username/password в NodeConfig/NVS каждого устройства доверенным способом. ESP32 setup portal пока принимает только WiFi и MQTT host/port; он не решает безопасную выдачу уникальных credentials.
6. Создать защищённый JSON secret file `{"nd-ph-1":"<MQTT password of this node>"}` для всех узлов, включить read-доступ только для HL и оператора. Указать путь как `MQTT_NODE_PASSWORDS_FILE`. Он монтируется read-only; содержимое не должно попадать в Git/логи.
7. Проверить на изолированном узле TLS, config_report, расшифровку node_secret_enc, HMAC и запрет чтения/записи чужих топиков. Возобновлять автоматизацию после проверки физического состояния и очередей.

Старый shared ACL оставлен только для dev-совместимости; использовать его как production ACL небезопасно. Имена MQTT топиков и payload не менялись. Config HMAC остаётся planned, никакой проверки подписи конфигурации этим изменением не добавлено.

## Проверки

Подробные логи находятся в `/workspace/hydro-audit/fix-*`. Полный frontend suite: 254 файла, 1787 passed, 1 skipped. Пройдены typecheck, ESLint, API boundary и production build. После последнего изменения dependency override повторно прошли dependency tree validation (npm ls), typecheck, lint и полный npm audit (0 vulnerabilities). Проверки firmware host проходят с UBSan; они не компилируют весь node_framework/ESP-IDF. Дополнительно прошли 58 тестов AE3 HTTP-клиента и sequential gateway. Пройдены схемы шести Compose конфигураций, зеркала JSON schema, PHPUnit для границы авторизации и семь реальных MQTT broker tests.

Профильный набор HL после request-local рефакторинга: 110 passed. Отдельный набор новых ограничений dispatch/DB pool и общих DB helpers: 17 passed.

Временный PostgreSQL 16.2 (`pgserver` только в audit directory, не dependency приложения) подтвердил monotonic projection, атомарный rollback и CAS/advisory-lock. Затем выполнена квалификация на настоящем TimescaleDB 2.28.2 / PostgreSQL 16.14 в изолированной Docker-сети (см. ниже). Временный PostgreSQL не подменяет этот результат или нагрузочный стенд.

Последующие разделы фиксируют выполненные общий restart/degraded сценарий core, 15-минутную нагрузку и физический PITR. Остаются Android/ESP32 на реальной аппаратуре (отложены пользователем), длительная нагрузка с production-профилем и production rollout. Отдельные Redis/AOF и restore drill не заменяют эти испытания.


## Следующие этапы: инструменты миграции и DB capability roles

Вместо ручной подготовки трёх независимых файлов используйте `tools/mqtt/prepare_node_credentials.py`:

```bash
chmod 600 /secure/service_credentials.json
python tools/mqtt/prepare_node_credentials.py /secure/inventory.json /secure/service_credentials.json /secure/mqtt-v1
```

`service_credentials.json` — JSON object ровно с ключами `history_logger` и `mqtt_bridge`, значения — используемые сервисные пароли минимум 32 байта. Они должны совпадать с соответствующими MQTT_*_PASS окружения сервисов. Пароли не передаются в аргументах subprocess и не печатаются. Генерация использует изолированный Docker `eclipse-mosquitto:2.0.22`, без сети и подключения к устройствам.

Комплект содержит `production.acl`, хешированный `passwords`, приватные `node_credentials.json` для доверенного переноса на устройства и `node_passwords.json` для HL; каталог имеет mode 0700, секретные файлы — 0600. Внутренний `.gitignore` защищает комплект от случайного `git add`. Используйте versioned directory вне репозитория. Production Compose требует:

- `MQTT_PRODUCTION_ACL_FILE=/secure/mqtt-v1/production.acl`
- `MQTT_PRODUCTION_PASSWORD_FILE=/secure/mqtt-v1/passwords`
- `MQTT_NODE_PASSWORDS_FILE=/secure/mqtt-v1/node_passwords.json`

При изменении inventory передайте `--previous /secure/mqtt-v1/node_credentials.json`: прежние пароли сохраняются. Для намеренной ротации добавьте `--rotate-node <node_uid>`. Изменение username/hardware_id требует явной ротации. Существующий output не перезаписывается. На ошибке временные plaintext файлы удаляются. Перед установкой нового комплекта согласуйте его с состоянием устройств; генерация не применяет credentials к ESP32.

Новая Laravel migration `2026_11_14_100000_create_runtime_capability_roles.php` создаёт четыре роли с именами `hydro_<hash_database>_{hl,ae,bridge,aggregator}`. Это NOLOGIN capability roles, не учётные записи подключения. Нет SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS; права выдаются явно на существующие таблицы и необходимые sequences. Ключевые границы: только HL пишет commands; AE пишет собственные execution/lease/workflow таблицы; агрегатор может удалить старые telemetry_samples, но не изменить их. Общие infra queue/event таблицы включены в соответствующие профили. Auth/user/recipe таблицы не разрешены. Новые таблицы будущих миграций требуют явного обновления grants.

Миграцию выполняет Laravel migrator с правом CREATEROLE. Существующая неизвестная роль с таким именем отвергается; повторное применение после rollback допускает только помеченные управляемые роли без опасных атрибутов. Rollback отзывает права и сохраняет NOLOGIN roles; он не использует DROP OWNED и не удаляет данные. Транзакция миграции обязательна.

Перед rollout выполните в Laravel контейнере:

```bash
php artisan hydro:db-runtime-roles
php artisan hydro:db-runtime-roles --check
```

По умолчанию команда и `--check` работают read-only: проверяются атрибуты capability roles, необходимые grants, отсутствие доступа к auth/recipe таблицам и CREATE на public schema. Явный `--apply` транзакционно повторяет выдачу управляемых grants и затем выполняет проверку; это операция migrator после portable restore с `--no-privileges`. Она не создаёт login-учётки и не восстанавливает их memberships. Login-учётки с разными секретами нужно создать доверенным механизмом управления credentials и включить в соответствующие capability roles с наследованием прав. Не назначать им владение БД/таблицами или административные роли. Затем задать `HL_PG_USER/PASS`, `AE_PG_USER/PASS`, `BRIDGE_PG_USER/PASS`, `AGGREGATOR_PG_USER/PASS`. Laravel migrations продолжают выполняться migrator-учёткой. Не устанавливать PG_USER в имя NOLOGIN capability role.

Проверено: 4 теста offline bundle, 8 реальных broker tests, Compose schemas, 6 PHPUnit tests профилей/команды/защиты от чужой роли и административных memberships. Выполненные SQL миграции также проверены на временном PostgreSQL 16.2: матрица разрешений, sequence access и безопасный rollback. PostgreSQL feature tests затем успешно выполнены в полном Laravel suite, включая reapply после revoke и проверку запрета лишних прав. Production credentials/устройства не менялись.


## Уточнение очередности

По указанию пользователя тестирование на физическом оборудовании отложено. Программная квалификация Android и восьми ESP-IDF целей выполняется независимо; прошивка устройств, дозирование и аппаратные E-STOP/сеть/калибровка в этот этап не входят.


## Программная квалификация Android и ESP-IDF

Завершены `assembleDevDebug`, `assembleProdRelease`, `testDevDebugUnitTest`: **35 passed, 0 failures/errors**, 12 suites. Среда: полный Temurin JDK 17.0.21, Gradle 8.13, AGP 8.13.2, Android Platform 34, Build-Tools 35.0.0. CI setup SDK выровнен по фактически необходимому Build-Tools 35. Локальный SDK path больше не отслеживается в Git.

Исправлена обработка Result.failure в provisioning ViewModel; отмена coroutine не превращается в UI error. Setup HTTP client выбирает физическую Wi-Fi Network с прямым маршрутом к 192.168.4.1, привязывает socketFactory/DNS, отвергает cellular и VPN. Тесты проверяют маршрутизацию на mock Android Network и успех/отказ repository. Это не аппаратное подтверждение Android routing.

Проверены итоговые APK: debug APK подписан по v2; release APK **unsigned**, signing key не создавался для production. В скомпилированной network-security-config release APK cleartext запрещён в base-config и разрешён только для 192.168.4.1 без subdomains. Release R8/resource shrinking/lintVital прошли. Обычные compiler/deprecation warnings в существующем Android коде остаются; успешная сборка не означает отсутствие всех замечаний Android Lint.

Восемь прошивок собраны на **ESP-IDF v5.5.0**, GCC 14.2.0_20241119. Для light_node использован RISC-V compiler, для остальных — Xtensa; test_node — ESP32-S3. Все ELF и бинарники сгенерированы, все app partition size checks прошли. В test_node dependencies.lock сохранена исходная запись IDF 5.5.3: metadata не понижалась из-за локального SDK, сторонние component versions не менялись. Локальный результат подтверждает совместимость с SDK 5.5.0; отдельный запуск CI с release-v5.5/5.5.3 здесь не выполнялся.

| Цель | Чип | App binary, байт | App partition, байт |
|---|---|---:|---:|
| ph_node | esp32 | 973760 | 1835008 |
| ec_node | esp32 | 971200 | 1835008 |
| pump_node | esp32 | 1106512 | 1835008 |
| storage_irrigation_node | esp32 | 1030160 | 1835008 |
| climate_node | esp32 | 1174208 | 1835008 |
| light_node | esp32c3 | 1198368 | 1835008 |
| relay_node | esp32 | 1000976 | 1835008 |
| test_node | esp32s3 | 1247024 | 2097152 |

Артефакты и отчёты сохранены в `/workspace/hydro-audit/build-artifacts/`: `android/app-dev-debug.apk`, `android/app-prod-release-unsigned.apk`, `android/validation-reports.zip`, `firmware-all.zip`. Отдельные firmware bundles содержат ELF, map, sdkconfig, flash args, bootloader и partition table. SHA256 и статистика: `build-android-results.json`, `build-firmware-results.json` в audit directory.

Физические устройства не прошивались; тесты насосов, E-STOP, калибровки, Wi-Fi reconnect и питания не выполнялись по указанию пользователя. Laravel/TimescaleDB и отдельные Redis/restore checks завершены (ниже). Далее выполнены 15-минутный soak, координированный restart восьми core runtimes и физический PITR на тестовой копии (ниже). Продолжительный production soak, rollout и постепенное разделение крупных AE3/frontend модулей остаются отдельными этапами. Production credentials, memberships и парк MQTT устройств по-прежнему требуют отдельного rollout.


## Laravel, TimescaleDB и восстановление

Среда проверки: PHP 8.2.35, PostgreSQL 16.14, TimescaleDB 2.28.2 (официальный образ `2.28.2-pg16`), Redis 7.4.9; отдельная Docker-сеть без опубликованных портов и без подключения к устройствам. Полный Laravel suite использует `hydro_test`. Отдельная миграция в режиме `APP_ENV=e2e` на новой `hydro_ts_test` создала четыре настоящих hypertable: `telemetry_samples`, `telemetry_agg_1m`, `telemetry_agg_1h`, `zone_features_5m`. Обычный testing mode намеренно пропускает hypertable conversion и сам по себе не проверяет этот путь.

Полный Laravel suite: **1452 tests, 7005 assertions, 0 failures/errors** (2:23, 211.5 MB). Два предупреждения PHPUnit о metadata в doc-comments устранены переводом Group на атрибуты; 48 broadcasting tests затем прошли без предупреждений (147 assertions), collection `--list-groups` также чистая. Pint для изменённых PHP-файлов, bash syntax, CI YAML parsing и `git diff --check` прошли.

Отдельная `hydro_ae_recovery_test`, подготовленная Laravel migrations: **40 passed** за 6.86 s. Набор включает startup recovery, crash windows между этапами, multi-instance recovery, terminal command reconciliation, requeue из waiting_command и fail-closed heartbeat lease. Это тестирование реальных SQL repositories с подменёнными внешними gateway, без отправки команд оборудованию; полный restart всего стека этим не подменяется.

В CI явно заданы PHP extensions `pdo_pgsql`, `redis`, `bcmath`, `pcntl` и memory_limit=1G. Исправлены два устаревших auth-теста, добавлены отрицательные проверки ingest/channel mutation без service token. Два broadcasting Group перенесены с doc-comments на PHPUnit attributes. Исправлено имя файла `RecipeRevisionPhaseTest.php`: четыре существующих теста ранее не обнаруживались PHPUnit. Reset public schema в тестах теперь выдаёт PUBLIC только USAGE, как PostgreSQL 16, вместо CREATE; иначе тестовая среда обходила проверку ограничения capability roles.

Реальный логический round-trip выявил и устранил ошибку restore для TimescaleDB: перед загрузкой выполняются создание extension и `timescaledb_pre_restore()`, после успешной загрузки — `timescaledb_post_restore()`. Используется `--exit-on-error`; неуспешный Timescale restore остаётся в restoring mode и не допускает фоновые jobs на частичной БД. До DROP выполняется `pg_restore --list`; повреждённый TOC отклоняется до подключения к целевой БД. Это не полная проверка целостности всех data blocks архива. Системные БД запрещены; имя target передаётся через безопасно цитируемые переменные psql.

Штатные backup/restore scripts успешно перенесли `hydro_ts_test` → `hydro_restore_test`. Подтверждены 17 samples, last projection, encrypted probe с тем же исходным тестовым APP_KEY, persisted dispatch marker и QUEUED status, четыре hypertable и restoring=off. `hydro:db-runtime-roles --apply` восстановила grants для нового database-scoped имени, проверка `--check` прошла. Повторный запуск с заведомо повреждённым архивом завершился ошибкой; все данные прежнего target остались и повторно проверены. Шесть регрессионных сценариев restore включены в CI.

Redis drill использовал реальный SIGKILL и запуск из AOF после WAITAOF. Три сообщения сохранились, два in-flight возвращены, повторный ACK/возврат не дублирует записи; malformed и исчерпавшие retry сообщения уходят в DLQ. При искусственном достижении maxmemory/noeviction новая запись отвергнута, прежнее сообщение сохранено, evicted_keys=0. Порог после проверки восстановлен.

Синтетический DB backup сохранён в `/workspace/hydro-audit/build-artifacts/database/fixture-backup.tar.gz` с закрытыми правами; это тестовый артефакт, не production backup. Логи: `/workspace/hydro-audit/qa-*`; сводки — `qa-restore-results.json`, `qa-corrupt-archive-results.json`, `qa-redis-results.json`. SQL restore малой fixture занял 0.939 s, Redis kill/restart/recover — 1.242 s. Это не измерение production RTO/RPO: не проверялись большой объём данных, WAL/PITR, потеря диска или полный application backup. Исходный APP_KEY должен храниться отдельно с закрытыми правами; новый key при восстановлении существующих зашифрованных данных не генерируется.


## Нагрузка и сбои telemetry path

На изолированном стенде без опубликованных портов работали реальные Mosquitto 2.0.22, Redis 7.4.9, HL, Laravel HTTP и TimescaleDB 2.28.2 / PostgreSQL 16.14. Fixture — 20 зон × 10 каналов pH, без команд и задач автоматики. Схема подготовлена Laravel migrations в e2e mode с четырьмя hypertable. На этом этапе наблюдался HTTP 200, но последующий контроль обнаружил неверный cwd у тестового PHP router: этот статус не подтверждал обработку batch самим Laravel. Прежние SQL/MQTT/Redis результаты сохраняются; сквозная Laravel-проверка выполнена заново ниже. Production и устройства не затрагивались.

Найдены и исправлены дополнительные дефекты:

- Сверка INSERT RETURNING не учитывала округление timestamp(0). Доли секунды давали ложный JOIN mismatch после commit, повтор samples и DLQ. Теперь сравниваются значения с точностью PostgreSQL, включая перенос секунды/даты и half-second boundary относительно PostgreSQL epoch. Добавлены десять регрессионных случаев.
- `_on_disconnect` блокировал сетевой поток ожиданием reconnect/CONNACK. Повторное подключение передано Paho network loop; Callback API v2 используется при Paho 2, старый callback API остаётся совместимым для прежних клиентов.
- В одном из контрольных crash-прогонов потеряны четыре уникальных sample: автоматический PUBACK происходил до асинхронного enqueue. HL теперь включает manual ACK только для durable telemetry subscription и подтверждает её после Redis admission. Во время Redis backpressure обработчик не завершает delivery; отмена не ACK. Остальные сообщения не получают новых повторов side effects.
- Восстановление постоянной сессии выявило окно startup: сообщения повторялись до установки callbacks. HL теперь сначала регистрирует callbacks, затем CONNECT. Это проверено перезапуском HL при недоступном Redis.
- Config-report facade перезаписывал module globals из вложенного helper. Из-за этого тест зависимости от порядка менял mocks и уходил в реальный HTTP. Теперь используются immutable task-local snapshots с восстановлением вложенного контекста; отдельно проверены конкурентные вызовы и выход по исключению. Channel sync получает execute явно.
- Redis test mocks больше не изображают синхронный register_script как async-функцию. Устранены предупреждения о не-awaited coroutine в HL и common suites.

Paho pins для HL, AE, MQTT bridge, digital-twin и shared test requirements выровнены на 2.1.0; требуется пересборка соответствующих images. HL отказывается запускать durable ingress с clean session либо без manual-ACK API. Topic/payload и команда на устройство не менялись.

| Сценарий | Результат |
|---|---|
| 40 samples/s × 180 s; SIGKILL PostgreSQL, SIGKILL HL, orderly stop/restart MQTT | 7200/7200 уникальных samples, 7200 publisher PUBACK, один повтор после crash, DLQ=0, evicted=0, projection mismatches=0 |
| Redis orderly stop; SIGKILL HL; HL запускается до Redis; Redis восстановлен | 1200/1200, без повторов, DLQ=0, projection mismatches=0 |
| Всплеск 1000 samples/s × 20 s с durable ACK | 20000/20000, 20000 publisher PUBACK, без повторов/DLQ/eviction, drain завершён за 20.793 s от старта |

В финальном burst наблюдаемый максимум queue+processing — 1171, Redis used_memory — 2626656 bytes. P99 времени от publish до первого SQL-наблюдения — 1767.381 ms; poll выполнялся примерно раз в секунду, поэтому это верхняя оценка с задержкой наблюдения, не точная latency commit. Для fault run P99 20462.098 ms включает намеренную недоступность БД. Readiness менялась 200 → 503/unreachable → 200 соответственно отказу зависимости/HL и восстановлению. Счётчики подтверждают сохранность уникальных samples; один повтор согласуется с at-least-once, а не exactly-once.

Логи и JSON: `/workspace/hydro-audit/resilience-*`. Файлы `*-before-*`, `*-aborted*`, `*-initial*`, `*-puback-api*` относятся к диагностическим/неполным прогонам и не являются успешной квалификацией. Итоговые данные — `resilience-chaos.json`, `resilience-durable-redis.json`, `resilience-burst-durable.json`.

Новые инструменты: `tools/ci/telemetry_resilience_fixture.php` и `tools/ci/telemetry_resilience_probe.py`. Fixture разрешена только в testing на `hydro_test` / `hydro_resilience_test*` и не перезаписывает существующие данные/manifest. Probe дополнительно проверяет реальные связи fixture в БД, отсутствие AE tasks, число уникальных samples, projection, DLQ и eviction; не отправляет команды узлам. Порядок запуска — RUNBOOKS.md.

Эта квалификация покрывает ingestion path и отдельные отказы зависимостей. Она не заменяет длительный soak, одновременное аварийное завершение всего стека (включая scheduler/AE), отказ диска, физический PITR и аппаратную проверку. Redis в новом admission-тесте останавливался штатно, чтобы отдельно проверить outage/backpressure; AOF после SIGKILL проверен предыдущим drill. Нулевой production RPO и достаточный memory headroom для реального потока не заявляются.


Финальные автоматические проверки этого этапа: **329 HL**, **316 common**, **40 AE recovery**, **17 MQTT bridge**, **8 real broker tests** — без failures/errors. HL suite сохраняет два deprecation warning зависимостей Starlette/httpx/AnyIO; common suite проходит без warnings. Paho callback API v1 deprecation устранена для общего MQTT client переходом на API v2. Ruff F/E9 по всем Python services, lint probe и `git diff --check` прошли. Portable fixture проверена на отдельной мигрированной БД: создание 20 зон, отказ повторного использования manifest и отказ запрещённой БД с ненулевым exit code. Финальный smoke нового probe: 200/200. Сводка с выбранными итоговыми файлами — `/workspace/hydro-audit/resilience-results.json`; остальные промежуточные baseline/diagnostic отчёты не используются как финальное подтверждение.


## Продолжение: soak, core restart и физический PITR

Стенд — отдельная **internal Docker network**, без опубликованных портов и физических устройств. Работали PostgreSQL 16.14 / TimescaleDB 2.28.2, Redis 7.4.9, Mosquitto 2.0.22, Laravel HTTP + настоящий `schedule:work`, HL, AE3 runtime, MQTT bridge и telemetry aggregator. Python запускался с текущим исходным кодом и Paho 2.1.0. Использованы сохранённые официальные runtime rootfs и отдельные тестовые data directories в RAM; это не сборка/развёртывание production images. Laravel cache — Redis; тестовая очередь Laravel — sync. Async Laravel queue-worker и WebSocket/Reverb этим набором не квалифицируются.

Исправлена конфигурация **тестового launcher**, не product-кода: PHP `server.php` требует cwd `public`. Ранее cwd был `/app`, и PHP выдавал HTML warning со статусом 200. Теперь сервер работает из `/app/public`; API проверяются по JSON и фактическому результату действий. Удалены прежние localhost overrides из hosts тестового PHP runtime. Предыдущие выводы об успешной обработке realtime на основании одного HTTP 200 отозваны; сохранность SQL samples и проверки broker/Redis от этого не зависели.

На исправленном стенде сценарий на основе канонической E95 прошёл **54 проверки**: реальный `ScheduleDispatcher` создаёт intent, обращается к AE, команда через HL поступает в MQTT; программный ответчик проверяет HMAC и отправляет DONE. Task и intent завершаются, canonical internal status endpoint возвращает completed. SQL подмены DONE нет. Reverb-соединение в этом сценарии не используется и не заявлено успешным.

### Измеренные результаты

| Проверка | Результат |
|---|---|
| Soak: 40 samples/s, 20 зон × 10 каналов, 900 s | **36000/36000** уникальных samples, 36000 publisher PUBACK; duplicates=0, DLQ=0, eviction=0, projection mismatches=0; завершение 901.187 s |
| Повторный restart под отдельным 120 s потоком | **4800/4800**, без повторов/DLQ/eviction; 120.374 s |
| Координированный SIGKILL восьми core containers | Все процессы восстановлены; проверены HL/AE readiness, Laravel HTTP, bridge/aggregator HTTP endpoints |
| Незавершённая команда при restart | Та же task completed после позднего DONE; **ae_commands=1, observed command publishes=1**; весь recovery scenario **55 checks, 0 failed** |
| Агрегатор после восстановления | 5400 строк 1m, 400 строк 1h, 200 daily; watermark 1m продвигался |

Для финального coordinated restart сначала остановлен **только тестовый publisher** через SIGSTOP. После прекращения поступления данных выполнены SET + WAITAOF в **одном Redis connection** (подтверждено 1 local AOF copy) и запрос сохранения Mosquitto через SIGUSR1. Затем восемь контейнеров завершены параллельным SIGKILL, подняты infra и приложения, после readiness разрешены поздний device DONE и продолжение publisher. Конец SIGKILL → наблюдаемая готовность HTTP endpoints: около **10.127 s** на этом малом RAM-стенде. Это контролируемая persistence boundary, не доказательство нулевого RPO при произвольном отказе питания, диска или непрерывном поступлении сообщений. Redis остаётся `appendfsync everysec`; барьер относится только к этому испытанию.

Soak P99 от publish до первого SQL-наблюдения — 3391.543 ms; включает polling и restart. Для repeat load — 3203.285 ms. Это не чистая latency commit. RSS снимался отдельно в `stack-rss.json`; общий cgroup лимит Docker в этом окружении не позволяет трактовать `docker stats` как отдельную память каждого сервиса. 15 минут не заменяют многочасовое испытание на реальном workload.

### Физическое восстановление

`pg_basebackup -X stream --manifest-checksums=SHA256`, затем `pg_verifybackup` успешно проверили **физическую** base backup. После неё в source записаны marker-before, `pg_create_restore_point('hydro_audit_pitr_verified')`, затем marker-after; WAL архивирован. Отдельный PostgreSQL восстановлен через `restore_command`, `recovery.signal`, `recovery_target_name` и `recovery_target_action=promote`. Проверены: marker-before=1, marker-after=0, четыре hypertable, `pg_is_in_recovery()=false`. Приложения к восстановленному кластеру не подключались.

Первый запуск clone с max_connections=30 был отвергнут PostgreSQL: source использовал 80. После выравнивания до 80 восстановление прошло; этот предел добавлен в runbook. 0.720 s — время локального запуска/replay уже подготовленного clone, **не** полный production RTO, не время создания/переноса base backup. Данные и WAL размещались на временной RAM filesystem, отказ диска не моделировался.

Приватный артефакт: `/workspace/hydro-audit/build-artifacts/database/physical-pitr-fixture.tar.gz` (35447605 bytes; SHA256 в `stack-pitr-artifact.json`). Это синтетический DB cluster backup с WAL, не application backup и не production data.

### Изменения проверочных инструментов

`tools/ci/pipeline_smoke.py` теперь поддерживает отдельный каталог отчётов (`CI_PIPELINE_REPORT_DIR`) и opt-in handshake restart (`HYDRO_RESILIENCE_TEST=1`, `CI_PIPELINE_RECOVERY_DIR`, только hydro_test/hydro_e2e). Контролируемая точка — waiting_command; затем внешний test controller перезапускает core и создаёт файл `resume`. Test-only deadline команды увеличивается до 120 s. После restart открывается новый DB connection; DML автоматически не повторяется. Перед cleanup проверяются completed, один ae_commands и одна наблюдаемая публикация команды. Уникальный control directory не перезаписывается.

MQTTProbe тестового E2E runner теперь сбрасывает connected при disconnect, восстанавливает subscriptions с исходным QoS и возвращает publish receipt для проверки PUBACK. Добавлены регрессионные проверки: **6 MQTT probe tests passed**. Ruff F/E9 изменённых Python tools и `git diff --check` прошли. Product wire/schema/AE task types не менялись; production credentials/развёртывание не выполнялись.

Итоговая сводка: `/workspace/hydro-audit/stack-qualification-results.json`. Источники: `stack-soak.json`, `stack-restart-load.json`, `stack-full-restart-events.json`, `stack-recovery-control-v4/completed.json`, `stack-pipeline-{baseline,recovery}-reports/`, `stack-pitr-results.json`. `stack-soak-preflight.*` и ранние control directories — диагностические прогоны, не финальная квалификация. Остаются production rollout, длительная нагрузка с настоящим профилем данных и аппаратная приёмка (отложена пользователем); архитектурный backlog AE/frontend не закрыт этими тестами.


## Продолжение F15: декомпозиция AE worker и RecipeEditor

Первый этап разделения крупных модулей выполнен без изменения wire, API, DB schema,
FSM или task types:

- `ae3lite/runtime/lease_heartbeat.py`: продление lease с прежними transient retries,
  отдельным consecutive-failure budget для каждой зоны, исходным fencing token и
  сигналом потери владения до попытки отправить alert.
- `ae3lite/runtime/intent_sync.py`: bounded retry для running/terminal, отказ CAS,
  метрики и alert/resolution. Repository, clock, logger, limits и callbacks передаются
  явно. В worker остались связывание зависимостей, исполнение/отмена, finalization,
  lease release и reconcile. Размер worker: **1953 → 1745 строк**.
- `composables/recipePhaseFields.ts`: преобразования единиц полей, nullable crop
  inputs, day/night limits, EC preview.
- `composables/useRecipeIrrigation.ts`: общий режим полива фаз, выбор совместимого
  субстрата и обработка созданного значения. Размер RecipeEditor: **1874 → 1719
  строк**; template и style побайтно совпадают с исходной версией. API payload и
  существующее поведение выбора субстрата сохранены.

Добавлены 6 AE policy tests: изоляция failure budgets двух зон, сброс после успеха,
передача owner/generation и свежего времени при retry, сигнал lease lost при отказе
alert transport, отмена без повторов. Добавлены 10 frontend tests: единицы при
сериализации API payload, пустые значения и ноль, независимые day/night limits,
preview без изменения draft, переключение режимов/субстратов и замена модели формы.

Полный AE прогон обнаружил дефект **test cleanup**: удаление greenhouse обнуляло
`commands.zone_id` через SET NULL и оставляло фиксированные cmd_id; второй запуск
recovery suite получал UniqueViolation. В cleanup recovery integration теперь
удаляются только команды зон своей fixture до удаления greenhouse. Product cleanup
и схема БД не изменялись. Первый диагностический полный запуск также выявил
неполные mounts QA launcher (schemas/configs); launcher исправлен, эти результаты
не используются как успешная квалификация.

Frontend: **256 файлов, 1797 passed, 1 skipped**; typecheck, ESLint, API boundary и
production build прошли. Сохраняются предупреждения Rollup об аннотациях комментариев
в Zod; сборка завершена. Laravel AE3: **14 passed / 27 assertions**. Ruff F/E9 и
`git diff --check` прошли. Источники: `/workspace/hydro-audit/refactor-frontend*`,
`refactor-worker-focused.log` (29 passed), `refactor-laravel-ae3.log`.

Это начало F15, не завершение всей архитектурной переработки: остаются
`correction.py`, orchestration/reconcile worker, крупный шаблон RecipeEditor и
остальные legacy MQTT facades. Следующие выделения требуют своих поведенческих
проверок. Аппаратная приёмка по указанию пользователя отложена.

Финальная проверка AE на PostgreSQL 16.14 / TimescaleDB 2.28.2 в изолированной
internal Docker network: **1832 passed, без skips/errors**. После полного suite на
той же БД повторно прошли **30 recovery/crash/multi-instance/metrics tests** —
без сброса БД между прогонами. Это подтвердило исправление fixture cleanup.
JUnit: `refactor-ae.xml`, `refactor-recovery-repeat.xml`; итоговая сводка:
`/workspace/hydro-audit/refactor-results.json`. Перед финальным полным прогоном
отдельная hydro_test пересоздана Laravel `migrate:fresh` с включёнными TimescaleDB
миграциями; production/dev базы не использовались. Архив физического PITR сохранён
по прежнему пути, размер и SHA256 проверены; APK/firmware артефакты сохранены.


## Продолжение F15: post-dose observation и reconcile loop

Из `CorrectionHandler` выделен `application/services/correction_observation_reader.py`.
Reader получает monitor, summarizer, event callback и logger явно; данные task,
PID baseline и актуальная observation/process configuration передаются каждому
вызову отдельно. Он проверяет baseline до чтения telemetry, затем freshness,
устойчивость, sanity bounds и временной охват. Нет записи PID, публикации команд
или выбора следующей стадии. Результат — `ObservationWindow` или `ObservationRetry`.
Handler переводит каждый retry в прежний guarded outcome через
`_enter_correction_after_delay_or_interrupt`; stage deadline/probe budget остаются
на прежнем месте. Диагностические event payloads, suppression штатного накопления
samples и метрика out-of-bounds сохранены. Размер correction: **4038 → 3852 строк**.

В `runtime/reconcile_loop.py::ReconcileLoop` перенесены ordered callbacks, ожидание
wake-up, счётчик ошибок и backoff. Порядок шести проверок сохранён; исключение
пропускает оставшиеся проверки тика, следующий тик начинает с первой. Полный успех
сбрасывает ошибки; задержки после последовательных ошибок: обычный poll для первых
двух, затем 2/4/8/16/30 секунд с верхней границей 30. Wake-up прерывает и backoff,
отмена выходит без учёта как DB failure. Отдельные reconcile policies, ownership,
cleanup и execution lifecycle остаются в worker. Размер worker этого этапа:
**1745 → 1712 строк** (исходный до F15 — 1953).

Проверки в Docker, на изолированной `hydro_test` с PostgreSQL 16.14 / TimescaleDB
2.28.2 и схемой из Laravel migrations:

- **160 профильных тестов** прошли до и после извлечения модулей.
- **16 новых boundary tests**: baseline отсутствует/равен нулю, transport delay,
  stale/missing sensor, накопление окна без event spam, sanity bounds/future
  timestamps, отмена, конкурентные чтения двух зон; порядок reconcile steps,
  пропуск оставшихся steps при ошибке, backoff/reset, wake-up и отмена при polling.
- **Полный AE suite: 1848 passed**, без skips/errors (45.63 s).
- **Laravel AE3: 14 passed, 27 assertions**.
- Ruff F/E9 для изменённых исходников и новых тестов, `git diff --check` прошли.

Сводка — `/workspace/hydro-audit/f15-observation-results.json`; JUnit —
`f15-observation-ae.xml`, логи — `f15-observation-*.log`. Frontend этого этапа не
менялся, frontend suite повторно не запускался. Исправлена устаревшая внутренняя
докстрока finalize: EC feedforward bias сохраняется до следующей pH dose, как и в
прежнем коде. Обновлены canonical module map/correction spec и локальный AGENT.md.
FSM, wire/API, DB schema и authority matrix не менялись.

Следующие части F15: dose routing/accounting и observation finalization в correction,
затем оставшиеся worker reconciliation policies/execution lifecycle. Перенос
целого handler в mixin и новые Python-сервисы не вводились. Production rollout и
аппаратная приёмка не выполнялись; аппаратные тесты остаются отложенными.


## Продолжение F15: dose routing и accounting helpers

Выделены два модуля:

- `domain/services/correction_dose_routing.py`: чистый `route_dose_plan` возвращает
  immutable `RoutedDose` с новым correction snapshot, selected action и decision
  reason. Приоритет pending pH после EC observation, EC-first нового dual plan,
  порядок multi-EC компонентов и JSON shapes single/multi EC/clamped pH сохранены.
  Модуль не выполняет команд, не обращается к БД и не пишет PID.
- `application/services/correction_dose_accounting.py`: выбор component/generic
  calibration, извлечение response details по индексу batch, согласование объёма
  через прежний domain feedback resolver и post-persist accounting marker.
  Callback маркера передаётся явно; только DONE dose с ae_command_id проходит
  фильтр. Ошибка записи логируется и не скрывает последующие элементы batch;
  отмена прерывает обработку. Нет автоматического retry с побочными эффектами.

В handler остались safety/control-mode/flow-hold, cooldown/discard/attempt gates,
запись plan PID только после подтверждения маршрута, physical execution, partial
EC batch handling и completion-anchored hold windows. Порядок DONE → PID persist →
accounting marker сохранён; при ошибке PID marker не вызывается. Наличие PID repo
и получение marker callback пока проверяет handler adapter через прежние
интерфейсы; это не объявляется завершённой декомпозицией execution dependencies.
Terminal repair и его идемпотентность не менялись. Неиспользуемый private wrapper
response-details удалён; per-component calibration adapter сохранён для текущих
handler integration fixtures. Размер correction этого этапа: **3852 → 3715 строк**
(до начала F15 — 4038).

Проверки:

- **122 профильных теста** до и после начального выделения модулей.
- После переноса feedback adapter: **140 профильных тестов**, включая **18 новых**.
  Проверены priority/direction, snapshot без изменения исходного corr, порядок и
  requested/effective metadata, calibration/fallback, feedback нужного batch
  элемента и ограничение effective volume планом, DONE filtering, отказ marker и
  отмена без учёта последующих команд. Существующие handler tests покрывают PID
  persist failure без marker, partial EC batch и обратную связь дозы в observe.
- **Полный AE suite: 1866 passed, без skips/errors** (46.33 s).
- **Laravel AE3: 14 passed / 27 assertions**.
- Ruff F/E9 новых модулей/тестов и изменённого handler, `git diff --check` прошли.

Все backend/Python проверки выполнены в Docker. Для полного suite использована
отдельная `hydro_test` с Laravel migrations, PostgreSQL 16.14 / TimescaleDB 2.28.2,
в internal Docker network без опубликованных портов. Первая попытка миграции
попала в запуск PostgreSQL (connection refused); после положительного pg_isready
миграции прошли. Диагностический `f15-dose-migrations-not-ready.log` не является
успешной квалификацией. Профильный baseline проверяет handler fixtures; итоговый
full suite включает настоящие SQL/recovery tests на мигрированной БД.

Сводка: `/workspace/hydro-audit/f15-dose-results.json`; JUnit:
`f15-dose-ae.xml`; логи: `f15-dose-*.log`. Обновлены module map, correction spec и
локальный AGENT.md. Wire/API, DB schema, FSM, authority matrix и task types не
менялись. Frontend этого этапа не затрагивался. Аппаратная приёмка и production
rollout не выполнялись.

Следующие части F15: observation finalization и оставшаяся dose execution/
partial-batch orchestration, затем worker execution/reconcile policies.


## Продолжение F15, 2026-11-15: observation finalization

`application/services/correction_observation_finalizer.py` содержит stateless
вычисления готового post-dose окна:

- `evaluate_observation`: expected/peak/tail/learning effect, next no-effect count,
  прежний payload `CORRECTION_OBSERVATION_EVALUATED`; missing process gain или dose
  сохраняют `corr_process_gain_missing`.
- `build_observation_pid_update`: integral freeze (`accumulate_integral=False`),
  measurement/D-clock и adaptive stats; сама запись в БД остаётся в handler.
- `correction_after_observation`: no-effect/reaction attempt policy, очистка
  завершённой дозы и сохранение pending dose противоположного контура.

Порядок awaits/побочных эффектов в handler не менялся: evaluated event → PID
persist → no-effect limit/outcome → следующий state. Helpers не содержат I/O,
командного gateway или repository. Сохранены использование peak вместо tail для
no-effect, отсутствие learning inflation на нулевом отклике, EC→pH feedforward
bias и conditional reset policy. Неиспользуемый `_expected_effect` wrapper удалён;
ошибка конфигурации переводится в прежний TaskExecutionError внутри evaluator.
Размер correction этого этапа: **3715 → 3570 строк** (до начала F15 — 4038).

Проверки:

- **145 профильных сценариев** до и после выделения вычислений.
- **16 новых boundary checks**: затухшая волна с сохранённым peak effect, equality
  threshold, fail-closed missing gain/dose, integral freeze/no learning inflation,
  неизменность входного PID snapshot, противоположная pending dose, reset/no-effect
  counters; порядок event/persist/limit, исключение callback, ошибка PID и отмена.
- Обычный отказ observability sink по-прежнему подавляется CorrectionEventLogger
  с warning/метрикой и не мешает PID/state progress; это проверено отдельно.
  Исключение из callback или PID persist прерывает дальнейшие операции.
- **Полный AE suite: 1882 passed, без skips/errors** (48.65 s).
- **Laravel AE3: 14 passed / 27 assertions**.
- Ruff F/E9 новых модулей/тестов и изменённого handler/test, `git diff --check` прошли.

RAM-кеш стенда оказался очищен между датами. Python runtime восстановлен из
существующего Docker image; официальные PHP/TimescaleDB OCI layers повторно
проверены SHA256 и извлечены в RAM. Для PHP восстановлены PostgreSQL/Redis и другие
прежние extensions. Chroot-only launch adapters (argv/uid switch/init password
file), DNS/hosts, CA bundle и canonical error catalogs восстановлены только в QA
runtime. Первый диагностический полный прогон выявил старый DNS; следующий —
пустой fallback error catalog из launcher image. Каталог заменён canonical
`backend/error_codes.json`. Laravel diagnostic выявил отсутствующее Redis extension;
после восстановления 6.3.0 suite прошёл. Product-код этим восстановлением не менялся.

Финальный AE запуск выполнен в Docker/internal network, на чистой `hydro_test`
после Laravel `migrate:fresh` с APP_ENV=e2e; предварительно проверены оба JSON
catalogs, DNS/SQL и четыре hypertables. Версии: PostgreSQL 16.14 / TimescaleDB 2.28.2,
PHP 8.2.35. Для сборки extensions PHP временно имел build network; перед итоговыми
Laravel checks оставлена только internal network. Опубликованных портов и
физических устройств не было. Диагностические неуспешные логи исключены из
итогового подтверждения; их список — в `f15-finalize-results.json`.

Сводка: `/workspace/hydro-audit/f15-finalize-results.json`; JUnit:
`f15-finalize-ae.xml`; итоговые логи — `f15-finalize-ae-full.log`,
`f15-finalize-laravel-ae3.log`, `f15-finalize-boundaries.log`. Обновлены module map,
correction spec и локальный AGENT.md. Wire/API, DB schema, FSM и authority matrix
не менялись. Frontend и устройства не затрагивались.

Далее по F15: оставшаяся dose execution/partial-batch orchestration в correction,
затем execution/reconcile policies worker. Аппаратная приёмка остаётся отложенной.


## Продолжение F15, 2026-11-15: EC execution и partial-batch policy

В `application/services/correction_ec_dose_executor.py` выделены прежний разбор EC
sequence JSON и `CorrectionEcDoseExecutor`. Зависимости — явные callbacks dispatch,
partial failure policy, error mapping, calibration, feedback и node selection.
Task/plan/corr, sequence и локальный dose context передаются каждому вызову отдельно;
между вызовами сервис не хранит их состояние. Физические команды по-прежнему идут
через прежний gateway/history-logger, прямого MQTT или нового retry loop нет.

- Single dose использует прежний checked path.
- Multi-sequential исполняет один компонент за вызов, сохраняет next index и
  подтверждённые volume/duration; completed index не отправляет дозы заново.
- Logical multi-parallel передаёт один упорядоченный batch существующему gateway,
  который ждёт DONE каждой команды перед следующей. Физическая параллельная
  публикация не добавлена.
- Ранний StageOutcome и актуальный task override сохраняются при промежуточном
  шаге и частичном отказе. Отмена не превращается в retry/partial/success.

`domain/services/ec_batch_failure.py` содержит чистые failed-index/partial rules
и descriptor successful/failed/remaining компонентов. Сохранены bounds индекса,
нормализация имён и prior-success эвристика. Poll deadline остаётся вне partial
classification и проходит прежний failure path. Событие EC_BATCH_PARTIAL_FAILURE,
metric и failure transition остаются в handler; runtime/config/sensor authority,
post-dose aggregation, PID persistence, markers и hold clocks тоже не перенесены.
Убраны дублированные private classifier wrappers и лишняя инициализация result.
Размер correction этого этапа: **3570 → 3286 строк** (до начала F15 — 4038).

Проверки в Docker:

- **123 профильных теста** до и после переноса: handler + multi-dose + enriched
  handler integration fixtures, включая текущие partial-failure paths.
- **25 новых boundary checks**: один resume component за вызов, completed skip,
  ограниченный feedback до requeue, command payload/step order, logical batch,
  single checked path, task override, partial outcome, deadline/error propagation,
  cancellation без retry, некорректный JSON, metadata compatibility, partitions
  classifier и независимые concurrent task contexts общего executor.
- **Полный AE suite: 1907 passed, без skips/errors** (43.88 s).
- **Laravel AE3: 14 passed / 27 assertions**.
- Ruff F/E9 новых модулей/тестов и изменённого handler, `git diff --check` прошли.

Использованы сохранённые QA runtimes, internal Docker network без опубликованных
портов и отдельная hydro_test, подготовленная Laravel migrations. Перед полным
suite проверены DNS/SQL, JSON catalogs и четыре Timescale hypertables; PostgreSQL
16.14 / TimescaleDB 2.28.2. Production/dev базы и устройства не использовались.
Эти проверки подтверждают программные границы; аппаратная приёмка по указанию
пользователя остаётся отложенной.

Сводка — `/workspace/hydro-audit/f15-ec-results.json`; JUnit — `f15-ec-ae.xml`;
логи — `f15-ec-{baseline,after,boundaries,ae-full,laravel-ae3}.log`. Canonical module
map, correction spec и локальный AGENT.md обновлены. Wire/API, DB schema, FSM,
authority matrix и task types не менялись; frontend не затрагивался.

Следующие части F15: pH/dilute execution и post-dose orchestration, затем оставшиеся
execution/reconcile policies worker. Декомпозиция всего handler не объявляется
завершённой.

## Полная декомпозиция AE3, 2026-11-15

По запросу пользователя последовательная декомпозиция AE3 завершена в пределах
существующего runtime: stage handlers и correction, worker/recovery/execution,
planners/config, task creation/workflow/state UI, SQL repositories/read models,
command gateway, HTTP API, greenhouse climate и interruption safety. Каноническая
карта владельцев реализации — `doc_ai/04_BACKEND_CORE/ae3lite.md`, §11.2.

Компоненты используют явные frozen `*Ports` и текущий task/plan/time. Нет mixins,
передачи целого handler/worker в helpers, изменений globals чужого модуля или
новых процессов/task types. Mutable worker/recovery state изолирован на экземпляр.
Ленивые read/config adapters совместимы с подклассами без `super().__init__` и
кешируют только экземпляр компонента, сохраняя актуальность плана/SQL/clock.
Климатические фазы возвращают типизированные records; запрос к dose planner —
immutable `CorrectionDoseRequest`. Реестр топологий, Pydantic-схемы, каталог SQL
schema и определения метрик сохранены цельными как декларативные модули.

Сохранены исходные транзакции/advisory locks, claim generation, lease ownership,
fail-safe pump-first/fan-out, дозирование/recovery без повторной подтверждённой
дозы, temporal windows и fail-closed решения. Public imports/signatures, ingress,
FSM и HTTP/event/MQTT/DB контракты не расширялись. Публикация команд — через HL.

### Размеры точек сборки

Цифры сравнивают начало полного этапа с текущим кодом; размер фасада включает
явное wiring и совместимые методы, а не перенесённую бизнес-логику. Число строк
не использовалось как критерий завершённости или улучшения производительности.

| Модуль внутри `ae3lite/` | До | После |
|---|---:|---:|
| `api/compat_endpoints.py` | 927 | 302 |
| `application/handlers/base.py` | 2180 | 832 |
| `application/handlers/correction.py` | 3286 | 1307 |
| `application/handlers/irrigation_check.py` | 682 | 225 |
| `application/handlers/solution_fill.py` | 651 | 194 |
| `application/services/automation_observability.py` | 504 | 29 |
| `application/services/correction_interrupt_safety.py` | 1137 | 434 |
| `application/services/stage_runtime_config.py` | 626 | 213 |
| `application/use_cases/create_task_from_intent.py` | 723 | 226 |
| `application/use_cases/execute_task.py` | 1831 | 588 |
| `application/use_cases/get_zone_automation_state.py` | 1452 | 483 |
| `application/use_cases/startup_recovery.py` | 1408 | 519 |
| `application/use_cases/workflow_router.py` | 1161 | 524 |
| `config/runtime_plan_builder.py` | 1431 | 79 |
| `domain/services/correction_planner.py` | 1957 | 525 |
| `domain/services/cycle_start_planner.py` | 1082 | 322 |
| `domain/services/zone_node_availability.py` | 617 | 362 |
| `greenhouse_climate/run_tick.py` | 1491 | 592 |
| `infrastructure/gateways/sequential_command_gateway.py` | 1307 | 449 |
| `infrastructure/read_models/zone_runtime_monitor.py` | 802 | 241 |
| `infrastructure/read_models/zone_snapshot_read_model.py` | 1037 | 290 |
| `infrastructure/repositories/ae_command_repository.py` | 748 | 300 |
| `infrastructure/repositories/automation_task_repository.py` | 1610 | 699 |
| `infrastructure/repositories/zone_intent_repository.py` | 912 | 307 |
| `runtime/app.py` | 1119 | 413 |
| `runtime/worker.py` | 1712 | 795 |

### Проверки завершения

- Полный AE suite в Docker: **1912 passed** (44.81 s), без skip/xfail.
- Laravel AE3 feature/integration: **14 passed / 27 assertions**.
- Отдельный software pipeline smoke: **54 checks passed** — реальный Laravel
  `ScheduleDispatcher` → intent → AE → HL → MQTT, проверка HMAC программным
  ответчиком, MQTT `DONE`, task/intent completed, internal task status 200.
- Crash/recovery smoke: **55 checks passed** — `SIGKILL` только AE при
  `waiting_command`, запуск того же исходного кода, release позднего `DONE`
  после readiness; та же task completed, **ae_commands=1, MQTT publishes=1**.
- Профильный финальный correction/day-night/pipeline: **455 passed**;
  дополнительные architecture/ownership checks: **5 passed** (входят в полный AE suite).
- Ruff F/E9 по всему automation-engine и `git diff --check` прошли.
  Прямой top-level граф imports ацикличен; форматирование фасадов отдельно
  проверено сравнением AST до/после.

Логи/XML/JSON — `/workspace/hydro-audit/f15-full-final*`,
`f15-full-laravel.log`, `f15-full-pipeline*`, `f15-full-recovery*`.
Успешные E2E отчёты — `f15-full-pipeline-reports` и
`f15-full-recovery-reports`; журналы неудачной подготовки launcher не являются
квалификацией runtime. Для smoke, из-за ограниченного диска, PHP/AE/HL/MQTT
размещены в одном временном test launcher с отдельными процессами и настоящими
HTTP/MQTT; PostgreSQL/TimescaleDB и Redis — отдельные контейнеры, сеть internal,
без host ports. Это проверка текущего source/runtime, не production image build.
Restart smoke перезапускал AE, не весь core stack; предыдущие full-stack restart
и soak результаты приведены отдельно выше.

QA-стенд после проверки удалён. Сохранены APK, восемь firmware archives,
`firmware-all.zip` и physical PITR fixture; SHA256 последнего повторно совпал
с ранее зафиксированным значением. Source `.env` и production credentials
не менялись.

Два source-guard теста snapshot freshness смотрят на реального владельца SQL
`zone_snapshot_loader`, сохраняя прежние assertions. Добавлены проверки
ацикличности прямых imports, per-instance worker state, ленивых snapshot
компонентов в подклассе, свежего runtime plan при повторном использовании
компонента и явных clock/timezone day/night.

При общих прогонах исправлены две регрессии извлечения: virtual override
publish-only gateway и подмена clock day/night. Они не скрыты skip/xfail;
проверки старого поведения продолжают выполняться. Hardware tests по указанию
пользователя отложены. Ранее выполненные frontend/MQTT/firmware/PITR/soak
проверки не выдаются за повторные прогоны этого этапа. Deployment/commit/push
не выполнялись; внешние F15 frontend/MQTT задачи остаются вне полного AE3 scope.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.


## Завершение F15: RecipeEditor и MQTT/telemetry, 2026-11-15

RecipeEditor разделён на identity/preview/phase coordinator и шесть групп полей;
форма сохранена общей и reactive. Справочники/loading, чистая validation и draft
revision persistence выделены из useRecipeEditor. Сохранены поля/testid/role UX,
clone mapping, порядок CRUD/publish и привязка active cycles к прежней revision.
Карта реализации — `FRONTEND_ARCH_FULL.md`, §3.0a.

HL facades больше не меняют `fetch`, metrics и callbacks соседних модулей.
MQTT, telemetry и command scopes используют immutable snapshots с восстановлением
после вложенных вызовов и исключений. Telemetry monolith разделён на 11 компонентов
с frozen ports; batch coordinator связывает resolution/normalization/persistence/
selective outcomes/realtime. Cache/backoff state остаётся у runtime-владельца и
передаётся явными accessors. SQL/Redis admission/ACK порядок, monotonic projection,
FK invalidation, shutdown/drain, HTTP/MQTT payload и единственная публикация через
HL не изменены. Новых процессов/schema/task types не добавлено.

При извлечении sensor resolution один тест обнаружил потерю global cache
invalidation. Исправлен явный setter владельца; исходный assertion сохранён.
Command dependency scope дополнительно сбрасывается после возврата/ошибки:
предыдущая привязка оставалась в coroutine context после завершения route helper.

### Завершённые программные проверки

- Frontend: **1797 passed, 1 прежний skipped**, 256 файлов; typecheck, ESLint,
  API boundary и production Vite build прошли. Четыре новых composition tests
  проверяют сортировку/удаление фазы, сохранение edits при смене режима,
  передачу создания substrate и plant. Установленные зависимости не менялись.
- HL: **335 passed**; common: **316 passed**; MQTT bridge: **17 passed**.
  Новые проверки перекрытия, вложенности и exceptions выполняются без замены
  underlying module globals. Два warnings Starlette/httpx/AnyIO остаются прежними.
- AE3: **1912 passed**. Laravel Recipe/ScheduleDispatcher/Ae3Lite filter:
  **114 passed / 488 assertions**.
- Реальный TLS/ACL broker: **8 passed** (production password gate, per-node
  namespace, запрет command writes узлам, TLS-only, untrusted CA rejection).
- Pipeline: **54 checks passed**. AE SIGKILL/restart при waiting_command:
  **55 checks passed**, та же task completed, **ae_commands=1, MQTT publishes=1**.

### Нагрузка и образы

Реальный программный стенд: PostgreSQL 16/TimescaleDB, Redis AOF/noeviction,
MQTT, Laravel HTTP/scheduler и четыре Python runtime. Синтетические 20 зон × 10
каналов, без физических узлов. Из-за ограничений диска сервисы выполнялись
отдельными процессами в одном QA launcher с реальными HTTP/MQTT/SQL, поэтому
результаты подтверждают source runtime, а не изоляцию production images.

| Профиль | Результат | Наблюдаемая p95/p99 задержка |
|---|---|---|
| 30 минут, 40 samples/s | 72 000/72 000 PUBACK и unique SQL rows | 1230 / 1382 ms |
| 20 секунд, 1000 samples/s | 20 000/20 000 PUBACK и unique SQL rows | 1487 / 1720 ms |
| 120 секунд, 40 samples/s; SIGKILL HL и PostgreSQL | 4800/4800 PUBACK и unique SQL rows | 16 288 / 21 036 ms, включая outages |

В каждом профиле: duplicates=0, projection mismatches=0, финальные queue/processing/
DLQ=0, Redis evictions=0, HL readiness=200. SQL polling наблюдателя раз в секунду
входит в задержки; это не измерение чистой commit latency. В fault-профиле
публикация продолжалась: HL остановлен ~на 10 секунд, затем PostgreSQL ~на 10
секунд; HL перезапущен с прежним persistent MQTT client ID, БД — с прежними данными.

30-минутный профиль включал **5.963 s quiesced-producer graceful restart HL/PHP**
для переноса интенсивных тестовых журналов в RAM при нехватке диска. Все прежние
байты журналов перед усечением сохранены и SHA256 проверены; это не заявляется
как непрерывный healthy soak. Финальные и исходные журналы перенесены из volatile
mounts в `build-artifacts/diagnostics/f16`, пять gzip archives с SHA256 manifest.

Финальный контроль всего набора: **96 800 samples = 96 800 unique sequence IDs**,
диапазон 1…96 800, 200 sensors/projections, 6978 минутных и 400 часовых aggregate
rows, четыре Timescale hypertables; Laravel/HL/AE/bridge/aggregator endpoints=200.
RSS snapshots с 14:51 до 15:18 UTC охватывают оставшуюся часть soak, burst и faults:
peaks HL 90 692 KiB, AE 82 788 KiB, bridge 63 612 KiB, aggregator 35 728 KiB.
Это ограниченный прогон, не доказательство отсутствия длительных memory leaks.
После финальной явной маркировки compatibility re-exports и удаления двух мёртвых
локальных значений HL повторно: **335 passed**; Ruff F/E9 и release tool lint прошли.

Production Docker images **не квалифицированы**. Primary/nested Docker отказал
из-за отсутствующей cgroup delegation. В отдельном rootless BuildKit с native
snapshotter исходный `history-logger/Dockerfile` прошёл `apt-get`, но `pip` отверг
CA managed proxy (`CERTIFICATE_VERIFY_FAILED`). TLS verification не отключалась,
продуктовые Dockerfiles ради окружения не менялись. Image IDs/artifacts готовой
release-сборки не получены; ошибки и статус сохранены в `f16-image-build-status.json`
и build logs. Для закрытия этапа нужен runner с рабочим Docker и доверенным CA.


Созданы manual CI workflow `release-qualification.yml` и
`tools/ci/qualify_release_images.py`: пять production Dockerfile builds,
три infra images, private logs/manifest, optional image archive; никаких push/deploy.
План и parsing workflow проверены; недоступный Docker daemon даёт failed manifest
и ненулевой exit, без ложной отметки built. Workflow извне не запускался.

Логи/XML/JSON этого этапа: `/workspace/hydro-audit/f16-*`. Файлы с ошибками
подготовки stand/run namespace не являются успешной квалификацией приложения.
Тесты выполнялись без физических устройств; production secrets/APP_KEY и source
.env не менялись. Deployment target/канал и реальный inventory узлов не заданы.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.


## Проверки перед слиянием в main, 2026-11-15

PR #40 запускает полный ci, Protocol Contract Tests и security/chaos workflow.
Первый запуск Composer audit выявил новый advisory PKSA-yxbx-3c9s-cjt9 /
CVE-2026-128083 (Concurrency Process task output injection). В composer.lock
обновлён только `laravel/framework`: 12.70.2 → 12.71.0. Constraint `^12.0`
сохранён, остальные пакеты не менялись. Update и `composer audit --locked`
выполнены в Docker с проверкой CA; после обновления advisories нет. Полный CI
повторно проверяет новый lock-файл; ни одна проверка безопасности не отключена.
