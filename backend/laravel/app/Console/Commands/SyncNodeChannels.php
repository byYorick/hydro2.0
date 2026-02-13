<?php

namespace App\Console\Commands;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use Illuminate\Console\Command;

class SyncNodeChannels extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'nodes:sync-channels 
                            {--node-uid= : Sync channels for specific node UID}
                            {--all : Sync channels for all nodes}
                            {--dry-run : Show what would be done without making changes}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Sync node channels based on node type and capabilities';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        $nodeUid = $this->option('node-uid');
        $all = $this->option('all');
        $dryRun = $this->option('dry-run');

        if (! $nodeUid && ! $all) {
            $this->error('Please specify either --node-uid=<uid> or --all');

            return Command::FAILURE;
        }

        $query = DeviceNode::query();

        if ($nodeUid) {
            $query->where('uid', $nodeUid);
        }

        $nodes = $query->get();

        if ($nodes->isEmpty()) {
            $this->warn('No nodes found');

            return Command::SUCCESS;
        }

        $this->info("Found {$nodes->count()} node(s) to process");
        if ($dryRun) {
            $this->warn('DRY RUN MODE - No changes will be made');
        }

        foreach ($nodes as $node) {
            $this->processNode($node, $dryRun);
        }

        return Command::SUCCESS;
    }

    private function processNode(DeviceNode $node, bool $dryRun): void
    {
        $this->info("Processing node: {$node->uid} (type: {$node->type})");

        // Определяем capabilities на основе типа узла
        $capabilities = $this->getCapabilitiesForNodeType($node->type);

        if (empty($capabilities)) {
            $this->warn("  No default capabilities for type '{$node->type}', skipping");

            return;
        }

        $this->line('  Capabilities: '.implode(', ', $capabilities));

        // Маппинг capability -> channel configuration
        $capabilityConfig = [
            'temperature' => ['type' => 'sensor', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
            'humidity' => ['type' => 'sensor', 'metric' => 'HUMIDITY', 'unit' => '%'],
            'co2' => ['type' => 'sensor', 'metric' => 'CO2', 'unit' => 'ppm'],
            'lighting' => ['type' => 'actuator', 'metric' => 'LIGHT', 'unit' => ''],
            'ventilation' => ['type' => 'actuator', 'metric' => 'VENTILATION', 'unit' => ''],
            'ph_sensor' => ['type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
            'ec_sensor' => ['type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
            'pump_A' => ['type' => 'actuator', 'metric' => 'PUMP_A', 'unit' => ''],
            'pump_B' => ['type' => 'actuator', 'metric' => 'PUMP_B', 'unit' => ''],
            'pump_C' => ['type' => 'actuator', 'metric' => 'PUMP_C', 'unit' => ''],
            'pump_D' => ['type' => 'actuator', 'metric' => 'PUMP_D', 'unit' => ''],
        ];

        $created = 0;
        $updated = 0;
        $skipped = 0;

        foreach ($capabilities as $capability) {
            $config = $capabilityConfig[$capability] ?? [
                'type' => 'sensor',
                'metric' => strtoupper($capability),
                'unit' => '',
            ];

            $existing = NodeChannel::where('node_id', $node->id)
                ->where('channel', $capability)
                ->first();

            if ($existing) {
                $this->line("    ✓ Channel '{$capability}' already exists");
                $skipped++;

                continue;
            }

            if ($dryRun) {
                $this->line("    [DRY RUN] Would create channel '{$capability}' ({$config['type']}, {$config['metric']})");
                $created++;
            } else {
                NodeChannel::create([
                    'node_id' => $node->id,
                    'channel' => $capability,
                    'type' => $config['type'],
                    'metric' => $config['metric'],
                    'unit' => $config['unit'],
                    'config' => [],
                ]);
                $this->line("    ✓ Created channel '{$capability}' ({$config['type']}, {$config['metric']})");
                $created++;
            }
        }

        $this->info("  Summary: Created={$created}, Skipped={$skipped}");
    }

    private function getCapabilitiesForNodeType(string $type): array
    {
        return match ($type) {
            'climate' => ['temperature', 'humidity', 'co2', 'lighting', 'ventilation'],
            'ph' => ['ph_sensor'],
            'ec' => ['ec_sensor'],
            'irrig' => ['pump_A', 'pump_B', 'pump_C', 'pump_D'],
            default => [],
        };
    }
}
