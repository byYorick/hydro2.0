<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class SystemLog extends Model
{
    use HasFactory;

    protected $table = 'system_logs';

    public $timestamps = false;

    protected $fillable = [
        'level',
        'message',
        'context',
        'created_at',
    ];

    protected $casts = [
        'context' => 'array',
        'created_at' => 'datetime',
    ];

    protected $appends = ['service'];

    /**
     * Получить имя сервиса из контекста.
     * Всегда возвращает строку, чтобы фронт мог группировать логи.
     */
    public function getServiceAttribute(): string
    {
        $context = $this->context ?? [];

        // Основной источник — контекстный ключ service
        if (is_array($context) && isset($context['service']) && is_string($context['service'])) {
            return $context['service'];
        }

        // Фолбэк: иногда в контексте используется source
        if (is_array($context) && isset($context['source']) && is_string($context['source'])) {
            return $context['source'];
        }

        return 'system';
    }
}
