<?php

namespace App\Http\Controllers;

use App\Services\CycleCenterService;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class CycleCenterController extends Controller
{
    public function __construct(
        private CycleCenterService $cycleCenterService
    ) {}

    public function index(Request $request): Response
    {
        $user = $request->user();
        $data = $this->cycleCenterService->getCycleCenterData($user);

        return Inertia::render('Cycles/Center', [
            'auth' => ['user' => ['role' => $user?->role ?? 'viewer']],
            'summary' => $data['summary'],
            'zones' => $data['zones'],
            'greenhouses' => $data['greenhouses'],
        ]);
    }
}
