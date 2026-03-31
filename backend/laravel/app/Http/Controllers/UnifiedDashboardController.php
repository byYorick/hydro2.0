<?php

namespace App\Http\Controllers;

use App\Services\UnifiedDashboardService;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class UnifiedDashboardController extends Controller
{
    public function __construct(
        private UnifiedDashboardService $service
    ) {}

    public function index(Request $request): Response
    {
        $user = $request->user();
        $data = $this->service->getData($user);

        return Inertia::render('Dashboard/Index', [
            'auth' => ['user' => ['role' => $user?->role ?? 'viewer']],
            'summary' => $data['summary'],
            'zones' => $data['zonesData'],
            'greenhouses' => $data['greenhouses'],
            'latestAlerts' => $data['latestAlerts'],
        ]);
    }
}
