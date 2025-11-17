<?php

namespace App\Services;

use App\Models\Alert;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class AlertService
{
    /**
     * Создать алерт
     */
    public function create(array $data): Alert
    {
        return DB::transaction(function () use ($data) {
            $alert = Alert::create($data);
            Log::info('Alert created', ['alert_id' => $alert->id, 'type' => $alert->type]);
            
            // Dispatch event для realtime обновлений
            event(new \App\Events\AlertCreated([
                'id' => $alert->id,
                'type' => $alert->type,
                'status' => $alert->status,
                'zone_id' => $alert->zone_id,
                'details' => $alert->details,
                'created_at' => $alert->created_at,
            ]));
            
            return $alert;
        });
    }

    /**
     * Подтвердить/принять алерт
     */
    public function acknowledge(Alert $alert): Alert
    {
        return DB::transaction(function () use ($alert) {
            if ($alert->status === 'resolved' || $alert->status === 'RESOLVED') {
                throw new \DomainException('Alert is already resolved');
            }

            $alert->update([
                'status' => 'RESOLVED',
                'resolved_at' => now(),
            ]);

            Log::info('Alert acknowledged', ['alert_id' => $alert->id]);
            return $alert->fresh();
        });
    }
}

