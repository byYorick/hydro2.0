<!DOCTYPE html>
<html lang="ru" class="light" data-theme="light" style="color-scheme: light">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    @php
        $brandName = config('app.name', 'Автоматика теплицы');
        if ($brandName === 'Laravel') {
            $brandName = 'Автоматика теплицы';
        }
    @endphp
    <title>404 — {{ $brandName }}</title>
    @vite(['resources/css/error-pages.css'])
</head>
<body class="font-sans antialiased bg-[#f3f6ef] text-[#191c1e] overflow-x-hidden">
{{-- Иконки — inline SVG, без Material Symbols / CDN --}}
<header class="sticky top-0 z-50 border-b border-emerald-900/10 bg-white/75 backdrop-blur-xl">
    <div class="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-6 py-4">
        <a href="{{ url('/') }}" class="text-xl font-extrabold tracking-tight text-emerald-900 transition-opacity hover:opacity-80">
            {{ $brandName }}
        </a>
        <div class="flex items-center gap-2 text-emerald-800">
            <span class="inline-flex rounded-full p-2 text-emerald-700/80" aria-hidden="true">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"/></svg>
            </span>
            <span class="inline-flex rounded-full p-2 text-emerald-700/80" aria-hidden="true">
                <svg class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.082A2.02 2.02 0 0 0 21 14.002V10a6 6 0 0 0-6-6H9a6 6 0 0 0-6 6v4.002c0 .61.49 1.093 1.095 1.002a23.91 23.91 0 0 0 5.454 1.082M15 10h.01M12 10h.01M9 10h.01"/></svg>
            </span>
        </div>
    </div>
</header>

<main class="relative flex min-h-[calc(100vh-4.5rem)] flex-col items-center justify-center px-6 py-16">
    {{-- Декор без внешних изображений --}}
    <div class="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div class="absolute -right-24 top-10 h-72 w-72 rounded-full bg-emerald-400/15 blur-3xl"></div>
        <div class="absolute -left-20 bottom-10 h-80 w-80 rounded-full bg-[#3b5d45]/10 blur-3xl"></div>
        <div class="absolute left-10 top-32 max-w-xs font-mono text-[10px] leading-tight text-slate-500/40 space-y-1 select-none">
            <p>[SYSTEM_INIT] Sector 7G sequence engaged...</p>
            <p>[WARNING] Unusual biometric readings detected.</p>
            <p>[ERROR] Route not found. 0x00404</p>
        </div>
    </div>

    <div class="relative z-10 flex max-w-2xl flex-col items-center text-center">
        <p class="mb-4 text-xs font-bold uppercase tracking-[0.3em] text-emerald-700/70">HTTP 404</p>
        <h1 class="text-7xl font-extrabold tracking-tighter text-emerald-900 sm:text-8xl md:text-9xl">
            404
        </h1>
        <h2 class="mt-6 text-2xl font-bold tracking-tight text-emerald-900 sm:text-3xl md:text-4xl">
            Страница не найдена
        </h2>
        <p class="mt-4 text-base text-slate-600 sm:text-lg">
            Запрошенный адрес не существует или был перенесён. Вернитесь в панель управления или на главную.
        </p>
        <div class="mt-10 flex flex-wrap items-center justify-center gap-4">
            <a
                href="{{ url('/') }}"
                class="inline-flex items-center gap-2 rounded-2xl bg-gradient-to-br from-[#0b6148] to-[#2f7b60] px-8 py-4 text-lg font-semibold text-white shadow-lg shadow-emerald-900/20 transition hover:-translate-y-0.5 hover:shadow-xl"
            >
                <svg class="h-5 w-5 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"/></svg>
                На главную
            </a>
            <a
                href="{{ url('/login') }}"
                class="inline-flex items-center gap-2 rounded-2xl border border-emerald-800/20 bg-white/80 px-8 py-4 text-lg font-semibold text-emerald-900 shadow-sm backdrop-blur transition hover:bg-white"
            >
                Вход
            </a>
        </div>
    </div>
</main>

<footer class="border-t border-emerald-900/10 bg-emerald-50/80 py-8 text-center text-xs font-semibold uppercase tracking-widest text-emerald-900/70">
    <div class="mx-auto flex max-w-[1180px] flex-col items-center justify-between gap-4 px-6 md:flex-row">
        <span>© {{ date('Y') }} {{ $brandName }}</span>
        <nav class="flex flex-wrap justify-center gap-6">
            <a class="transition hover:text-emerald-600" href="{{ url('/') }}">Статус</a>
            <a class="transition hover:text-emerald-600" href="{{ url('/dashboard') }}">Панель</a>
            <a class="transition hover:text-emerald-600" href="{{ url('/login') }}">Поддержка</a>
        </nav>
    </div>
</footer>
</body>
</html>
