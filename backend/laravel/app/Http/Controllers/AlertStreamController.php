<?php

namespace App\Http\Controllers;

use App\Models\Alert;
use Illuminate\Http\Request;

class AlertStreamController extends Controller
{
    public function stream(Request $request)
    {
        return response()->stream(function () use ($request) {
            $lastId = (int)($request->query('last_id', 0));
            while (true) {
                $q = Alert::query()->orderBy('id', 'asc');
                if ($lastId > 0) {
                    $q->where('id', '>', $lastId);
                }
                $items = $q->limit(50)->get();
                foreach ($items as $a) {
                    $lastId = max($lastId, $a->id);
                    echo "event: alert\n";
                    echo "data: " . json_encode($a) . "\n\n";
                    @ob_flush();
                    @flush();
                }
                sleep(2);
            }
        }, 200, [
            'Content-Type' => 'text/event-stream',
            'Cache-Control' => 'no-cache',
            'X-Accel-Buffering' => 'no',
        ]);
    }
}


