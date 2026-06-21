# feat(us-mod-05): жёсткая блокировка (необратимая)

## 🎯 Цель

Реализовать жёсткую блокировку товара модератором — терминальный статус `HARD_BLOCKED`, после которого карточка не может быть изменена штатными средствами. Это последняя линия защиты каталога от контрафакта, запрещённых товаров и нарушений авторских прав.

## 🔍 Контекст

Контрафакт, запрещённый товар, нарушение авторских прав — есть случаи, где правка не поможет. Жёсткая блокировка — терминальный статус: карточка уходит в `HARD_BLOCKED`, продавец больше ничего с ней не сделает, активные заказы в B2C превращаются в недоступные.

Ошибка модератора стоит дорого — реализация должна быть строгой и без обратного хода в штатном flow. `HARD_BLOCKED` снимается только суперадмином через Django Admin (data-fix с audit log).

## ✅ Что реализовано

### Endpoint
`POST /api/v1/tickets/{ticket_id}/block` — общий с soft-block, маршрут определяется флагом `hard_block` причины.

### Логика
- Переход `IN_REVIEW → HARD_BLOCKED` (терминальный)
- Отправка события `BLOCKED + hard_block=true` в B2B
- Проверка терминальности в каждом мутирующем endpoint

### Защита терминальности
| Сценарий | Поведение |
|----------|-----------|
| `POST /approve` на HARD_BLOCKED | → 403 |
| `POST /block` на HARD_BLOCKED | → 403 |
| `POST /b2b/events` с `PRODUCT_EDITED` на HARD_BLOCKED | → 202 (игнорируется) |
| `POST /b2b/events` с `PRODUCT_DELETED` на HARD_BLOCKED | → 202 (запись удаляется) |

### Формат события BLOCKED

```json
{
  "idempotency_key": "uuid",
  "product_id": "product-123",
  "event_type": "BLOCKED",
  "blocking_reason_id": "uuid",
  "moderator_comment": "Counterfeit product",
  "field_reports": [],
  "hard_block": true,
  "occurred_at": "2026-06-21T10:00:00Z"
}
Лог тестов
platform win32 -- Python 3.12.3, pytest-7.4.3, pluggy-1.6.0 -- C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\US-MOD-05
asyncio: mode=Mode.AUTO

tests/test_mod5_hard_block.py::test_hard_block_transitions_to_terminal_and_emits_event PASSED          [ 20%]
tests/test_mod5_hard_block.py::test_hard_block_event_carries_hard_block_true PASSED                    [ 40%]
tests/test_mod5_hard_block.py::test_any_modify_on_hard_blocked_returns_403 PASSED                      [ 60%]
tests/test_mod5_hard_block.py::test_edited_event_on_hard_blocked_is_ignored PASSED                     [ 80%]
tests/test_mod5_hard_block.py::test_deleted_event_removes_hard_blocked PASSED                          [100%]
