<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\ZoneService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService
    ) {
    }

    public function index(Request $request)
    {
        $query = Zone::query()->withCount('nodes');
        if ($request->filled('greenhouse_id')) {
            $query->where('greenhouse_id', $request->integer('greenhouse_id'));
        }
        if ($request->filled('status')) {
            $query->where('status', $request->string('status'));
        }
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        $zone = $this->zoneService->create($data);
        return response()->json(['status' => 'ok', 'data' => $zone], Response::HTTP_CREATED);
    }

    public function show(Zone $zone)
    {
        $zone->load(['greenhouse', 'preset', 'nodes']);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function update(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        $zone = $this->zoneService->update($zone, $data);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function destroy(Zone $zone)
    {
        try {
            $this->zoneService->delete($zone);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function attachRecipe(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'recipe_id' => ['required', 'integer', 'exists:recipes,id'],
            'start_at' => ['nullable', 'date'],
        ]);
        $this->zoneService->attachRecipe(
            $zone,
            $data['recipe_id'],
            isset($data['start_at']) ? new \DateTime($data['start_at']) : null
        );
        return response()->json(['status' => 'ok']);
    }

    public function changePhase(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'phase_index' => ['required', 'integer', 'min:0'],
        ]);
        try {
            $this->zoneService->changePhase($zone, $data['phase_index']);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function pause(Zone $zone)
    {
        try {
            $zone = $this->zoneService->pause($zone);
            return response()->json(['status' => 'ok', 'data' => $zone]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function resume(Zone $zone)
    {
        try {
            $zone = $this->zoneService->resume($zone);
            return response()->json(['status' => 'ok', 'data' => $zone]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}


