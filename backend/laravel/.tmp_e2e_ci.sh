#!/bin/bash
set -e

cp .env.example .env
php artisan key:generate --no-interaction
composer install --no-interaction --prefer-dist --optimize-autoloader
npm ci --legacy-peer-deps
npm run build
php artisan config:clear
php artisan cache:clear
php artisan config:cache

php -r "require __DIR__.'/vendor/autoload.php'; \$app = require __DIR__.'/bootstrap/app.php'; \$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap(); \$statements = [ 'DROP VIEW IF EXISTS telemetry_raw', \"SELECT drop_hypertable('telemetry_samples', if_exists => TRUE)\", \"SELECT drop_hypertable('telemetry_agg_1m', if_exists => TRUE)\", \"SELECT drop_hypertable('telemetry_agg_1h', if_exists => TRUE)\", \"SELECT drop_hypertable('commands', if_exists => TRUE)\", \"SELECT drop_hypertable('zone_events', if_exists => TRUE)\" ]; foreach (\$statements as \$sql) { try { Illuminate\\Support\\Facades\\DB::statement(\$sql); } catch (Throwable \$e) { fwrite(STDERR, '[ci] '.\$e->getMessage().PHP_EOL); } }"

php artisan migrate:fresh --force &
MIGRATE_PID=$!
php artisan serve --host=127.0.0.1 --port=8000 --env=testing &
SERVE_PID=$!

wait $MIGRATE_PID || true
php artisan db:seed --class=AdminUserSeeder --force

max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
  attempt=$((attempt + 1))
  if curl -f -s http://127.0.0.1:8000 > /dev/null 2>&1; then
    break
  fi
  sleep 1
done
if [ $attempt -eq $max_attempts ]; then
  echo "ERROR: Server failed to start after $max_attempts attempts"
  exit 1
fi

npx playwright install --with-deps
npx playwright test --reporter=list,html
