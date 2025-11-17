<?php

namespace App\Http\Controllers;

use App\Models\Command;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Response;

class PythonIngestController extends Controller
{
    private function ensureToken(Request $request): void
    {
        $expected = Config::get('services.python_bridge.ingest_token') ?? Config::get('services.python_bridge.token');
        $given = $request->bearerToken();
        abort_unless($expected && hash_equals($expected, (string)$given), 401);
    }

    public function telemetry(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'zone_id' => ['required','integer'],
            'node_id' => ['nullable','integer'],
            'metric_type' => ['required','string','max:64'],
            'value' => ['required','numeric'],
            'ts' => ['nullable','date'],
            'channel' => ['nullable','string','max:64'],
        ]);
        TelemetrySample::create([
            'zone_id' => $data['zone_id'],
            'node_id' => $data['node_id'] ?? null,
            'metric_type' => $data['metric_type'],
            'value' => $data['value'],
            'ts' => $data['ts'] ?? now(),
            'channel' => $data['channel'] ?? null,
        ]);
        TelemetryLast::updateOrCreate(
            [
                'zone_id' => $data['zone_id'],
                'node_id' => $data['node_id'] ?? null,
                'metric_type' => $data['metric_type'],
                'channel' => $data['channel'] ?? null,
            ],
            [
                'value' => $data['value'],
                'ts' => $data['ts'] ?? now(),
            ]
        );
        return Response::json(['status' => 'ok']);
    }

    public function commandAck(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'cmd_id' => ['required','string','max:64'],
            'status' => ['required','string','in:accepted,completed,failed'],
            'details' => ['nullable','array'],
        ]);
        $cmd = Command::query()->where('cmd_id', $data['cmd_id'])->first();
        if ($cmd) {
            $cmd->status = $data['status'];
            $cmd->details = $data['details'] ?? null;
            $cmd->save();
        }
        return Response::json(['status' => 'ok']);
    }
}

