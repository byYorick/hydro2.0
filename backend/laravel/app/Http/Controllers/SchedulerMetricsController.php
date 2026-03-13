<?php

namespace App\Http\Controllers;

use App\Services\AutomationScheduler\SchedulerPrometheusMetricsExporter;
use Illuminate\Http\Response;

class SchedulerMetricsController extends Controller
{
    public function __invoke(SchedulerPrometheusMetricsExporter $exporter): Response
    {
        return response($exporter->render(), 200, [
            'Content-Type' => 'text/plain; version=0.0.4; charset=utf-8',
            'Cache-Control' => 'no-store, no-cache, must-revalidate',
        ]);
    }
}
