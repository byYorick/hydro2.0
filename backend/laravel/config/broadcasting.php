<?php

$defaultConnection = env('BROADCAST_CONNECTION', 'null');

if (env('APP_ENV') === 'testing') {
    $defaultConnection = env('BROADCAST_CONNECTION_TESTING', 'log');
}

$clientOptions = [];

if (env('REVERB_CLIENT_OPTIONS')) {
    try {
        $clientOptions = json_decode(env('REVERB_CLIENT_OPTIONS'), true, 512, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_IGNORE) ?: [];
    } catch (\Throwable $e) {
        $clientOptions = [];
    }
}

$reverbPath = env('REVERB_CLIENT_PATH', env('REVERB_SERVER_PATH', ''));

return [

    /*
    |--------------------------------------------------------------------------
    | Default Broadcaster
    |--------------------------------------------------------------------------
    |
    | This option controls the default broadcaster that will be used by the
    | framework when an event needs to be broadcast. Tests automatically
    | fall back to the "log" connection to avoid hitting real Reverb servers.
    |
    */

    'default' => $defaultConnection,

    /*
    |--------------------------------------------------------------------------
    | Broadcast Connections
    |--------------------------------------------------------------------------
    |
    | Here you may define all of the broadcast connections that will be used
    | to broadcast events to other systems or over WebSockets.
    |
    | Supported: "reverb", "pusher", "ably", "redis", "log", "null"
    |
    */

    'connections' => [

        'reverb' => [
            'driver' => 'reverb',
            'key' => env('REVERB_APP_KEY'),
            'secret' => env('REVERB_APP_SECRET'),
            'app_id' => env('REVERB_APP_ID'),
            'options' => array_filter([
                'host' => env('REVERB_HOST'),
                'port' => env('REVERB_PORT', 443),
                'scheme' => env('REVERB_SCHEME', 'https'),
                'useTLS' => env('REVERB_SCHEME', 'https') === 'https',
                'path' => $reverbPath,
            ]),
            'client_options' => $clientOptions,
        ],

        'pusher' => [
            'driver' => 'pusher',
            'key' => env('PUSHER_APP_KEY'),
            'secret' => env('PUSHER_APP_SECRET'),
            'app_id' => env('PUSHER_APP_ID'),
            'options' => [
                'cluster' => env('PUSHER_APP_CLUSTER'),
                'host' => env('PUSHER_HOST') ?: 'api-'.env('PUSHER_APP_CLUSTER', 'mt1').'.pusher.com',
                'port' => env('PUSHER_PORT', 443),
                'scheme' => env('PUSHER_SCHEME', 'https'),
                'encrypted' => true,
                'useTLS' => env('PUSHER_SCHEME', 'https') === 'https',
            ],
            'client_options' => [
                // Guzzle client options: https://docs.guzzlephp.org/en/stable/request-options.html
            ],
        ],

        'ably' => [
            'driver' => 'ably',
            'key' => env('ABLY_KEY'),
        ],

        'redis' => [
            'driver' => 'redis',
            'connection' => 'default',
        ],

        'log' => [
            'driver' => 'log',
        ],

        'null' => [
            'driver' => 'null',
        ],

    ],

];
