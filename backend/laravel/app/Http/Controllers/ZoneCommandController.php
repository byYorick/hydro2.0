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
            'params' => ['nullable'],
        ]);
        
        // Ensure params is an associative array (object), not a list
        // Python service expects Dict[str, Any], not a list
        if (!isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            // Convert indexed array to empty object
            $data['params'] = [];
        }

        $commandId = $bridge->sendZoneCommand($zone, $data);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'command_id' => $commandId,
            ],
        ]);
    }
}


