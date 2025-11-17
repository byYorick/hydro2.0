<?php

namespace App\Http\Controllers;

use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use Illuminate\Http\Request;

class TelemetryController extends Controller
{
    public function zoneLast(int $zoneId)
    {
        $rows = TelemetryLast::query()
            ->where('zone_id', $zoneId)
            ->get();

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    public function zoneHistory(Request $request, int $zoneId)
    {
        $validated = $request->validate([
            'metric' => ['required', 'string', 'max:64'],
            'from' => ['nullable', 'date'],
            'to' => ['nullable', 'date'],
        ]);

        $q = TelemetrySample::query()->where('zone_id', $zoneId)
            ->where('metric_type', $validated['metric'])
            ->orderBy('ts', 'asc');

        if (!empty($validated['from'])) {
            $q->where('ts', '>=', $validated['from']);
        }
        if (!empty($validated['to'])) {
            $q->where('ts', '<=', $validated['to']);
        }

        $rows = $q->limit(5000)->get(['ts', 'value', 'node_id', 'channel']);

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }

    public function nodeLast(int $nodeId)
    {
        $rows = TelemetryLast::query()
            ->where('node_id', $nodeId)
            ->get();

        return response()->json([
            'status' => 'ok',
            'data' => $rows,
        ]);
    }
}


