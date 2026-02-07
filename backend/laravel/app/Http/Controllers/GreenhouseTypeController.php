<?php

namespace App\Http\Controllers;

use App\Models\GreenhouseType;
use Illuminate\Http\JsonResponse;

class GreenhouseTypeController extends Controller
{
    public function index(): JsonResponse
    {
        $items = GreenhouseType::query()
            ->where('is_active', true)
            ->orderBy('sort_order')
            ->orderBy('name')
            ->get(['id', 'code', 'name', 'description']);

        return response()->json([
            'status' => 'ok',
            'data' => $items,
        ]);
    }
}

