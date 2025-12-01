<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\PythonBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class ZoneCommandController extends Controller
{
    public function store(Request $request, Zone $zone, PythonBridgeService $bridge)
    {
        $data = $request->validate([
            'type' => ['required', 'string', 'max:64'],
            'params' => ['nullable'],
            'node_uid' => ['nullable', 'string', 'max:64'],
            'channel' => ['nullable', 'string', 'max:64'],
        ]);

        // Ensure params is an associative array (object), not a list
        // Python service expects Dict[str, Any], not a list
        if (! isset($data['params']) || $data['params'] === null) {
            $data['params'] = [];
        } elseif (is_array($data['params']) && array_is_list($data['params'])) {
            // Convert indexed array to empty object
            $data['params'] = [];
        }

        try {
            $commandId = $bridge->sendZoneCommand($zone, $data);

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'command_id' => $commandId,
                ],
            ]);
        } catch (ConnectionException $e) {
            Log::error('ZoneCommandController: Connection error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_UNAVAILABLE',
                'message' => 'Unable to connect to command service. Please try again later.',
            ], 503);
        } catch (TimeoutException $e) {
            Log::error('ZoneCommandController: Timeout error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'SERVICE_TIMEOUT',
                'message' => 'Command service did not respond in time. Please try again later.',
            ], 503);
        } catch (RequestException $e) {
            Log::error('ZoneCommandController: Request error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
                'status' => $e->response?->status(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'COMMAND_FAILED',
                'message' => 'Failed to send command. The command may have been queued but failed validation.',
            ], 422);
        } catch (\InvalidArgumentException $e) {
            Log::warning('ZoneCommandController: Invalid argument', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'code' => 'INVALID_ARGUMENT',
                'message' => $e->getMessage(),
            ], 422);
        } catch (\Exception $e) {
            Log::error('ZoneCommandController: Unexpected error', [
                'zone_id' => $zone->id,
                'command_type' => $data['type'] ?? null,
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
