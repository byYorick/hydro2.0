<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class FirmwareFile extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'node_type',
        'version',
        'file_path',
        'checksum_sha256',
        'release_notes',
    ];

    protected $casts = [
        'created_at' => 'datetime',
    ];
}

