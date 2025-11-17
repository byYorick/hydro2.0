<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use Illuminate\Support\Facades\DB;

class SystemController extends Controller
{
    public function health()
    {
        // Простая проверка подключения к БД
        $dbOk = false;
        try {
            DB::connection()->getPdo();
            $dbOk = true;
        } catch (\Throwable $e) {
            $dbOk = false;
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'app' => 'ok',
                'db' => $dbOk ? 'ok' : 'fail',
            ],
        ]);
    }

    public function configFull()
    {
        $greenhouses = Greenhouse::with([
            'zones.nodes.channels',
            'zones.recipeInstance.recipe',
        ])->get();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'greenhouses' => $greenhouses,
            ],
        ]);
    }
}


