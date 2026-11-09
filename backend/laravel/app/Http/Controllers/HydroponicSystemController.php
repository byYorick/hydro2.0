<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Support\Hydroponics\HydroponicSystemCatalog;
use Illuminate\Http\JsonResponse;

class HydroponicSystemController extends Controller
{
    public function index(): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => HydroponicSystemCatalog::publicPayload(),
        ]);
    }
}
