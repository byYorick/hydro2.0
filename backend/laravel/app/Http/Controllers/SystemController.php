<?php

namespace App\Http\Controllers;

use App\Models\Greenhouse;
use Illuminate\Support\Facades\DB;

class SystemController extends Controller
{
    public function health()
    {
        // Быстрая проверка подключения к БД с таймаутом
        $dbOk = false;
        try {
            // Используем простой SELECT 1 вместо getPdo() для быстрой проверки
            DB::connection()->selectOne('SELECT 1 as test');
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


