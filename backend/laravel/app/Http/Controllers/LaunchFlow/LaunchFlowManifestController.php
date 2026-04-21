<?php

namespace App\Http\Controllers\LaunchFlow;

use App\Http\Controllers\Controller;
use App\Models\Zone;
use App\Services\LaunchFlow\LaunchFlowManifestBuilder;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class LaunchFlowManifestController extends Controller
{
    public function __construct(private readonly LaunchFlowManifestBuilder $builder)
    {
    }

    public function show(Request $request): JsonResponse
    {
        $zoneId = $request->query('zone_id');
        $zone = null;

        if ($zoneId !== null && $zoneId !== '') {
            if (! ctype_digit((string) $zoneId)) {
                return response()->json([
                    'status' => 'error',
                    'error' => ['code' => 'invalid_zone_id', 'message' => 'zone_id must be a positive integer'],
                ], 422);
            }

            $zone = Zone::query()->find((int) $zoneId);
            if (! $zone) {
                return response()->json([
                    'status' => 'error',
                    'error' => ['code' => 'zone_not_found', 'message' => 'Zone not found'],
                ], 404);
            }
        }

        $manifest = $this->builder->build($zone, $request->user());

        return response()->json([
            'status' => 'ok',
            'data' => $manifest,
        ]);
    }
}
