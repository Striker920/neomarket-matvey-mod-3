# fix(us-mod-01): приём событий о товаре от B2B

## 🎯 Цель

Реализовать endpoint `POST /api/v1/b2b/events` для приёма событий о товаре от B2B с идемпотентностью и межсервисной авторизацией.

## 🔍 Контекст

NeoMarket восстанавливается. Каждый листинг проходит через модерацию — без неё каталог наполнят товары-призраки. Продавец завёл карточку в B2B — её должна увидеть Moderation. Отредактировал — карточка возвращается на повторную проверку. Удалил — уходит из очереди. B2B и Moderation общаются событиями.

## ✅ Что реализовано

### Endpoint
`POST /api/v1/b2b/events`

### Request body (IncomingB2BEvent)
```json
{
  "event_type": "PRODUCT_CREATED",
  "idempotency_key": "uuid",
  "occurred_at": "2026-06-22T10:00:00Z",
  "payload": {
    "product_id": "uuid",
    "seller_id": "uuid",
    "product_data": {"title": "...", ...}
  }
}
лог тестов
platform win32 -- Python 3.12.3, pytest-7.4.3, pluggy-1.6.0 -- C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\US-MOD-01\US-MOD-00
plugins: anyio-3.7.1, asyncio-0.21.1
collected 7 items                                                                                              
tests/test_events.py::TestProductEvents::test_edited_returns_to_review PASSED                            [ 28%]
tests/test_events.py::TestProductEvents::test_duplicate_event_no_side_effects PASSED                     [ 71%]
tests/test_events.py::TestProductEvents::test_missing_service_header_401 PASSED                          [ 85%]
tests/test_events.py::TestProductEvents::test_invalid_service_key_401 PASSED                             [100%]

..\..\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\formparsers.py:10
  C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\formparsers.py:10: PendingDeprecationWarning: Please use `import python_multipart` instead.
    import multipart

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
