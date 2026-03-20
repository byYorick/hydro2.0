<!DOCTYPE html>
<html class="light" lang="ru">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
@php
    $brandName = config('app.name', 'Greenhouse Intelligence');
    if ($brandName === 'Laravel') {
        $brandName = 'Greenhouse Intelligence';
    }
@endphp
<title>404 - {{ $brandName }}</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&amp;family=Inter:wght@400;500;600&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script id="tailwind-config">
      tailwind.config = {
        darkMode: "class",
        theme: {
          extend: {
            colors: {
              "secondary-container": "#d0e1fb",
              "on-tertiary": "#ffffff",
              "primary-fixed-dim": "#8bd6b6",
              "on-surface": "#191c1e",
              "on-primary": "#ffffff",
              "tertiary": "#3b5d45",
              "surface-container-high": "#e6e8ea",
              "surface-variant": "#e0e3e5",
              "error-container": "#ffdad6",
              "on-secondary-fixed": "#0b1c30",
              "inverse-primary": "#8bd6b6",
              "on-primary-fixed-variant": "#00513b",
              "on-primary-container": "#bfffe2",
              "on-background": "#191c1e",
              "inverse-surface": "#2d3133",
              "outline": "#707a6c",
              "surface": "#f7f9fb",
              "error": "#ba1a1a",
              "on-error-container": "#93000a",
              "surface-container": "#eceef0",
              "primary-fixed": "#a6f2d1",
              "on-error": "#ffffff",
              "surface-dim": "#d8dadc",
              "secondary": "#505f76",
              "outline-variant": "#bfcaba",
              "on-tertiary-container": "#d4fcdb",
              "tertiary-fixed": "#c5eccc",
              "surface-container-highest": "#e0e3e5",
              "on-primary-fixed": "#002116",
              "on-surface-variant": "#40493d",
              "on-tertiary-fixed": "#00210e",
              "secondary-fixed": "#d3e4fe",
              "tertiary-container": "#53765c",
              "on-secondary-fixed-variant": "#38485d",
              "background": "#f7f9fb",
              "primary-container": "#2f7b60",
              "on-tertiary-fixed-variant": "#2c4e36",
              "tertiary-fixed-dim": "#aad0b1",
              "surface-tint": "#1b6b51",
              "secondary-fixed-dim": "#b7c8e1",
              "inverse-on-surface": "#eff1f3",
              "surface-bright": "#f7f9fb",
              "primary": "#0b6148",
              "on-secondary": "#ffffff",
              "surface-container-low": "#f2f4f6",
              "surface-container-lowest": "#ffffff",
              "on-secondary-container": "#54647a"
            },
            fontFamily: {
              "headline": ["Manrope"],
              "body": ["Inter"],
              "label": ["Inter"]
            },
            borderRadius: {"DEFAULT": "0.25rem", "lg": "0.5rem", "xl": "0.75rem", "full": "9999px"},
          },
        },
      }
    </script>
<style>
        .material-symbols-outlined {
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }
        .organic-path {
            clip-path: polygon(10% 0%, 100% 0%, 90% 100%, 0% 100%);
        }
        .glass-panel {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(12px);
        }
    </style>
</head>
<body class="bg-surface font-body text-on-surface overflow-hidden">
<!-- TopAppBar -->
<header class="bg-white/70 dark:bg-emerald-950/70 backdrop-blur-xl text-emerald-800 dark:text-emerald-100 font-manrope font-bold tracking-tight docked full-width top-0 sticky shadow-sm dark:shadow-none z-50">
<div class="flex justify-between items-center w-full px-6 py-4 max-w-full">
<a class="text-xl font-extrabold text-emerald-900 dark:text-emerald-50 tracking-tighter" href="{{ url('/') }}">
                {{ $brandName }}
            </a>
<div class="flex items-center gap-4">
<button class="material-symbols-outlined p-2 rounded-full hover:bg-emerald-50/50 dark:hover:bg-emerald-900/50 transition-colors scale-98 duration-200 ease-out" data-icon="account_circle" type="button">account_circle</button>
<button class="material-symbols-outlined p-2 rounded-full hover:bg-emerald-50/50 dark:hover:bg-emerald-900/50 transition-colors scale-98 duration-200 ease-out" data-icon="notifications" type="button">notifications</button>
</div>
</div>
</header>
<main class="relative min-h-screen flex flex-col items-center justify-center px-6 py-20 overflow-hidden">
<!-- Decorative Background Elements: System Logs covered by Ivy -->
<div class="absolute inset-0 z-0 pointer-events-none opacity-20 select-none">
<div class="absolute top-20 left-10 max-w-xs font-mono text-[10px] text-secondary leading-tight space-y-1">
<p>[SYSTEM_INIT] Sector 7G sequence engaged...</p>
<p>[WARNING] Unusual biometric readings detected.</p>
<p>[CRITICAL] Root penetration in Server Rack A-12.</p>
<p>[LOG] Photosynthesis levels exceeding safety parameters.</p>
<p>[ERROR] Data packet corrupted by chlorophyll. 0x00404</p>
</div>
<div class="absolute bottom-20 right-10 max-w-xs font-mono text-[10px] text-secondary text-right leading-tight space-y-1">
<p>STATUS: OVERGROWN</p>
<p>LOCAL_ENV: TROPICAL_DENSE</p>
<p>RECOVERY: IMPOSSIBLE</p>
<p>LINK_INTEGRITY: 0%</p>
</div>
<!-- Organic Textures/Vines via Images -->
<img alt="" class="absolute -top-20 -right-20 w-80 h-80 rotate-12 opacity-40 mix-blend-multiply" data-alt="Close up of green ivy leaves against a white wall" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDWqIOZoJ9PquRh5nf7jL0bRZUF3qZHaKk6gqX2PY-K48nzHXrPy82pZxeVhdxXlFYI93zi_wsYiAj_CS7vJJa8jKc6CPaj8yjbwrSscUhiSmvq_AGN56qiJcU4CVT0QIwaS_1NyQ5xaEFzJCP7pjVHk-C6qGW25eFNyIdGaGhwcvJ6tUd4tB8jQbJxfLXYpkS8PyZOiivYVtOeTZwCHHKwZLvX4v8lUBrzPba0yQuJJNmIPqRTqcriYo4hsXG3nWdedx2rKRZCCXU"/>
<img alt="" class="absolute -bottom-10 -left-10 w-96 h-96 -rotate-12 opacity-30 mix-blend-multiply" data-alt="Hanging vines and monstera leaves silhouette" src="https://lh3.googleusercontent.com/aida-public/AB6AXuCoyZ9Exv7Xf90R1M_ACJOndIk6gbDeZ79suPyB6aigBPqhLuOSrtS1yQmZ9kCNs7v_f-W7Hcfta01BkU-LFP9QUPhSeQcwxHMYTvDrr6NuryvDi-tpAjLmXof1OYWOnB7zsbE7Oy8J-4z9_JFCF1fGjxrhUsLM5AvhPvqok2oUBpp5v0Q9IxsDGv02__foDfhkVcbHoeAdEtiNWHWqDAlLMnC5CimTOoQPOr89LiOcITOYbR_yybBbnQ__VGUytDNLBfaiKQAxXZU"/>
</div>
<!-- Hero 404 Visual -->
<div class="relative z-10 flex flex-col items-center">
<div class="relative mb-8">
<!-- Large Stylized 404 -->
<h1 class="text-[12rem] md:text-[18rem] font-headline font-extrabold tracking-tighter text-surface-container-high relative leading-none">
                    404
                    <!-- Overlaying Vines -->
<span class="absolute inset-0 flex items-center justify-center">
<img alt="" class="w-full h-full object-contain mix-blend-overlay opacity-90" data-alt="Lush green tropical vines wrapping around white numbers" src="https://lh3.googleusercontent.com/aida-public/AB6AXuAeoY4MYmgiIiTnSIeNUb_mPvZx40NszZJXVbWTTs2QCZSlSzNv4_GfKDc4L7ccEa2_sJRGBT9Ml5EMRRQfsQsdGTuyv2zwE35dwmutJrrDDo4YVToRdTLp5H0IsSRhawYSjBEXZWlQAD7wvXpMHfEWfocjA1woQ7tBYw2GaHwPGFaHC61Q1jnFxZUAVzxxvl2ayIxVNobhOzIJS1cKCbn_OCTtp10GcepRX9zlI_f2UJMbkUYMXp573Ivi9oMYy-UkDm-1zyI0w4E"/>
</span>
</h1>
<!-- Floating Glass Tile Data Points -->
<div class="absolute -top-4 -right-8 glass-panel px-4 py-2 rounded-xl shadow-sm border border-outline-variant/10 text-xs font-label uppercase tracking-widest text-primary font-bold">
<span class="flex items-center gap-2">
<span class="w-2 h-2 rounded-full bg-tertiary animate-pulse shadow-[0_0_8px_#3b5d45]"></span>
                        Bio-Anomaly Detected
                    </span>
</div>
</div>
<!-- Error Messages -->
<div class="text-center max-w-2xl space-y-6">
<h2 class="text-4xl md:text-5xl font-headline font-extrabold text-primary tracking-tight">
                    Биологический сбой: Сектор поглощен флорой
                </h2>
<p class="text-lg md:text-xl text-secondary font-body leading-relaxed">
                    Похоже, растения проросли сквозь наши серверы и эта ссылка больше не существует. Возвращайтесь в лабораторию, пока джунгли не захватили всё.
                </p>
</div>
<!-- CTA -->
<div class="mt-12">
<a class="group relative flex items-center gap-3 px-10 py-5 bg-gradient-to-br from-primary to-primary-container text-on-primary rounded-[1.5rem] rounded-tr-[0.5rem] rounded-bl-[0.5rem] font-headline font-bold text-lg shadow-xl hover:shadow-primary/20 transition-all active:scale-95 overflow-hidden" href="{{ url('/') }}">
<span class="material-symbols-outlined" data-icon="eco">eco</span>
                    Вернуться в лабораторию
                    <!-- Leaf effect on hover -->
<div class="absolute -right-2 -bottom-2 opacity-10 group-hover:opacity-30 transition-opacity">
<span class="material-symbols-outlined text-6xl" data-icon="psychology">psychology</span>
</div>
</a>
</div>
</div>
<!-- Background subtle data aesthetic -->
<div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[80vw] h-[819px] border border-outline-variant/5 rounded-full pointer-events-none"></div>
<div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[60vw] h-[614px] border border-outline-variant/10 rounded-full pointer-events-none"></div>
</main>
<!-- Footer -->
<footer class="bg-emerald-50 dark:bg-emerald-950/40 text-emerald-900 dark:text-emerald-100 font-inter text-xs uppercase tracking-widest font-semibold full-width bottom-0 border-t border-emerald-900/5 dark:border-emerald-100/5 opacity-80 hover:opacity-100 duration-300 z-50">
<div class="flex flex-col md:flex-row justify-between items-center w-full px-12 py-8 gap-6">
<div>© {{ date('Y') }} Organic Precision Systems. Rooted in Intelligence.</div>
<div class="flex gap-8">
<a class="hover:text-emerald-600 dark:hover:text-emerald-400 transition-all" href="{{ url('/') }}">System Status</a>
<a class="hover:text-emerald-600 dark:hover:text-emerald-400 transition-all" href="{{ url('/dashboard') }}">Growth Documentation</a>
<a class="hover:text-emerald-600 dark:hover:text-emerald-400 transition-all" href="{{ url('/login') }}">Support Lattice</a>
<a class="hover:text-emerald-600 dark:hover:text-emerald-400 transition-all" href="{{ url('/') }}">Privacy Foliage</a>
</div>
</div>
</footer>
</body></html>
