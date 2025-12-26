<?php

/*
|--------------------------------------------------------------------------
| Final Routes
|--------------------------------------------------------------------------
|
| Финальные маршруты: Swagger, Admin, Testing backdoor.
|
*/

use Illuminate\Support\Facades\Route;

// Swagger доступен только для авторизованных пользователей в dev/testing окружениях
// В production должен быть отключен или защищен дополнительной аутентификацией
Route::get('/swagger', function () {
    if (app()->environment(['production', 'staging'])) {
        abort(404, 'Swagger documentation is not available in this environment');
    }
    if (! auth()->check()) {
        return redirect()->route('login');
    }

    return redirect('/swagger.html');
})->middleware('auth');

Route::middleware(['web', 'auth', 'role:admin,operator,agronomist'])->group(function () {
    Route::get('/plants', [PlantController::class, 'index'])->name('plants.index');
    Route::get('/plants/{plant}', [PlantController::class, 'show'])->name('plants.show');
    Route::post('/plants', [PlantController::class, 'store'])->name('plants.store');
    Route::put('/plants/{plant}', [PlantController::class, 'update'])->name('plants.update');
    Route::delete('/plants/{plant}', [PlantController::class, 'destroy'])->name('plants.destroy');
    Route::post('/plants/{plant}/prices', [PlantController::class, 'storePriceVersion'])->name('plants.prices.store');
});

Route::middleware(['web', 'auth'])->group(function () {
    Route::get('/profile', [ProfileController::class, 'edit'])->name('profile.edit');
    Route::patch('/profile', [ProfileController::class, 'update'])->name('profile.update');
    Route::delete('/profile', [ProfileController::class, 'destroy'])->name('profile.destroy');
    
    /**
     * Monitoring - страница мониторинга системы
     *
     * Inertia Props:
     * - auth: { user: { role: string } }
     */
    Route::get('/monitoring', fn () => Inertia::render('Monitoring/Index', [
        'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
    ]))->name('monitoring.index');
});

require __DIR__.'/auth.php';

// Тестовый backdoor доступен ТОЛЬКО в testing окружении (не в local!)
// Это предотвращает случайное включение в production при ошибочной конфигурации env
if (app()->environment('testing')) {
    Route::get('/testing/login/{user}', function (\App\Models\User $user) {
        \Illuminate\Support\Facades\Auth::login($user);
        \Log::warning('Testing backdoor used', [
            'user_id' => $user->id,
            'ip' => request()->ip(),
        ]);

        return redirect()->intended('/');
    })->name('testing.login');
}
