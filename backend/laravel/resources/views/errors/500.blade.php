<!DOCTYPE html>
<html lang="ru">
<head>
    @php
        $brandName = config('app.name', 'Автоматика теплицы');
        if ($brandName === 'Laravel') {
            $brandName = 'Автоматика теплицы';
        }
    @endphp
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>500 - {{ $brandName }}</title>
    <style>
        :root {
            --bg: #f6f3f1;
            --panel: rgba(255, 255, 255, 0.8);
            --panel-strong: rgba(255, 255, 255, 0.94);
            --border: rgba(214, 190, 190, 0.54);
            --text: #191c1e;
            --muted: #5f5656;
            --dim: #877a7a;
            --accent: #ba1a1a;
            --accent-2: #e05b4f;
            --shadow: 0 24px 70px rgba(49, 18, 18, 0.14);
        }
        * { box-sizing: border-box; }
        html, body { margin: 0; min-height: 100%; }
        body {
            min-height: 100vh;
            background:
                radial-gradient(at 0% 0%, rgba(186, 26, 26, 0.06) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(224, 91, 79, 0.05) 0px, transparent 50%),
                var(--bg);
            color: var(--text);
            font-family: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            overflow-x: hidden;
        }
        .page { position: relative; min-height: 100vh; isolation: isolate; }
        .orb { position: fixed; pointer-events: none; z-index: -1; border-radius: 9999px; filter: blur(90px); }
        .orb--one { top: -6rem; left: -6rem; width: 20rem; height: 20rem; background: rgba(186, 26, 26, 0.08); }
        .orb--two { right: -8rem; bottom: -8rem; width: 28rem; height: 28rem; background: rgba(224, 91, 79, 0.08); }
        .topbar { position: sticky; top: 0; z-index: 10; background: rgba(255, 255, 255, 0.72); backdrop-filter: blur(16px); border-bottom: 1px solid rgba(214, 190, 190, 0.36); }
        .topbar__inner, .footer__inner, .shell { width: min(1180px, calc(100% - 2rem)); margin: 0 auto; }
        .topbar__inner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 0; }
        .brand { display: flex; align-items: center; gap: 0.85rem; color: var(--accent); text-decoration: none; }
        .brand__mark {
            width: 2.5rem; height: 2.5rem; border-radius: 0.9rem; display: grid; place-items: center;
            background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff;
            box-shadow: 0 14px 28px rgba(186, 26, 26, 0.18); font-weight: 800; letter-spacing: 0.18em;
        }
        .brand__name { font-size: 1.05rem; font-weight: 800; letter-spacing: -0.03em; }
        .brand__sub { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.26em; color: var(--dim); margin-top: 0.1rem; }
        .topbar__actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        .pill {
            display: inline-flex; align-items: center; gap: 0.45rem; padding: 0.55rem 0.85rem; border-radius: 9999px;
            background: rgba(255, 255, 255, 0.72); border: 1px solid rgba(214, 190, 190, 0.45);
            color: var(--muted); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
        }
        .shell { min-height: calc(100vh - 9rem); display: grid; place-items: center; padding: 2rem 0 4rem; }
        .card {
            width: 100%; display: grid; grid-template-columns: 1.05fr 0.95fr; overflow: hidden;
            border-radius: 2rem; background: var(--panel); border: 1px solid var(--border); box-shadow: var(--shadow); backdrop-filter: blur(16px);
        }
        .card__visual {
            position: relative; min-height: 40rem; padding: 3rem; color: #fff;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%); overflow: hidden;
        }
        .card__visual::before {
            content: ""; position: absolute; inset: 0;
            background:
                radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.18) 0, transparent 28%),
                radial-gradient(circle at 80% 15%, rgba(255, 255, 255, 0.14) 0, transparent 22%);
        }
        .visual__content, .card__body { position: relative; z-index: 1; }
        .visual__brand { display: flex; align-items: center; gap: 0.85rem; margin-bottom: 3rem; }
        .visual__logo {
            width: 2.75rem; height: 2.75rem; display: grid; place-items: center; border-radius: 0.95rem;
            background: rgba(255, 255, 255, 0.2); border: 1px solid rgba(255, 255, 255, 0.2); font-weight: 800; letter-spacing: 0.2em;
        }
        .visual__title { margin: 0; font-size: clamp(2.75rem, 4vw, 4.8rem); line-height: 0.96; letter-spacing: -0.06em; max-width: 12ch; }
        .visual__text { margin: 1.5rem 0 0; max-width: 30rem; color: rgba(255, 255, 255, 0.82); font-size: 1.05rem; line-height: 1.65; }
        .card__body { padding: 3rem 3rem 2.5rem; display: flex; flex-direction: column; justify-content: center; background: var(--panel-strong); }
        .eyebrow { margin: 0 0 0.75rem; font-size: 0.7rem; font-weight: 800; letter-spacing: 0.28em; text-transform: uppercase; color: var(--dim); }
        .body__title { margin: 0; font-size: clamp(2rem, 2.8vw, 3.15rem); line-height: 1.05; letter-spacing: -0.05em; color: var(--text); }
        .body__subtitle { margin: 0.9rem 0 0; max-width: 34rem; font-size: 1.05rem; line-height: 1.7; color: var(--muted); }
        .status { margin-top: 1.5rem; padding: 1rem 1.1rem; border-radius: 1rem; background: rgba(186, 26, 26, 0.08); border: 1px solid rgba(186, 26, 26, 0.18); color: #8f1d1d; font-size: 0.95rem; font-weight: 600; }
        .correlation { margin-top: 1rem; font-size: 0.82rem; color: var(--dim); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        .details { margin-top: 1rem; padding: 1rem 1.1rem; border-radius: 1rem; background: rgba(234, 224, 224, 0.56); border: 1px solid rgba(214, 190, 190, 0.52); color: var(--muted); }
        .details__title { margin: 0 0 0.6rem; font-size: 0.86rem; font-weight: 800; color: var(--accent); }
        .details__meta { margin: 0.45rem 0 0; font-size: 0.82rem; line-height: 1.6; word-break: break-word; }
        .actions { margin-top: 2rem; display: flex; flex-wrap: wrap; gap: 0.75rem; }
        .btn {
            display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem; min-height: 3.1rem;
            padding: 0.85rem 1.1rem; border-radius: 1rem; border: 1px solid transparent; font: inherit; font-weight: 700;
            text-decoration: none; cursor: pointer; transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease, border 0.2s ease;
        }
        .btn:hover { transform: translateY(-1px); }
        .btn--primary { background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%); color: #fff; box-shadow: 0 18px 40px rgba(186, 26, 26, 0.22); }
        .btn--secondary { background: rgba(255, 255, 255, 0.78); border-color: rgba(120, 104, 104, 0.65); color: var(--text); }
        .btn--ghost { background: transparent; border-color: rgba(120, 104, 104, 0.65); color: var(--accent); }
        .footer { border-top: 1px solid rgba(214, 190, 190, 0.34); background: rgba(255, 255, 255, 0.5); }
        .footer__inner {
            display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding: 1rem 0 1.25rem;
            color: var(--muted); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase;
        }
        .footer__links { display: flex; flex-wrap: wrap; gap: 1rem 1.25rem; }
        .footer__links a { color: var(--muted); text-decoration: none; }
        .footer__links a:hover { color: var(--accent); }
        @media (max-width: 960px) {
            .card { grid-template-columns: 1fr; }
            .card__visual { min-height: auto; padding: 2.25rem 1.5rem; }
            .card__body { padding: 2rem 1.5rem 2.25rem; }
        }
        @media (max-width: 640px) {
            .topbar__inner, .footer__inner { width: min(100% - 1rem, 1180px); }
            .topbar__inner { align-items: flex-start; flex-direction: column; }
            .shell { width: min(100% - 1rem, 1180px); padding-top: 1rem; padding-bottom: 2rem; }
            .card { border-radius: 1.35rem; }
            .footer__inner { flex-direction: column; align-items: flex-start; }
        }
    </style>
</head>
<body>
<div class="page">
    <div class="orb orb--one"></div>
    <div class="orb orb--two"></div>

    <header class="topbar">
        <div class="topbar__inner">
            <a class="brand" href="{{ url('/') }}">
                <span class="brand__mark">GI</span>
                <span>
                    <span class="brand__name">{{ $brandName }}</span>
                    <span class="brand__sub">Laboratory control panel</span>
                </span>
            </a>
            <div class="topbar__actions">
                <span class="pill">Статус: 500</span>
                <a class="pill" href="{{ url('/') }}">На главную</a>
            </div>
        </div>
    </header>

    <main class="shell">
        <section class="card">
            <aside class="card__visual">
                <div class="visual__content">
                    <div class="visual__brand">
                        <div class="visual__logo">GI</div>
                        <div>
                            <div style="font-weight: 800; font-size: 1.05rem; letter-spacing: -0.03em;">{{ $brandName }}</div>
                            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.26em; color: rgba(255,255,255,0.64);">Server fault layer</div>
                        </div>
                    </div>

                    <h1 class="visual__title">500</h1>
                    <p class="visual__text">
                        На стороне сервера произошел сбой. Данные и доступ сохранены, но запрос временно не может быть выполнен.
                    </p>
                </div>
            </aside>

            <div class="card__body">
                <p class="eyebrow">Внутренняя ошибка</p>
                <h2 class="body__title">Произошла ошибка сервера</h2>
                <p class="body__subtitle">
                    Сервис столкнулся с неожиданной проблемой. Попробуйте повторить запрос позже или вернитесь на главную страницу.
                </p>

                @isset($correlation_id)
                    <div class="correlation">ID запроса: {{ $correlation_id }}</div>
                @endisset

                @if(isset($message) && $message)
                    <div class="status">{{ $message }}</div>
                @else
                    <div class="status">Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.</div>
                @endif

                @if(app()->environment(['local', 'testing', 'development']) && (isset($exception) || isset($file)))
                    <div class="details">
                        <div class="details__title">Детали ошибки (только в dev режиме)</div>
                        @isset($exception)
                            <div class="details__meta"><strong>Исключение:</strong> {{ $exception }}</div>
                        @endisset
                        @isset($file)
                            <div class="details__meta"><strong>Файл:</strong> {{ $file }}:{{ $line ?? 'N/A' }}</div>
                        @endisset
                    </div>
                @endif

                <div class="actions">
                    <a class="btn btn--primary" href="{{ url('/') }}">На главную</a>
                    <button class="btn btn--secondary" type="button" onclick="window.history.back()">Назад</button>
                    <a class="btn btn--ghost" href="{{ url('/login') }}">Войти</a>
                </div>
            </div>
        </section>
    </main>

    <footer class="footer">
        <div class="footer__inner">
            <div>© {{ date('Y') }} {{ $brandName }}</div>
            <div class="footer__links">
                <a href="{{ url('/') }}">Главная</a>
                <a href="{{ url('/login') }}">Вход</a>
                <a href="{{ url('/dashboard') }}">Панель</a>
            </div>
        </div>
    </footer>
</div>
</body>
</html>
