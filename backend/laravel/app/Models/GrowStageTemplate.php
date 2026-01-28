<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class GrowStageTemplate extends Model
{
    use HasFactory;

    protected $fillable = [
        'name',
        'code',
        'order_index',
        'default_duration_days',
        'ui_meta',
    ];

    protected $casts = [
        'order_index' => 'integer',
        'default_duration_days' => 'integer',
        'ui_meta' => 'array',
    ];

    public function phases(): HasMany
    {
        return $this->hasMany(RecipeRevisionPhase::class, 'stage_template_id');
    }
}
