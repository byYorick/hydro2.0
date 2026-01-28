<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class CommandAck extends Model
{
    use HasFactory;

    protected $table = 'command_acks';

    protected $fillable = [
        'command_id',
        'ack_type',
        'measured_current',
        'measured_flow',
        'error_message',
        'metadata',
    ];

    protected $casts = [
        'measured_current' => 'decimal:4',
        'measured_flow' => 'decimal:4',
        'metadata' => 'array',
        'created_at' => 'datetime',
    ];

    public $timestamps = false; // Используем created_at вместо timestamps

    /**
     * Команда
     */
    public function command(): BelongsTo
    {
        return $this->belongsTo(Command::class);
    }

    /**
     * Scope для типа подтверждения
     */
    public function scopeOfType($query, string $ackType)
    {
        return $query->where('ack_type', $ackType);
    }

    /**
     * Scope для успешных подтверждений
     */
    public function scopeSuccessful($query)
    {
        return $query->whereIn('ack_type', ['accepted', 'executed', 'verified']);
    }

    /**
     * Scope для ошибок
     */
    public function scopeErrors($query)
    {
        return $query->where('ack_type', 'error');
    }
}

