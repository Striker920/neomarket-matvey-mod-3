# fix(us-mod-01): приём событий о товаре от B2B

## 🎯 Суть задачи
Реализован endpoint `POST /api/v1/b2b/events` для приёма событий о товаре от B2B-системы с поддержкой идемпотентности, межсервисной авторизации и корректной state machine карточки модерации.

## 📋 DoD — Definition of Done

| Критерий | Статус |
|----------|--------|
| Соответствие канон-flow `flows/moderation-flows.md#receive-product-events` | ✅ |
| Соответствие OpenAPI `moderation/openapi.yaml` (часть `/events/product`) | ✅ |
| Сценарий `created_pending` — CREATED создаёт карточку в PENDING | ✅ |
| Сценарий `edited_returns_to_review` — EDITED после APPROVED/BLOCKED возвращает в PENDING | ✅ |
| Сценарий `edited_updates_in_review` — EDITED во время IN_REVIEW сбрасывает в PENDING + обнуляет moderator_id | ✅ |
| Сценарий `deleted_archived` — DELETED удаляет карточку из очереди | ✅ |
| Сценарий `duplicate_event_no_side_effects` — повтор с тем же idempotency_key → 409 | ✅ |
| Сценарий `missing_service_header_401` — без X-Service-Key → 401 | ✅ |
| HARD_BLOCKED — терминальный статус, EDITED игнорируется | ✅ |
| Статус ответа 202 Accepted | ✅ |
| ADR в описании PR | ✅ |
| 5+ pytest | ✅ (8 тестов) |

## 🔧 Что реализовано

### Endpoint
- `POST /api/v1/b2b/events` — приём событий `PRODUCT_CREATED`, `PRODUCT_EDITED`, `PRODUCT_DELETED`
- Статус ответа: **202 Accepted** при успехе
- **409 Conflict** при дублирующем `idempotency_key`
- **401 Unauthorized** при отсутствии/неверном `X-Service-Key`
- **422 Unprocessable Entity** при невалидной схеме события

### Идемпотентность
- Дедупликация по `idempotency_key` через таблицу `processed_events`
- `idempotency_key` валидируется как UUID (format: uuid)
- Запись сохраняется **после** успешной обработки — гарантия at-least-once

### Межсервисная авторизация
- Заголовок `X-Service-Key` (общий ключ маршрутизатора)
- Не путать с JWT пользователя — это service-to-service auth

### State machine карточки
- `PENDING` → `IN_REVIEW` → `APPROVED` / `BLOCKED` / `HARD_BLOCKED`
- `HARD_BLOCKED` — терминальный статус, игнорирует EDITED
- `APPROVED` / `BLOCKED` при EDITED → сброс в `PENDING` (возврат в очередь)
- `IN_REVIEW` при EDITED → сброс в `PENDING` + обнуление `moderator_id`, `moderator_comment`, `date_moderation` (по канону)

### Снапшоты
- `json_after` — текущее состояние карточки (обязательное для CREATED/EDITED)
- `json_before` — предыдущее состояние (для EDITED)
- Значения берутся **из payload события**, без дополнительных HTTP-запросов к B2B

## 🐛 Исправления по фидбэку арбитров

| # | Проблема | Было | Стало |
|---|----------|------|-------|
| 1 | Неправильная структура payload | `product_data: Optional[Dict]` | `json_after: Dict` + `json_before: Optional[Dict]` |
| 2 | Несуществующий статус в enum | `'MODERATED'` в условии | `'APPROVED'` (по `TicketStatus` enum) |
| 3 | Устаревшие данные у модератора | `pass` при `IN_REVIEW` | Сброс в `PENDING` + обнуление `moderator_id` |
| 4 | Pydantic молча отбрасывал поля | Без `extra` | `extra='forbid'` |
| 5 | `idempotency_key` принимал любую строку | Без валидации | Pattern: UUID v4 |

## 📂 Структура изменений

```
src/
├── api/events.py              # endpoint POST /api/v1/b2b/events
├── schemas/event.py           # Pydantic-схемы событий
├── services/event_service.py  # бизнес-логика обработки
├── models/event.py            # ProcessedEvent (идемпотентность)
└── models/moderation_card.py  # ModerationCard

tests/
├── conftest.py                # фикстуры (valid_service_headers, очистка БД)
└── test_events.py             # 8 тестов по канону
```

## 🧪 Тестовое покрытие

| # | Тест | Сценарий |
|---|------|----------|
| 1 | `test_created_pending` | CREATED → PENDING |
| 2 | `test_edited_returns_to_review` | EDITED после APPROVED → PENDING |
| 3 | `test_edited_updates_in_review` | EDITED во время IN_REVIEW → PENDING + обнуление модератора |
| 4 | `test_deleted_archived` | DELETED → удаление карточки |
| 5 | `test_duplicate_event_no_side_effects` | Дубликат → 409 без побочных эффектов |
| 6 | `test_missing_service_header_401` | Нет заголовка → 401 |
| 7 | `test_wrong_service_header_401` | Неверный заголовок → 401 |
| 8 | `test_hard_blocked_ignores_edited` | HARD_BLOCKED игнорирует EDITED |

**Результат:** `8 passed` ✅

## 📐 ADR: Хранение снапшотов карточки

**Контекст.** При каждом EDITED нужно сохранять предыдущее и текущее состояние карточки, чтобы модератор видел diff, а при инцидентах можно было восстановить историю.

**Рассматривал 3 варианта:**

1. **json_before + json_after** (два JSON-поля в карточке)
2. **Full snapshot** (только `json_after`, `json_before` вычисляется запросом к B2B)
3. **Delta** (хранить только diff между версиями)

**Выбрал вариант 1 — `json_before + json_after`.**

**Критерии выбора:**

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 |
|----------|-----------|-----------|-----------|
| Место в БД | ~2× payload | ~1× payload | минимально |
| Сложность диагностики инцидента | ⭐ Низкая (есть оба снимка) | Средняя (нужен запрос к B2B) | ⭐ Высокая (нужно восстанавливать) |
| Удобство для модератора | ⭐ Сразу виден diff | Нужен доп. запрос | Непонятно без восстановления |
| Latency при обработке | ⭐ Нет доп. запросов | +1 HTTP к B2B | ⭐ Нет доп. запросов |

**Итог:** Небольшой перерасход места (~2× payload) окупается простотой диагностики инцидентов и UX модератора. Delta-подход отклонён из-за высокой сложности восстановления полной версии карточки.

## 🔗 Связанные задачи

- **US-B2B-09** (`apply-moderation`) — парный квест, принимает события от Moderation
- **US-MOD-03** — одобрение товара (переводит в `APPROVED`)
- **US-MOD-04** — мягкая блокировка (переводит в `BLOCKED`)
- **US-MOD-05** — жёсткая блокировка (переводит в `HARD_BLOCKED`)

## 🎁 Бонус-возможности (опционально)

- [ ] Внести PR в `neomarket-protocols` с OpenAPI-схемой `/events/product`, если её ещё нет
- [ ] Прокомментировать PR команды US-B2B-09 по формату события — ревью между командами
- [ ] Синхронизировать формат события с US-B2B-09 через PR в `neomarket-protocols`
- [ ] После первых 5 PR-кейсов зафиксировать размеры в `neomarket-protocols`

## 🚀 Запуск локально

```powershell
cd C:\neomarket-matvey-mod-3-feature-us-mod-01-receive-events
C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_events.py -v
```

**Ожидаемый результат:** `8 passed` ✅

## 📎 Источники

- Канон-flow: `flows/moderation-flows.md#receive-product-events`
- OpenAPI: `moderation/openapi.yaml` (часть `/events/product`)
- Межсервисная авторизация: `flows/auth-flows.md`
