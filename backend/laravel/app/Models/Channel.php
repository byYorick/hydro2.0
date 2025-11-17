<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Channel extends Model
{
    protected $fillable = ['device_id', 'name', 'kind', 'last_value'];

    public function device(): BelongsTo
    {
        return $this->belongsTo(Device::class);
    }
}

