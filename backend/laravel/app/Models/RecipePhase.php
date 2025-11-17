<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class RecipePhase extends Model
{
    use HasFactory;

    protected $fillable = [
        'recipe_id',
        'phase_index',
        'name',
        'duration_hours',
        'targets',
    ];

    protected $casts = [
        'targets' => 'array',
    ];

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }
}


