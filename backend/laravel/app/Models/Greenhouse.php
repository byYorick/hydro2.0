<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Greenhouse extends Model
{
    use HasFactory;

    protected $fillable = [
        'uid',
        'provisioning_token',
        'name',
        'timezone',
        'type',
        'coordinates',
        'description',
    ];

    protected $hidden = [
        'provisioning_token', // Скрываем токен от API-ответов
    ];

    protected $casts = [
        'coordinates' => 'array',
    ];

    public function zones(): HasMany
    {
        return $this->hasMany(Zone::class);
    }

    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class);
    }

    /**
     * Экземпляры инфраструктуры теплицы (климат: вентиляция, проветривание, подогрев)
     */
    public function infrastructureInstances(): HasMany
    {
        return $this->morphMany(InfrastructureInstance::class, 'owner')
            ->where('owner_type', 'greenhouse');
    }
}


