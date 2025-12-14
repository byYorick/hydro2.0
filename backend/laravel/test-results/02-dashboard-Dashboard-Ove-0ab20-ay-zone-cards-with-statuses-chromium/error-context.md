# Page snapshot

```yaml
- generic [ref=e2]:
  - generic [ref=e3]: "500"
  - heading "Внутренняя ошибка сервера" [level=1] [ref=e4]
  - paragraph [ref=e5]: The route dashboard could not be found.
  - generic [ref=e6]: "ID запроса: req_693ed496bd9f7_aa8960c5"
  - generic [ref=e7]:
    - heading "Детали ошибки (только в dev режиме):" [level=3] [ref=e8]
    - generic [ref=e9]:
      - strong [ref=e10]: "Исключение:"
      - text: Symfony\Component\HttpKernel\Exception\NotFoundHttpException
    - generic [ref=e11]:
      - strong [ref=e12]: "Файл:"
      - text: /app/vendor/laravel/framework/src/Illuminate/Routing/AbstractRouteCollection.php:45
  - generic [ref=e13]:
    - link "На главную" [ref=e14] [cursor=pointer]:
      - /url: /
    - button "Назад" [ref=e15] [cursor=pointer]
```