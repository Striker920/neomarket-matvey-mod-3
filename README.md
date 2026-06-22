# feat(us-mod-05): жёсткая блокировка товара (необратимая)

## 🎯 Суть задачи
Реализована жёсткая блокировка товара модератором — терминальный статус `HARD_BLOCKED`, из которого нет возврата в штатном flow. Контрафакт, запрещённый товар, нарушение авторских прав — случаи, где правка не поможет.

- Endpoint `POST /api/v1/tickets/{ticket_id}/block` с причиной `hard_block=true`
- Переход `IN_REVIEW → HARD_BLOCKED` (терминальный статус)
- Отправка события `BLOCKED` с `hard_block=true` в B2B для каскада в B2C
- Защита от любых правок после блокировки (403)
- EDITED события от продавца игнорируются
- DELETED события удаляют запись из очереди

## 📋 DoD — Definition of Done

| Критерий | Статус |
|----------|--------|
| Соответствие канон-flow `flows/moderation-flows.md#hard-block` | ✅ |
| Соответствие OpenAPI `moderation/openapi.yaml` | ✅ |
| Сценарий `hard_block_transitions_to_terminal_and_emits_event` | ✅ |
| Сценарий `hard_block_event_carries_hard_block_true` | ✅ |
| Сценарий `any_modify_on_hard_blocked_returns_403` | ✅ |
| Сценарий `edited_event_on_hard_blocked_is_ignored` | ✅ |
| Сценарий `deleted_event_removes_hard_blocked` | ✅ |
| Статус ответа 200 OK | ✅ |
| ADR в описании PR | ✅ |
| 5+ pytest | ✅ (5 тестов) |

## 🔧 Что реализовано

### Endpoint
- `POST /api/v1/tickets/{ticket_id}/block` — общий с soft-block, маршрут определяется флагом `hard_block` причины
- Переход `IN_REVIEW → HARD_BLOCKED` (терминальный статус)
- Отправка события `BLOCKED` с `hard_block=true` в B2B

### Терминальность
- Проверка `HARD_BLOCKED` перед каждой мутацией (approve, block)
- Повторный approve/block → **403 Forbidden**
- EDITED события от B2B → **202 Accepted** (идемпотентно игнорируются)
- DELETED события → удаление записи (товар остаётся заблокированным в B2B)

### Проверки
- Карточка существует (404)
- Не HARD_BLOCKED (403)
- Статус IN_REVIEW (409)
- Закреплён за текущим модератором (403)
- `blocking_reason_ids[]` не пустой (400)
- Причина существует в справочнике (400)

### Формат ошибок
- Плоский формат: `{"code": "...", "message": "..."}` (без обёртки `detail`)
- Соответствует спецификации `moderation/openapi.yaml:563-568`

## 🐛 Исправления по фидбэку арбитров

| # | Проблема | Было | Стало |
|---|----------|------|-------|
| 1 | Формат ошибок | `{"detail": {"code":..., "message":...}}` | `{"code":..., "message":...}` |
| 2 | `_send_to_b2b` использует `ASGITransport` | Запрос внутри Moderation → 404 | Реальный HTTP-клиент с `B2B_BASE_URL` |
| 3 | Событие не доходит до B2B | `except Exception: pass` (молча) | Логирование с `print()` + детали |
| 4 | Хардкод `X-Service-Key` в тестах | `"moderation-service-secret-key"` | `APP_CONFIG.B2B_SERVICE_KEY` |

## 📂 Структура изменений

```
app/
├── api/v1/
│   ├── common.py                    # ✅ error_response(): плоский формат
│   └── moderation_service.py        # ✅ _send_to_b2b: реальный HTTP-клиент
│                                     # ✅ Терминальность HARD_BLOCKED
│                                     # ✅ EDITED/DELETED события
└── infrastructure/config/config.py  # APP_CONFIG с B2B_BASE_URL

tests/
└── test_mod5_hard_block.py          # ✅ 5 тестов по канону
```

## 🧪 Тестовое покрытие

| # | Тест | Сценарий |
|---|------|----------|
| 1 | `test_hard_block_transitions_to_terminal_and_emits_event` | Happy path: HARD_BLOCKED + событие в B2B |
| 2 | `test_hard_block_event_carries_hard_block_true` | Флаг `hard_block=true` в событии |
| 3 | `test_any_modify_on_hard_blocked_returns_403` | Любая правка (approve/block) → 403 |
| 4 | `test_edited_event_on_hard_blocked_is_ignored` | EDITED от B2B не выводит из терминала |
| 5 | `test_deleted_event_removes_hard_blocked` | DELETED удаляет запись из Moderation |

**Результат:** `5 passed` ✅

## 📐 ADR: Гарантия необратимости HARD_BLOCKED

**Контекст.** Жёсткая блокировка — терминальный статус. Ошибка модератора стоит дорого, поэтому необратимость должна быть гарантирована на уровне кода, а не только на уровне UI.

**Рассматривал 3 варианта:**

1. **Терминальный enum-статус с проверкой на каждом мутирующем endpoint** — проверка `if status == 'HARD_BLOCKED'` перед каждой мутацией
2. **Отдельный флаг `is_terminal` в схеме** — булево поле, вычисляемое из статуса
3. **Выделение HARD_BLOCKED в отдельную таблицу-архив** — физическое разделение активных и заблокированных карточек

**Выбрал вариант 1 — терминальный enum-статус с проверкой на каждом endpoint.**

**Критерии выбора:**

| Критерий | Вариант 1 | Вариант 2 | Вариант 3 |
|----------|-----------|-----------|-----------|
| Риск случайной правки в обход защиты | ⭐ Минимальный (проверка в одном месте перед каждой мутацией) | Средний (флаг может рассинхронизироваться со статусом) | ⭐ Минимальный (физическое разделение) |
| Сложность аудита | ⭐ Низкая (статус виден в БД, простая выборка) | Средняя (нужно проверять 2 поля) | Высокая (JOIN между таблицами) |
| Поведение при экстренном data-fix через админку | ⭐ Удобное (суперадмин через Django Admin меняет статус с обязательным audit log — штатный flow не затрагивается) | Среднее (нужно менять 2 поля) | Сложное (перенос между таблицами) |

**Итог:** Терминальный enum-статус даёт минимальный риск случайной правки (проверка в одном месте перед каждой мутацией), низкую сложность аудита (статус виден в БД) и удобное поведение при data-fix (суперадмин через Django Admin меняет статус с обязательным audit log, штатный flow не затрагивается). Вариант 2 избыточен (флаг дублирует статус и может рассинхронизироваться), вариант 3 усложняет миграции и работу с историей карточки.

## 🔗 Связанные задачи

- **US-MOD-03** (approve) — проверяет HARD_BLOCKED перед одобрением
- **US-MOD-04** (soft-block) — общий endpoint `/block`, маршрутизация по флагу `hard_block`
- **US-MOD-06** (справочник причин) — содержит `hard_block=true` для жёстких причин
- **US-B2B-09** (apply-moderation) — парный квест, принимает событие `BLOCKED` + `hard_block=true` и инициирует каскад в B2C

## 🎁 Бонус-возможности (опционально)

- [ ] Внести PR в `neomarket-protocols` с OpenAPI-схемой event `BLOCKED` + `hard_block=true`, если её ещё нет
- [ ] Прокомментировать PR команды US-B2B-09 по каскаду в B2C — ревью между командами засчитывается

## 🚀 Запуск локально

```powershell
cd C:\neomarket-matvey-mod-3-main
C:\Users\matvey_chertovikov\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_mod5_hard_block.py -v
```

**Ожидаемый результат:** `5 passed` ✅

## 📎 Источники

- Канон-flow: `flows/moderation-flows.md#hard-block`
- OpenAPI: `moderation/openapi.yaml`
- Парный квест: US-B2B-09 (apply-moderation)
- Связан: US-MOD-06 (справочник причин с `hard_only=true`)
