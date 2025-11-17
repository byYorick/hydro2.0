<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use App\Services\AlertService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class AlertController extends Controller
{
    public function __construct(
        private AlertService $alertService
    ) {
    }

    public function index(Request $request)
    {
        $query = Alert::query();
        if ($request->filled('zone_id')) {
            $query->where('zone_id', $request->integer('zone_id'));
        }
        if ($request->filled('status')) {
            $query->where('status', $request->string('status')->toString());
        }
        $items = $query->orderByDesc('id')->paginate(50);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function show(Alert $alert)
    {
        return response()->json(['status' => 'ok', 'data' => $alert]);
    }

    public function ack(Alert $alert)
    {
        try {
            $alert = $this->alertService->acknowledge($alert);
            return response()->json(['status' => 'ok', 'data' => $alert], Response::HTTP_OK);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }
}


