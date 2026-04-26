<?php

namespace App\Console\Commands;

use App\Models\Zone;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * Прогнать полную калибровку Digital Twin для всех активных зон.
 *
 * Делает HTTP-запрос на digital-twin /v1/calibrate/zone/{id}?days=N&persist=true.
 * digital-twin сам отвечает за чтение истории и persist в zone_dt_params.
 *
 * Используется в scheduler как ежесуточная задача.
 */
class DigitalTwinCalibrateAll extends Command
{
    protected $signature = 'digital-twin:calibrate-all '
        . '{--days=7 : Сколько дней истории использовать} '
        . '{--zone= : Калибровать только указанную зону} '
        . '{--persist=1 : Сохранять ли результат в zone_dt_params (1/0)}';

    protected $description = 'Прогон калибровки Digital Twin для всех активных зон';

    public function handle(): int
    {
        $days = max(1, (int) $this->option('days'));
        $persist = (bool) (int) $this->option('persist');
        $zoneFilter = $this->option('zone');

        $baseUrl = Config::get('services.digital_twin.base_url', 'http://digital-twin:8003');
        $token = Config::get('services.digital_twin.token');

        $query = Zone::query()->whereNull('deleted_at');
        if ($zoneFilter !== null && $zoneFilter !== '') {
            $query->where('id', (int) $zoneFilter);
        }
        $zones = $query->get(['id', 'uid', 'name']);

        if ($zones->isEmpty()) {
            $this->warn('No active zones found.');
            return self::SUCCESS;
        }

        $okCount = 0;
        $failCount = 0;

        foreach ($zones as $zone) {
            $url = rtrim($baseUrl, '/') . "/v1/calibrate/zone/{$zone->id}";
            $this->info("Calibrating zone={$zone->id} ({$zone->name})...");

            try {
                $request = Http::timeout(120);
                if ($token) {
                    $request = $request->withToken($token);
                }
                $response = $request->post($url, [], [
                    'days' => $days,
                    'persist' => $persist ? 'true' : 'false',
                ]);
            } catch (\Throwable $e) {
                $failCount++;
                $this->error("  Connection error: {$e->getMessage()}");
                Log::warning('digital-twin calibrate connection error', [
                    'zone_id' => $zone->id,
                    'error' => $e->getMessage(),
                ]);
                continue;
            }

            if ($response->successful()) {
                $okCount++;
                $data = $response->json('data') ?? [];
                $persisted = $data['persisted'] ?? [];
                $this->info("  OK; persisted=" . count($persisted));
            } else {
                $failCount++;
                $this->error("  HTTP {$response->status()}: {$response->body()}");
                Log::warning('digital-twin calibrate failed', [
                    'zone_id' => $zone->id,
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);
            }
        }

        $this->newLine();
        $this->info("Done. ok={$okCount}, failed={$failCount}");
        return $failCount === 0 ? self::SUCCESS : self::FAILURE;
    }
}
