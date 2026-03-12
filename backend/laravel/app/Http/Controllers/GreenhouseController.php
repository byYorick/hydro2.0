<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class GreenhouseController extends Controller
{
    public function index(Request $request)
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Получаем доступные зоны для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        // Фильтруем теплицы по доступным зонам
        $query = Greenhouse::query();
        
        // Если пользователь не админ, фильтруем по доступным зонам
        if (!$user->isAdmin()) {
            $query->whereHas('zones', function ($q) use ($accessibleZoneIds) {
                $q->whereIn('id', $accessibleZoneIds);
            });
        }
        
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Права доступа проверяются на уровне маршрута (middleware role:operator,admin,agronomist,engineer)
        
        $data = $request->validate([
            'uid' => ['required', 'string', 'max:64', 'unique:greenhouses,uid'],
            'name' => ['required', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        
        // Генерируем уникальный provisioning_token для регистрации нод
        // Этот токен не должен быть доступен через API (скрыт в модели)
        $data['provisioning_token'] = 'gh_' . \Illuminate\Support\Str::random(32);
        
        $greenhouse = Greenhouse::create($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse], Response::HTTP_CREATED);
    }

    public function show(Request $request, Greenhouse $greenhouse)
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        $greenhouse->load('zones');
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function update(Request $request, Greenhouse $greenhouse)
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        $data = $request->validate([
            'uid' => ['sometimes', 'string', 'max:64', 'unique:greenhouses,uid,'.$greenhouse->id],
            'name' => ['sometimes', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        $greenhouse->update($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function destroy(Request $request, Greenhouse $greenhouse)
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Только админы могут удалять теплицы
        if (!$user->isAdmin()) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only administrators can delete greenhouses',
            ], 403);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        // Проверяем наличие привязанных зон
        $zonesCount = \App\Models\Zone::where('greenhouse_id', $greenhouse->id)->count();
        if ($zonesCount > 0) {
            return response()->json([
                'status' => 'error',
                'message' => "Cannot delete greenhouse: it has {$zonesCount} associated zone(s). Please delete or reassign zones first.",
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
        
        // Проверяем наличие привязанных узлов (на всякий случай, если есть прямая связь)
        // Обычно узлы привязаны через зоны, но проверка не помешает
        $nodesCount = \App\Models\DeviceNode::whereHas('zone', function ($q) use ($greenhouse) {
            $q->where('greenhouse_id', $greenhouse->id);
        })->count();
        
        if ($nodesCount > 0) {
            return response()->json([
                'status' => 'error',
                'message' => "Cannot delete greenhouse: it has {$nodesCount} associated node(s) through zones. Please delete or reassign nodes first.",
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
        
        $greenhouse->delete();
        return response()->json(['status' => 'ok']);
    }
}


