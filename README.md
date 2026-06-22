# fix(us-mod-03): одобрение товара модератором

## 🎯 Суть задачи
Реализован endpoint `POST /api/v1/tickets/{ticket_id}/approve` для одобрения товара модератором:
- Переход карточки из `IN_REVIEW` → `APPROVED`
- Отправка события `MODERATED` в B2B
- Проверки: закреплён за модератором, не HARD_BLOCKED, есть SKU, не было EDITED

## 📋 DoD — Definition of Done

| Критерий | Статус |
|----------|--------|
| Соответствие канон-flow `flows/moderation-flows.md#approve-product` | ✅ |
| Соответствие OpenAPI `moderation/openapi.yaml` | ✅ |
| Сценарий `approve_transitions_to_moderated_and_emits_event` | ✅ |
| Сценарий `approve_others_card_returns_403` | ✅ |
| Сценарий `approve_after_edited_returns_409` | ✅ |
| Сценарий `approve_without_sku_returns_409` | ✅ |
| Статус ответа 200 OK | ✅ |
| ADR в описании PR | ✅ |
| 4+ pytest | ✅ (4 теста) |

## 🔧 Что реализовано

### Endpoint
- `POST /api/v1/tickets/{ticket_id}/approve` — одобрение товара
- Переход `IN_REVIEW → APPROVED`
- Отправка события `MODERATED` в B2B

### Проверки
- Карточка существует (404)
- Не HARD_BLOCKED (403)
- Статус IN_REVIEW (409)
- Закреплён за текущим модератором (403)
- Есть SKU (409)

### Формат ответа
- Плоский формат ошибок: `{"code": "...", "message": "..."}` (без обёртки `detail`)
- Правильные имена полей: `id`, `kind`, `created_at` (по OpenAPI)

## 🐛 Исправления по фидбэку арбитров

| # | Проблема | Было | Стало |
|---|----------|------|-------|
| 1 | Неправильный статус | `MODERATED` | `APPROVED` (по TicketStatus enum) |
| 2 | Неправильные поля ответа | `ticket_id`, `date_created`, нет `kind` | `id`, `created_at`, `kind` |
| 3 | Неправильный путь события | `/api/v1/b2b/events` | `/api/v1/moderation/events` |
| 4 | Нет проверки X-Service-Key | Не проверялся | Проверяется через `require_service_key()` |
| 5 | Нет заголовка X-Service-Key | Отсутствовал | Добавлен в исходящих событиях |
| 6 | Неправильный формат ошибок | `{"detail": "..."}` | `{"code": "...", "message": "..."}` |

## 📂 Структура изменений

```
app/
├── core/
│   ├── base.py          # ServiceError, utcnow, iso
│   ├── config.py        # Настройки приложения
│   └── store.py         # NeoMarketStore (in-memory)
├── api/v1/
│   ├── common.py        # error_response, get_store, require_service_key
│   └── moderation_service.py  # Endpoint approve/block/receive_event
└── main.py              # FastAPI app + startup event

tests/
└── test_mod3_approve.py # 4 теста по канону
```

## 🧪 Тестовое покрытие

| # | Тест | Сценарий |
|---|------|----------|
| 1 | `test_approve_transitions_to_approved_and_emits_event` | Happy path: APPROVED + событие в B2B |
| 2 | `test_approve_others_card_returns_403` | Чужая карточка → 403 |
| 3 | `test_approve_after_edited_returns_409` | Продавец редактировал → 409 |
| 4 | `test_approve_without_sku_returns_409` | Нет SKU → 409 |

**Результат:** `4 passed` ✅

## 📐 ADR: Доставка события MODERATED в B2B

**Контекст.** После одобрения товара нужно отправить событие `MODERATED` в B2B, чтобы товар попал в каталог.

**Рассматривал 3 варианта:**

1. **Синхронный POST в обработчике approve** — отправляем событие сразу, ждём ответа
2. **Outbox-pattern с фоновой отправкой** — сохраняем событие в БД, фоновый воркер отправляет
3. **Event-bus (Kafka/RabbitMQ)** — публикуем событие в шину, B2B подписывается

**Выбрал вариант 1 — синхронный POST с fire-and-forget.**

**Критерии выбора:**

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 |
|----------|-----------|-----------|-----------|
| Надёжность при отказе B2B | ⭐ Средняя (логируем ошибку) | ⭐ Высокая (guaranteed delivery) | ⭐ Высокая (broker) |
| Сложность реализации | ⭐ Низкая (простой HTTP) | Высокая (БД + воркер) | Высокая (broker + consumer) |
| Время отклика для модератора | ⭐ Быстрое (не ждём B2B) | ⭐ Быстрое (async) | ⭐ Быстрое (async) |

**Итог:** Синхронный POST с fire-and-forget даёт минимальную сложность реализации, быстрое время отклика для модератора (не ждём подтверждения от B2B), и достаточную надёжность (ошибки логируются). Outbox-pattern и event-bus избыточны для текущей нагрузки.

## 🔗 Связанные задачи

- **US-MOD-01** — приём событий о товаре от B2B
- **US-MOD-02** — получение следующей карточки из очереди
- **US-MOD-04** — мягкая блокировка с замечаниями
- **US-MOD-05** — жёсткая блокировка
- **US-B2B-09** (apply-moderation) — парный квест, принимает событие MODERATED

## 🎁 Бонус-возможности (опционально)

- [ ] Внести PR в `neomarket-protocols` с OpenAPI-схемой `/approve` и event-схемой `MODERATED`, если их ещё нет
- [ ] Прокомментировать PR команды US-B2B-09 по формату события — ревью между командами

## 🚀 Запуск локально

```powershell
cd C:\neomarket-matvey-mod-3-main
C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_mod3_approve.py -v
```

**Ожидаемый результат:** `4 passed` ✅

## 📎 Источники

- Канон-flow: `flows/moderation-flows.md#approve-product`
- OpenAPI: `moderation/openapi.yaml`
