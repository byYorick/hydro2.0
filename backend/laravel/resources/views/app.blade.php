@php
    $isLightAuthRoute = request()->routeIs('login', 'register', 'password.*', 'verification.*');
    $htmlTheme = $isLightAuthRoute ? 'light' : 'dark';
@endphp
<!DOCTYPE html>
<html
    lang="{{ str_replace('_', '-', app()->getLocale()) }}"
    class="{{ $isLightAuthRoute ? 'light' : '' }}"
    data-theme="{{ $htmlTheme }}"
    style="color-scheme: {{ $htmlTheme }}"
>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="csrf-token" content="{{ csrf_token() }}">
        <meta http-equiv="content-language" content="{{ str_replace('_', '-', app()->getLocale()) }}">
        <meta name="application-name" content="{{ config('app.name') }}">
        <meta name="apple-mobile-web-app-title" content="{{ config('app.name') }}">
        <meta name="theme-color" content="#0b6148">

        <link rel="icon" href="/favicon.svg?v=3" type="image/svg+xml">
        <link rel="alternate icon" href="/favicon.ico?v=3" sizes="any">
        <link rel="manifest" href="/site.webmanifest">

        <title inertia>{{ config('app.name') }}</title>

        <!-- Fonts: IBM Plex Sans + JetBrains Mono подключаются локально через @font-face в resources/css/app.css -->

        <!-- Scripts -->
        @routes
        @vite(['resources/js/app.js'])
        @inertiaHead
    </head>
    <body class="font-sans antialiased">
        @inertia
    </body>
</html>
