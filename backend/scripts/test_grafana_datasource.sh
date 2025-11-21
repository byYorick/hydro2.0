#!/bin/bash
# Скрипт для проверки подключения PostgreSQL datasource в Grafana

echo "=== Проверка данных в БД ==="
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "
SELECT 
    'Alerts (ACTIVE)' as metric, 
    COUNT(*) as count 
FROM alerts 
WHERE UPPER(status) = 'ACTIVE'
UNION ALL
SELECT 
    'Commands (total)', 
    COUNT(*) 
FROM commands
UNION ALL
SELECT 
    'Telemetry (last 24h)', 
    COUNT(*) 
FROM telemetry_samples 
WHERE ts >= NOW() - INTERVAL '24 hours'
UNION ALL
SELECT 
    'Zone Events (last 24h)', 
    COUNT(*) 
FROM zone_events 
WHERE created_at >= NOW() - INTERVAL '24 hours'
UNION ALL
SELECT 
    'Nodes (online)', 
    COUNT(*) 
FROM nodes 
WHERE status = 'online';
"

echo ""
echo "=== Тест запросов из dashboards ==="

echo "1. Alerts Dashboard - Active Alerts:"
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT COUNT(*) FROM alerts WHERE UPPER(status) = 'ACTIVE';"

echo "2. Commands Dashboard - Commands by Status:"
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT status, COUNT(*) FROM commands GROUP BY status;"

echo "3. Node Status - Nodes:"
docker exec backend-db-1 psql -U hydro -d hydro_dev -c "SELECT status, COUNT(*) FROM nodes GROUP BY status;"

echo ""
echo "=== Проверка подключения PostgreSQL ==="
echo "Проверьте в Grafana UI: Configuration → Data Sources → PostgreSQL → Test"

