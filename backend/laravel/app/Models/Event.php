<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Event extends Model
{
    protected $fillable = ['zone_id', 'kind', 'message', 'occurred_at'];
    protected $casts = ['occurred_at' => 'datetime'];

    public function zone(): BelongsTo { return $this->belongsTo(Zone::class); }
}

