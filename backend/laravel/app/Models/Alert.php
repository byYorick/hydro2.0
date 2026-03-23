<?php

namespace App\Models;

use App\Services\AlertLocalizationService;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Alert extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'source',
        'code',
        'type',
        'details',
        'status',
        'category',
        'severity',
        'node_uid',
        'hardware_id',
        'error_count',
        'first_seen_at',
        'last_seen_at',
        'created_at',
        'resolved_at',
    ];

    protected $casts = [
        'details' => 'array',
        'created_at' => 'datetime',
        'resolved_at' => 'datetime',
        'first_seen_at' => 'datetime',
        'last_seen_at' => 'datetime',
    ];

    protected $appends = [
        'title',
        'message',
        'description',
        'recommendation',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function getTitleAttribute(): string
    {
        return $this->localizedPresentation()['title'];
    }

    public function getMessageAttribute(): string
    {
        return $this->localizedPresentation()['message'];
    }

    public function getDescriptionAttribute(): string
    {
        return $this->localizedPresentation()['description'];
    }

    public function getRecommendationAttribute(): string
    {
        return $this->localizedPresentation()['recommendation'];
    }

    /**
     * @return array{code:string,title:string,description:string,recommendation:string,message:string}
     */
    private function localizedPresentation(): array
    {
        /** @var AlertLocalizationService $localizer */
        $localizer = app(AlertLocalizationService::class);

        return $localizer->present(
            code: is_string($this->code) ? $this->code : null,
            type: is_string($this->type) ? $this->type : null,
            details: is_array($this->details) ? $this->details : [],
            source: is_string($this->source) ? $this->source : null,
        );
    }
}
