<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Substrate extends Model
{
    use HasFactory;

    protected $fillable = [
        'code',
        'name',
        'components',
        'applicable_systems',
        'notes',
    ];

    protected $casts = [
        'components' => 'array',
        'applicable_systems' => 'array',
    ];
}
