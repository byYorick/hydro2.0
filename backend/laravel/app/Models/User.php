<?php

namespace App\Models;

// use Illuminate\Contracts\Auth\MustVerifyEmail;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Foundation\Auth\User as Authenticatable;
use Illuminate\Notifications\Notifiable;
use Laravel\Sanctum\HasApiTokens;

class User extends Authenticatable
{
    use HasApiTokens, HasFactory, Notifiable;

    /**
     * The attributes that are mass assignable.
     *
     * @var array<int, string>
     */
    protected $fillable = [
        'name',
        'email',
        'password',
        'role',
    ];

    /**
     * The attributes that should be hidden for serialization.
     *
     * @var array<int, string>
     */
    protected $hidden = [
        'password',
        'remember_token',
    ];

    /**
     * Get the attributes that should be cast.
     *
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'email_verified_at' => 'datetime',
            'password' => 'hashed',
        ];
    }

    public function isAdmin(): bool
    {
        return ($this->role ?? 'operator') === 'admin';
    }

    /**
     * Проверить, имеет ли пользователь указанную роль
     */
    public function hasRole(string $role): bool
    {
        return ($this->role ?? 'operator') === $role;
    }

    /**
     * Проверить, является ли пользователь агрономом
     */
    public function isAgronomist(): bool
    {
        return $this->hasRole('agronomist');
    }

    public function zones(): BelongsToMany
    {
        return $this->belongsToMany(Zone::class, 'user_zones')
            ->withTimestamps();
    }

    public function greenhouses(): BelongsToMany
    {
        return $this->belongsToMany(Greenhouse::class, 'user_greenhouses')
            ->withTimestamps();
    }
}
