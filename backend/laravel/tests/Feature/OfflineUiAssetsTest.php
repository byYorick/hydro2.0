<?php

namespace Tests\Feature;

use Symfony\Component\Finder\Finder;
use Tests\TestCase;

class OfflineUiAssetsTest extends TestCase
{
    public function test_swagger_html_uses_local_vendor_assets(): void
    {
        $html = (string) file_get_contents(public_path('swagger.html'));

        $this->assertStringNotContainsString('unpkg.com', $html);
        $this->assertStringContainsString('/vendor/swagger-ui/swagger-ui.css', $html);
        $this->assertStringContainsString('/vendor/swagger-ui/swagger-ui-bundle.js', $html);
    }

    public function test_error_404_blade_has_no_cdn_fonts_or_tailwind_play(): void
    {
        $blade = (string) file_get_contents(resource_path('views/errors/404.blade.php'));

        $this->assertStringNotContainsString('fonts.googleapis.com', $blade);
        $this->assertStringNotContainsString('fonts.gstatic.com', $blade);
        $this->assertStringNotContainsString('cdn.tailwindcss.com', $blade);
        $this->assertStringContainsString('@vite', $blade);
        $this->assertStringContainsString('resources/css/error-pages.css', $blade);
    }

    public function test_swagger_ui_vendor_files_exist(): void
    {
        $this->assertFileExists(public_path('vendor/swagger-ui/swagger-ui.css'));
        $this->assertFileExists(public_path('vendor/swagger-ui/swagger-ui-bundle.js'));
    }

    public function test_app_css_has_no_remote_font_stylesheet_imports(): void
    {
        $css = (string) file_get_contents(resource_path('css/app.css'));

        $this->assertStringNotContainsString('fonts.googleapis.com', $css);
        $this->assertStringNotContainsString('fonts.gstatic.com', $css);
        $this->assertDoesNotMatchRegularExpression(
            '/@import\s+url\s*\(\s*[\'"]?https?:\/\//i',
            $css,
            'app.css не должен подключать внешние стили через @import url(http...)'
        );
    }

    public function test_inertia_root_layout_has_no_cdn_links(): void
    {
        $blade = (string) file_get_contents(resource_path('views/app.blade.php'));

        $this->assertStringNotContainsString('fonts.googleapis.com', $blade);
        $this->assertStringNotContainsString('unpkg.com', $blade);
        $this->assertStringNotContainsString('cdn.tailwindcss.com', $blade);
    }

    public function test_all_error_blade_views_avoid_common_cdns(): void
    {
        $dir = resource_path('views/errors');
        $this->assertDirectoryExists($dir);

        $finder = new Finder;
        $finder->files()->in($dir)->name('*.blade.php');

        $forbidden = [
            'fonts.googleapis.com',
            'fonts.gstatic.com',
            'cdn.tailwindcss.com',
            'unpkg.com',
            'jsdelivr.net',
        ];

        foreach ($finder as $file) {
            $contents = $file->getContents();
            foreach ($forbidden as $needle) {
                $this->assertStringNotContainsString(
                    $needle,
                    $contents,
                    sprintf('Файл %s не должен содержать %s', $file->getRelativePathname(), $needle)
                );
            }
        }
    }

    public function test_welcome_page_has_no_external_asset_urls(): void
    {
        $vue = (string) file_get_contents(resource_path('js/Pages/Welcome.vue'));

        $this->assertStringNotContainsString('laravel.com/assets/img', $vue);
        $this->assertStringNotContainsString('https://laravel.com/assets/', $vue);
    }

    /** Политика: в Blade-шаблонах нет строки https:// */
    public function test_blade_views_contain_no_https_scheme(): void
    {
        $dir = resource_path('views');
        $this->assertDirectoryExists($dir);

        $finder = new Finder;
        $finder->files()->in($dir)->name('*.blade.php');

        $needle = 'https://';

        foreach ($finder as $file) {
            $this->assertStringNotContainsString(
                $needle,
                $file->getContents(),
                sprintf('%s не должен содержать %s', $file->getRelativePathname(), $needle)
            );
        }
    }

    /** Политика: в разметке Vue (Pages/Components) нет строки https:// */
    public function test_vue_pages_and_components_contain_no_https_scheme(): void
    {
        $roots = [
            resource_path('js/Pages'),
            resource_path('js/Components'),
        ];

        $needle = 'https://';

        foreach ($roots as $root) {
            if (! is_dir($root)) {
                continue;
            }

            $finder = new Finder;
            $finder->files()->in($root)->name('*.vue');

            foreach ($finder as $file) {
                $this->assertStringNotContainsString(
                    $needle,
                    $file->getContents(),
                    sprintf('%s не должен содержать %s', $file->getRelativePathname(), $needle)
                );
            }
        }
    }
}
