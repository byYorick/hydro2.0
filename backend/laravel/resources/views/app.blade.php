<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta name="csrf-token" content="{{ csrf_token() }}">

        <title inertia>{{ config('app.name', 'Laravel') }}</title>

        <!-- Fonts -->
        <link rel="preconnect" href="https://fonts.bunny.net">
        <link href="https://fonts.bunny.net/css?family=figtree:400,500,600&display=swap" rel="stylesheet" />

        <!-- Scripts -->
        @routes
        <?php
            $vite = app(\Illuminate\Foundation\Vite::class);
            $entries = ['resources/js/app.js'];
            $pageComponent = "resources/js/Pages/{$page['component']}.vue";

            try {
                echo $vite(array_merge($entries, [$pageComponent]));
            } catch (\Illuminate\Foundation\ViteException $e) {
                echo $vite($entries);
            }
        ?>
        @inertiaHead
    </head>
    <body class="font-sans antialiased">
        @inertia
    </body>
</html>
