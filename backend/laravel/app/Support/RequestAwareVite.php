<?php

namespace App\Support;

use Illuminate\Foundation\Vite as BaseVite;

/**
 * В dev (public/hot) генерирует URL Vite-ассетов от текущего Host запроса,
 * чтобы работали и localhost:8080, и LAN IP с одного хоста.
 */
class RequestAwareVite extends BaseVite
{
    protected function hotAsset($asset): string
    {
        $baseUrl = config('app.url');

        if (is_string($baseUrl) && $baseUrl !== '') {
            return rtrim($baseUrl, '/').'/'.trim($asset, '/');
        }

        return parent::hotAsset($asset);
    }
}
