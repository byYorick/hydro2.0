<?php

namespace Tests\Feature;

use App\Support\RequestAwareVite;
use Illuminate\Foundation\Vite;
use Tests\TestCase;

class RequestAwareViteTest extends TestCase
{
    public function test_hot_asset_uses_config_app_url_instead_of_hot_file(): void
    {
        config(['app.url' => 'http://localhost:8080']);

        $vite = new RequestAwareVite;
        $method = new \ReflectionMethod(RequestAwareVite::class, 'hotAsset');
        $method->setAccessible(true);

        $this->assertSame(
            'http://localhost:8080/@vite/client',
            $method->invoke($vite, '@vite/client'),
        );
    }

    public function test_login_page_vite_tags_use_app_url_when_hot_file_present(): void
    {
        $this->app->singleton(Vite::class, RequestAwareVite::class);

        $hotFile = public_path('hot');
        $hadHotFile = is_file($hotFile);
        $previousContents = $hadHotFile ? (string) file_get_contents($hotFile) : null;

        file_put_contents($hotFile, 'http://192.168.1.116:8080');
        config(['app.url' => 'http://localhost:8080']);

        try {
            $response = $this->get('/login');

            $response->assertOk();
            $response->assertSee('src="http://localhost:8080/@vite/client"', false);
            $response->assertDontSee('src="http://192.168.1.116:8080/@vite/client"', false);
        } finally {
            if ($hadHotFile && $previousContents !== null) {
                file_put_contents($hotFile, $previousContents);
            } elseif (is_file($hotFile)) {
                unlink($hotFile);
            }
        }
    }

    public function test_vite_facade_is_request_aware_implementation_in_local(): void
    {
        if (! app()->environment('local')) {
            $this->assertInstanceOf(Vite::class, app(Vite::class));

            return;
        }

        $this->assertInstanceOf(RequestAwareVite::class, app(Vite::class));
    }
}
