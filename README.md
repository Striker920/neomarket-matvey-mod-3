# NeoMarket Moderation Service

Сервис модерации товаров для платформы NeoMarket.

## Структура

```
src/
├── api/
│   └── events.py          # POST /api/v1/events/product
├── models/
│   ├── product_moderation.py
│   └── field_report.py
├── schemas/
│   └── event.py
├── services/
│   └── event_service.py
├── dependencies/
│   └── service_key.py
├── config.py
├── database.py
├── exceptions.py
└── main.py
```

## Запуск

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## Тесты

```bash
pytest tests/ -v
```

## US-MOD-01: Приём событий от B2B

**Endpoint:** `POST /api/v1/events/product`

**Event types:**
- `CREATED` — создаёт карточку в PENDING
- `EDITED` — возвращает в PENDING очередь
- `DELETED` — удаляет карточку

**Auth:** X-Service-Key

**Response:** `{"accepted": true}`
