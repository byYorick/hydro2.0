import defaultTheme from 'tailwindcss/defaultTheme';
import forms from '@tailwindcss/forms';

/** @type {import('tailwindcss').Config} */
export default {
    content: [
        './vendor/laravel/framework/src/Illuminate/Pagination/resources/views/*.blade.php',
        './storage/framework/views/*.php',
        './resources/views/**/*.blade.php',
        './resources/js/**/*.vue',
    ],

    theme: {
        extend: {
            fontFamily: {
                sans: ['"IBM Plex Sans"', 'Figtree', ...defaultTheme.fontFamily.sans],
                mono: ['"JetBrains Mono"', ...defaultTheme.fontFamily.mono],
            },
            colors: {
                brand: {
                    DEFAULT: 'var(--brand)',
                    soft: 'var(--brand-soft)',
                    ink: 'var(--brand-ink)',
                },
                growth: {
                    DEFAULT: 'var(--growth)',
                    soft: 'var(--growth-soft)',
                },
                warn: {
                    DEFAULT: 'var(--warn)',
                    soft: 'var(--warn-soft)',
                },
                alert: {
                    DEFAULT: 'var(--alert)',
                    soft: 'var(--alert-soft)',
                },
            },
        },
    },

    plugins: [forms],
};
