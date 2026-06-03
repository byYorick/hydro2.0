<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Concerns\PresentsLocalizedApiErrors;
use App\Helpers\ZoneAccessHelper;
use App\Http\Requests\StoreNodeCommandRequest;
use App\Models\DeviceNode;
use App\Services\PythonBridgeService;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class NodeCommandController extends Controller
{
    use PresentsLocalizedApiErrors;

    public function store(StoreNodeCommandRequest $request, DeviceNode $node, PythonBridgeService $bridge)
    {
        $user = $request->user();
        if (! $user) {
            return $this->localizedError('unauthenticated', null, 401);
        }

        if (! ZoneAccessHelper::canAccessNode($user, $node)) {
            return $this->localizedError('forbidden', 'Нет доступа к этому узлу.', 403);
        }

        $data = $request->validated();

        // Support both 'type' and 'cmd' fields for backward compatibility
        if (! isset($data['cmd']) && isset($data['type'])) {
            $data['cmd'] = $data['type'];
        }

        // Ensure cmd is set (валидация в Form Request)
        if (! isset($data['cmd'])) {
            return response()->json([
                'message' => 'The cmd or type field is required.',
                'errors' => ['cmd' => ['The cmd or type field is required.']],
            ], 422);
        }

        // Ensure params is an associative array (object), not a list (валидация в Form Request)
        if (! isset($data['params']) || $data['params'] === null) {
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

            return $this->localizedError('service_unavailable', null, 503, [
                'details' => $e->getMessage(),
            ]);
        } catch (TimeoutException $e) {
            Log::error('NodeCommandController: Timeout error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('service_timeout', null, 503, [
                'details' => $e->getMessage(),
            ]);
        } catch (RequestException $e) {
            $upstreamStatus = $e->response?->status();
            Log::error('NodeCommandController: Request error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
                'status' => $upstreamStatus,
            ]);

            if ($upstreamStatus !== null && $upstreamStatus >= 500) {
                return $this->localizedError('service_unavailable', null, 503, [
                    'details' => $this->extractRequestExceptionDetails($e),
                ]);
            }

            $decoded = $e->response?->json();
            if (is_array($decoded) && $upstreamStatus !== null && $upstreamStatus >= 400 && $upstreamStatus < 500) {
                return $this->enrichedUpstreamResponse(
                    array_merge($decoded, [
                        'details' => $this->extractRequestExceptionDetails($e),
                    ]),
                    $upstreamStatus,
                );
            }

            return $this->localizedError('command_failed', null, 422, [
                'details' => $this->extractRequestExceptionDetails($e),
            ]);
        } catch (\InvalidArgumentException $e) {
            Log::warning('NodeCommandController: Invalid argument', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
            ]);

            return $this->localizedError('invalid_argument', 'Аргумент команды недопустим. Подробности — в журнале сервера.', 422);
        } catch (\Exception $e) {
            Log::error('NodeCommandController: Unexpected error', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'command_type' => $data['cmd'] ?? null,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
                'trace' => $e->getTraceAsString(),
            ]);

            return $this->localizedError('internal_error', 'Неожиданная ошибка при отправке команды.', 500);
        }
    }

    private function extractRequestExceptionDetails(RequestException $exception): string
    {
        $response = $exception->response;
        if (! $response) {
            return $exception->getMessage();
        }

        $json = $response->json();
        if (is_array($json)) {
            $message = $json['message'] ?? null;
            if (is_string($message) && $message !== '') {
                return $message;
            }
        }

        $body = trim((string) $response->body());
        if ($body !== '') {
            return mb_substr($body, 0, 600);
        }

        return $exception->getMessage();
    }
}
