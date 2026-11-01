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
                telemetry: ['"JetBrains Mono"', ...defaultTheme.fontFamily.mono],
            },
            fontSize: {
                eyebrow: ['0.68rem', { lineHeight: '1.2', letterSpacing: '0.16em' }],
                telemetry: ['1.75rem', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
                'telemetry-sm': ['1.25rem', { lineHeight: '1.15', letterSpacing: '-0.02em' }],
            },
            spacing: {
                page: '1rem',
                section: '1.25rem',
            },
            borderRadius: {
                card: '1.2rem',
                control: '0.7rem',
            },
            boxShadow: {
                card: 'var(--shadow-card)',
                elevated: 'var(--shadow-elevated)',
            },
            colors: {
                canvas: 'var(--bg-main)',
                surface: {
                    DEFAULT: 'var(--bg-surface)',
                    strong: 'var(--bg-surface-strong)',
                    elevated: 'var(--bg-elevated)',
                },
                ink: {
                    DEFAULT: 'var(--text-primary)',
                    muted: 'var(--text-muted)',
                    dim: 'var(--text-dim)',
                },
                line: {
                    DEFAULT: 'var(--border-muted)',
                    strong: 'var(--border-strong)',
                },
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
                status: {
                    ok: 'var(--status-ok)',
                    'ok-soft': 'var(--status-ok-soft)',
                    warning: 'var(--status-warning)',
                    'warning-soft': 'var(--status-warning-soft)',
                    critical: 'var(--status-critical)',
                    'critical-soft': 'var(--status-critical-soft)',
                    offline: 'var(--status-offline)',
                    'offline-soft': 'var(--status-offline-soft)',
                    info: 'var(--status-info)',
                    'info-soft': 'var(--status-info-soft)',
                },
            },
        },
    },

    plugins: [forms],
};
