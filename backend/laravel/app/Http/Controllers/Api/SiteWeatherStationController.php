<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\SiteWeather\AssignSiteWeatherStationRequest;
use App\Models\DeviceNode;
use App\Services\SiteInfrastructureService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class SiteWeatherStationController extends Controller
{
    public function __construct(
        private readonly SiteInfrastructureService $siteInfrastructure,
    ) {}

    public function index(Request $request): JsonResponse
    {
        if (! $request->user()) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        $stations = $this->siteInfrastructure->listWeatherStations();

        return response()->json([
            'status' => 'ok',
            'data' => $stations,
            'meta' => [
                'greenhouse_uid' => SiteInfrastructureService::SITE_GREENHOUSE_UID,
                'zone_uid' => SiteInfrastructureService::SITE_WEATHER_ZONE_UID,
            ],
        ]);
    }

    public function store(AssignSiteWeatherStationRequest $request): JsonResponse
    {
        $node = DeviceNode::query()->findOrFail((int) $request->validated('node_id'));

        try {
            $station = $this->siteInfrastructure->assignWeatherStation($node);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $station,
        ], Response::HTTP_CREATED);
    }

    public function destroy(Request $request, DeviceNode $node): JsonResponse
    {
        $user = $request->user();
        if (! $user) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        if (! in_array($user->role, ['admin', 'operator', 'agronomist', 'engineer'], true)) {
            return response()->json(['status' => 'error', 'message' => 'Forbidden'], 403);
        }

        try {
            $station = $this->siteInfrastructure->unassignWeatherStation($node);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $station,
        ]);
    }
}
