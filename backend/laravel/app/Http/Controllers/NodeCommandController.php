<?php

namespace App\Http\Controllers;

use App\Models\DeviceNode;
use App\Services\PythonBridgeService;
use Illuminate\Http\Request;

class NodeCommandController extends Controller
{
    public function store(Request $request, DeviceNode $node, PythonBridgeService $bridge)
    {
        $data = $request->validate([
            'type' => ['nullable', 'string', 'max:64'],
            'cmd' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:128'],
            'params' => ['nullable', 'array'],
        ]);

        // Support both 'type' and 'cmd' fields for backward compatibility
        if (!isset($data['cmd']) && isset($data['type'])) {
            $data['cmd'] = $data['type'];
        }
        
        // Ensure cmd is set
        if (!isset($data['cmd'])) {
            return response()->json([
                'message' => 'The cmd or type field is required.',
                'errors' => ['cmd' => ['The cmd or type field is required.']],
            ], 422);
        }

        // Ensure params is an associative array (object), not a list
        // Python service expects Dict[str, Any], not a list
        if (!isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            // Convert indexed array to empty object
            $data['params'] = [];
        }

        $commandId = $bridge->sendNodeCommand($node, $data);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'command_id' => $commandId,
            ],
        ]);
    }
}


