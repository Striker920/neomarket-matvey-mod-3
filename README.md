# feat(us-mod-06): справочник причин блокировки

## 🎯 Цель

Реализовать справочник причин блокировки товара — словарь, общий для всей платформы. Модератор выбирает из готового списка, продавец видит унифицированную причину, аналитика считает по id.

## 🔍 Контекст

Когда модератор вручную пишет «фото не соответствует», аналитика рушится: «фото плохое», «не то фото», «фото не то» — три разные строки, один смысл. Справочник причин решает эту проблему, обеспечивая:
- **Унификацию** — один id для одной причины
- **Аналитику** — корректная агрегация по причинам
- **Масштабируемость** — новые причины добавляются без релиза

## ✅ Что реализовано

### Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/v1/product-blocking-reasons` | Список активных причин |
| POST | `/api/v1/product-blocking-reasons` | Создать причину (админка) |
| PUT | `/api/v1/product-blocking-reasons/{id}` | Обновить причину (админка) |
| DELETE | `/api/v1/product-blocking-reasons/{id}` | Деактивировать (мягкое удаление) |

### Response (GET)
```json
[
  {
    "id": "uuid",
    "title": "Photo mismatch",
    "description": "Фото товара не соответствует описанию",
    "hard_block": false,
    "is_active": true
  }
]
Тесты
==================================== test session starts =====================================
platform win32 -- Python 3.12.3, pytest-7.4.3, pluggy-1.6.0 -- C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\US-MOD-01\US-MOD-00
plugins: anyio-3.7.1, asyncio-0.21.1
asyncio: mode=Mode.STRICT
collected 6 items                                                                             
16%]
tests/test_blocking_reasons.py::TestBlockingReasons::test_referenced_reason_cannot_be_deleted PASSED [ 50%]
tests/test_blocking_reasons.py::TestBlockingReasons::test_unreferenced_reason_can_be_deactivated PASSED [ 66%]
tests/test_blocking_reasons.py::TestBlockingReasons::test_create_reason PASSED          [ 83%]
tests/test_blocking_reasons.py::TestBlockingReasons::test_hard_block_filter PASSED      [100%]

..\..\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\formparsers.py:10
  C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\Lib\site-packages\starlette\formparsers.py:10: PendingDeprecationWarning: Please use `import python_multipart` instead.
    import multipart

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ 6 passed, 1 warning in 0.26s ===========
