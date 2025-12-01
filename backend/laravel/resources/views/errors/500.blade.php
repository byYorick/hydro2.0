<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка 500 - Внутренняя ошибка сервера</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #0a0a0a; color: #e5e5e5;
            display: flex; align-items: center; justify-content: center;
            min-height: 100vh; padding: 20px;
        }
        .container { max-width: 600px; width: 100%; text-align: center; }
        .error-code { font-size: 120px; font-weight: bold; color: #ef4444; line-height: 1; margin-bottom: 20px; }
        .error-title { font-size: 24px; font-weight: 600; margin-bottom: 12px; color: #f5f5f5; }
        .error-message { font-size: 16px; color: #a3a3a3; margin-bottom: 30px; line-height: 1.5; }
        .correlation-id { font-size: 12px; color: #525252; margin-bottom: 30px; font-family: monospace; }
        .dev-info { background: #171717; border: 1px solid #262626; border-radius: 8px; padding: 20px; margin-bottom: 30px; text-align: left; font-size: 14px; }
        .dev-info h3 { color: #fbbf24; margin-bottom: 12px; font-size: 16px; }
        .dev-info pre { background: #0a0a0a; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 12px; color: #d1d5db; margin-top: 8px; }
        .actions { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
        .btn { padding: 12px 24px; border-radius: 6px; font-size: 14px; font-weight: 500; text-decoration: none; display: inline-block; transition: all 0.2s; border: none; cursor: pointer; }
        .btn-primary { background: #3b82f6; color: white; }
        .btn-primary:hover { background: #2563eb; }
        .btn-secondary { background: #262626; color: #e5e5e5; border: 1px solid #404040; }
        .btn-secondary:hover { background: #404040; }
    </style>
</head>
<body>
    <div class="container">
        <div class="error-code">500</div>
        <h1 class="error-title">Внутренняя ошибка сервера</h1>
        <p class="error-message">{{ $message ?? 'Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже.' }}</p>
        @if(isset($correlation_id))<div class="correlation-id">ID запроса: {{ $correlation_id }}</div>@endif
        @if(app()->environment(['local', 'testing', 'development']) && isset($exception))
        <div class="dev-info">
            <h3>Детали ошибки (только в dev режиме):</h3>
            <div><strong>Исключение:</strong> {{ $exception }}</div>
            @if(isset($file))<div style="margin-top: 8px;"><strong>Файл:</strong> {{ $file }}:{{ $line ?? 'N/A' }}</div>@endif
        </div>
        @endif
        <div class="actions">
            <a href="/" class="btn btn-primary">На главную</a>
            <button onclick="window.history.back()" class="btn btn-secondary">Назад</button>
        </div>
    </div>
</body>
</html>
