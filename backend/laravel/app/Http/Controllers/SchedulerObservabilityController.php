<?php

namespace App\Http\Controllers;

use App\Services\AutomationScheduler\SchedulerDispatchReadModel;
use Illuminate\Http\JsonResponse;

class SchedulerObservabilityController extends Controller
{
    public function __invoke(SchedulerDispatchReadModel $readModel): JsonResponse
    {
        return response()->json(['status' => 'ok', 'data' => $readModel->snapshot()])
            ->header('Cache-Control', 'no-store');
    }
}
