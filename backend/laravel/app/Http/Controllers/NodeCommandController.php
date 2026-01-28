<?php

namespace App\Http\Controllers;

use App\Http\Requests\StoreNodeCommandRequest;
use App\Models\DeviceNode;
use App\Services\PythonBridgeService;
use Illuminate\Http\Request;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Log;

class NodeCommandController extends Controller
{
    public function store(StoreNodeCommandRequest $request, DeviceNode $node, PythonBridgeService $bridge)
    {
        $data = $request->validated();
        
        // Support both 'type' and 'cmd' fields for backward compatibility
        if (!isset($data['cmd']) && isset($data['type'])) {
            $data['cmd'] = $data['type'];
        }
        
        // Ensure cmd is set (валидация в Form Request)
        if (!isset($data['cmd'])) {
            return response()->json([
                'message' => 'The cmd or type field is required.',
                'errors' => ['cmd' => ['The cmd or type field is required.']],
            ], 422);
        }

        // Ensure params is an associative array (object), not a list (валидация в Form Request)
        if (!isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            $data['params'] = [];
        }

        try {
            $commandId = $bridge->sendNodeCommand($node, $data);

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'command_id' => $commandId,
                ],
            ]);
        } catch (ConnectionException $e) {
            Log::error('NodeCommandController: Connection error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
            ]);
            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_UNAVAILABLE',
                'message' => 'Unable to connect to command service. Please try again later.',
            ], 503);
        } catch (TimeoutException $e) {
            Log::error('NodeCommandController: Timeout error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
            ]);
            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_TIMEOUT',
                'message' => 'Command service did not respond in time. Please try again later.',
            ], 503);
        } catch (RequestException $e) {
            Log::error('NodeCommandController: Request error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);
            return response()->json([
                'status' => 'error',
                'code' => 'COMMAND_FAILED',
                'message' => 'Failed to send command. The command may have been queued but failed validation.',
            ], 422);
        } catch (\InvalidArgumentException $e) {
            Log::warning('NodeCommandController: Invalid argument', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
            ]);
            return response()->json([
                'status' => 'error',
                'code' => 'INVALID_ARGUMENT',
                'message' => $e->getMessage(),
            ], 422);
        } catch (\Exception $e) {
            Log::error('NodeCommandController: Unexpected error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);
            return response()->json([
                'status' => 'error',
                'code' => 'INTERNAL_ERROR',
                'message' => 'An unexpected error occurred while sending the command.',
            ], 500);
        }
    }
}
