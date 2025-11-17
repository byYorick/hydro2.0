<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneRecipeInstance extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'recipe_id',
        'current_phase_index',
        'started_at',
    ];

    protected $casts = [
        'started_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }
}


