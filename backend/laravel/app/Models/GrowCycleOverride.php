<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GrowCycleOverride extends Model
{
    use HasFactory;

    protected $fillable = [
        'grow_cycle_id',
        'parameter',
        'value_type',
        'value',
        'reason',
        'created_by',
        'applies_from',
        'applies_until',
        'is_active',
    ];

    protected $casts = [
        'applies_from' => 'datetime',
        'applies_until' => 'datetime',
        'is_active' => 'boolean',
    ];

    /**
     * Цикл выращивания, для которого действует это перекрытие
     */
    public function growCycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class);
    }

    /**
     * Пользователь, создавший перекрытие
     */
    public function creator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    /**
     * Проверка, активно ли перекрытие в данный момент
     */
    public function isCurrentlyActive(): bool
    {
        if (!$this->is_active) {
            return false;
        }

        $now = now();

        if ($this->applies_from && $now->lt($this->applies_from)) {
            return false;
        }

        if ($this->applies_until && $now->gt($this->applies_until)) {
            return false;
        }

        return true;
    }

    /**
     * Получить значение с правильным типом
     */
    public function getTypedValue()
    {
        return match ($this->value_type) {
            'integer' => (int) $this->value,
            'decimal', 'float' => (float) $this->value,
            'boolean' => filter_var($this->value, FILTER_VALIDATE_BOOLEAN),
            'time' => $this->value, // время как строка
            default => $this->value,
        };
    }
}

