<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\PythonBridgeService;
use Illuminate\Http\Request;

class ZoneCommandController extends Controller
{
    public function store(Request $request, Zone $zone, PythonBridgeService $bridge)
    {
        $data = $request->validate([
            'type' => ['required', 'string', 'max:64'],
            'params' => ['nullable', 'array'],
        ]);

        $commandId = $bridge->sendZoneCommand($zone, $data);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'command_id' => $commandId,
            ],
        ]);
    }
}


