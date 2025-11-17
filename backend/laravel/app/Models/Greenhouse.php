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
        'name',
        'timezone',
        'type',
        'coordinates',
        'description',
    ];

    protected $casts = [
        'coordinates' => 'array',
    ];

    public function zones(): HasMany
    {
        return $this->hasMany(Zone::class);
    }
}


