<?php

namespace App\Http\Requests\Auth;

use Illuminate\Auth\Events\Lockout;
use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;

class LoginRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        return [
            'email' => ['required', 'string', 'email'],
            'password' => ['required', 'string'],
        ];
    }

    /**
     * Get custom messages for validator errors.
     *
     * @return array<string, string>
     */
    public function messages(): array
    {
        return [
            'email.required' => 'Поле email обязательно для заполнения.',
            'email.email' => 'Пожалуйста, введите корректный email адрес.',
            'password.required' => 'Поле пароль обязательно для заполнения.',
        ];
    }

    /**
     * Attempt to authenticate the request's credentials.
     *
     * @throws \Illuminate\Validation\ValidationException
     */
    public function authenticate(): void
    {
        $this->ensureIsNotRateLimited();

        // Используем явно web guard для сессионной аутентификации
        if (! Auth::guard('web')->attempt($this->only('email', 'password'), $this->boolean('remember'))) {
            RateLimiter::hit($this->throttleKey());

            // Для Inertia запросов нужно правильно обработать ошибку валидации
            // чтобы форма оставалась на странице логина
            throw ValidationException::withMessages([
                'email' => 'Неверный email или пароль. Проверьте правильность введенных данных.',
            ])->errorBag('default');
        }

        RateLimiter::clear($this->throttleKey());
    }

    /**
     * Ensure the login request is not rate limited.
     *
     * @throws \Illuminate\Validation\ValidationException
     */
    public function ensureIsNotRateLimited(): void
    {
        if (! RateLimiter::tooManyAttempts($this->throttleKey(), 5)) {
            return;
        }

        event(new Lockout($this));

        $seconds = RateLimiter::availableIn($this->throttleKey());
        $minutes = ceil($seconds / 60);

        throw ValidationException::withMessages([
            'email' => "Слишком много попыток входа. Пожалуйста, попробуйте снова через {$minutes} " . ($minutes === 1 ? 'минуту' : ($minutes < 5 ? 'минуты' : 'минут')) . ".",
        ]);
    }

    /**
     * Get the rate limiting throttle key for the request.
     */
    public function throttleKey(): string
    {
        return Str::transliterate(Str::lower($this->string('email')).'|'.$this->ip());
    }

    /**
     * Get the URL to redirect to on a validation error.
     * Для Inertia запросов возвращаем URL страницы логина,
     * чтобы форма оставалась на месте при ошибке валидации.
     * 
     * Примечание: Этот метод используется только для стандартной обработки Laravel.
     * Для Inertia запросов ValidationException обрабатывается в bootstrap/app.php
     * через redirect()->back()->withErrors(), который автоматически возвращает на страницу логина.
     *
     * @return string
     */
    protected function getRedirectUrl()
    {
        // Для Inertia запросов возвращаем URL страницы логина
        // чтобы форма оставалась на месте при ошибке валидации
        if ($this->header('X-Inertia')) {
            return route('login');
        }

        // Для обычных запросов используем стандартный back()
        return url()->previous();
    }
}
