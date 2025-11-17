<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Event extends Model
{
    protected $table = 'zone_events';
    
    protected $fillable = ['zone_id', 'type', 'details'];
    
    protected $casts = [
        'details' => 'array',
        'created_at' => 'datetime',
    ];

    public function zone(): BelongsTo 
    { 
        return $this->belongsTo(Zone::class); 
    }
    
    // Accessors for compatibility with old field names
    public function getKindAttribute()
    {
        return $this->type;
    }
    
    public function getMessageAttribute()
    {
        return $this->details['message'] ?? $this->type;
    }
    
    public function getOccurredAtAttribute()
    {
        return $this->created_at;
    }
}

