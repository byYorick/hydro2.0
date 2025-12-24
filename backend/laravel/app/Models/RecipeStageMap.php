<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class RecipeStageMap extends Model
{
    use HasFactory;

    protected $fillable = [
        'recipe_id',
        'stage_template_id',
        'order_index',
        'start_offset_days',
        'end_offset_days',
        'phase_indices',
        'targets_override',
    ];

    protected $casts = [
        'order_index' => 'integer',
        'start_offset_days' => 'integer',
        'end_offset_days' => 'integer',
        'phase_indices' => 'array',
        'targets_override' => 'array',
    ];

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    public function stageTemplate(): BelongsTo
    {
        return $this->belongsTo(GrowStageTemplate::class, 'stage_template_id');
    }
}

