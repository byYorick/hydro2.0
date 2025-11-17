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
            'cmd' => ['required', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:128'],
            'params' => ['nullable', 'array'],
        ]);

        $commandId = $bridge->sendNodeCommand($node, $data);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'command_id' => $commandId,
            ],
        ]);
    }
}


