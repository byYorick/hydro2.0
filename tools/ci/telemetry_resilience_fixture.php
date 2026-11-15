<?php
// Synthetic data only. Run with Laravel dependencies inside its test container.
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\DB;

try {
    require (getenv('HYDRO_APP_ROOT') ?: '/app').'/vendor/autoload.php';
    $app = require (getenv('HYDRO_APP_ROOT') ?: '/app').'/bootstrap/app.php';
    $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

    $database = DB::getDatabaseName();
    $output = $argv[1] ?? '';
    if (getenv('HYDRO_RESILIENCE_TEST') !== '1' || ! app()->environment('testing') ||
        ($database !== 'hydro_test' && ! str_starts_with($database, 'hydro_resilience_test')) ||
        $output === '' || file_exists($output)) {
        throw new RuntimeException('Requires an isolated testing database and a new output path.');
    }
    umask(0077);
    $fixtures = Model::withoutEvents(fn () => DB::transaction(function () {
        if (Greenhouse::where('uid', 'gh-resilience')->exists()) {
            throw new RuntimeException('Use a fresh test database; existing fixture is not overwritten.');
        }
        $greenhouse = Greenhouse::factory()->create(['uid' => 'gh-resilience']);
        $fixtures = [];
        for ($index = 0; $index < 20; $index++) {
            $zone = Zone::factory()->create([
                'uid' => 'zn-resilience-'.$index,
                'greenhouse_id' => $greenhouse->id,
                'status' => 'online',
            ]);
            $node = DeviceNode::factory()->create([
                'uid' => 'nd-resilience-'.$index,
                'zone_id' => $zone->id,
                'type' => 'ph',
                'status' => 'online',
            ]);
            $fixtures[] = [
                'greenhouse_uid' => $greenhouse->uid,
                'zone_uid' => $zone->uid, 'zone_id' => $zone->id,
                'node_uid' => $node->uid, 'node_id' => $node->id,
            ];
        }
        return $fixtures;
    }));
    if (file_put_contents($output, json_encode($fixtures, JSON_THROW_ON_ERROR)) === false) {
        throw new RuntimeException('Unable to write fixture manifest.');
    }
    echo "Created 20 synthetic zones without automation tasks or commands.\n";
} catch (Throwable) {
    fwrite(STDERR, "Fixture rejected or failed: check isolated testing database and a new output path.\n");
    exit(1);
}
