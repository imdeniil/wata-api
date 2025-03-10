# Payment API Client

Клиентская библиотека для работы с платежным API с поддержкой иерархического логирования.

Внимание, это неофициальная версия, вы используете ее на свой страх и риск, обновление и поддержка не осуществляются.

[![PyPI version](https://badge.fury.io/py/payment-api.svg)](https://badge.fury.io/py/payment-api)
[![Python versions](https://img.shields.io/pypi/pyversions/payment-api.svg)](https://pypi.org/project/payment-api/)

## Установка

```bash
pip install wata-api
```

## Описание

Payment API Client предоставляет следующие возможности:

- ✅ Иерархическое логирование для всех компонентов системы
- ✅ Управление платежными ссылками (создание, получение и поиск)
- ✅ Обработка вебхуков с проверкой криптографической подписи
- ✅ Поддержка асинхронных операций (async/await)
- ✅ Контекстные менеджеры для автоматического закрытия соединений

## Быстрый старт

### Инициализация клиента

```python
import asyncio
import logging
from wata import PaymentClient

async def main():
    # Инициализация клиента (реализует паттерн Singleton)
    client = PaymentClient.initialize(
        api_key="your_api_key_here", 
        base_url="https://api.payment-provider.com",
        log_level=logging.INFO
    )
    
    # Использование API...
    
    # Закрытие соединений
    await client.close()

asyncio.run(main())
```

### Создание платежа

```python
import asyncio
import decimal
from wata import PaymentClient

async def create_payment():
    client = PaymentClient.initialize(
        api_key="your_api_key_here", 
        base_url="https://api.payment-provider.com"
    )
    
    # Создание платежа
    payment = await client.payment.create(
        amount=decimal.Decimal("299.99"),
        currency="RUB",
        description="Оплата заказа #12345",
        order_id="ORDER-12345",
        success_redirect_url="https://yourshop.com/payment/success",
        fail_redirect_url="https://yourshop.com/payment/fail"
    )
    
    print(f"Платеж создан: ID={payment['id']}")
    print(f"Ссылка для оплаты: {payment['paymentUrl']}")
    
    await client.close()

asyncio.run(create_payment())
```

## Подробная документация

### Инициализация клиента

Клиент реализует паттерн Singleton и может быть инициализирован только один раз.

```python
import logging
from wata import PaymentClient

# Инициализация клиента
client = PaymentClient.initialize(
    api_key="your_api_key_here",
    base_url="https://api.payment-provider.com",
    log_level=logging.DEBUG  # Устанавливаем детальный уровень логирования
)

# Получение существующего экземпляра
client = PaymentClient.get_instance()
```

### Модуль платежей

#### Создание платежа

```python
payment_result = await client.payment.create(
    amount=decimal.Decimal("299.99"),  # Также поддерживаются int и float
    currency="RUB",
    description="Оплата заказа #12345",
    order_id="ORDER-12345",
    success_redirect_url="https://yourshop.com/payment/success",
    fail_redirect_url="https://yourshop.com/payment/fail"
)
```

#### Получение информации о платежной ссылке

```python
# UUID платежной ссылки
payment_link_uuid = "550e8400-e29b-41d4-a716-446655440000"

# Получение информации о платежной ссылке
link_info = await client.payment.get_link_by_uuid(payment_link_uuid)

print(f"Статус: {link_info['status']}")
print(f"Сумма: {link_info['amount']} {link_info['currency']}")
print(f"Создан: {link_info['creationTime']}")
```

#### Поиск платежей с фильтрацией

```python
from datetime import datetime, timedelta

# Параметры для поиска платежей
one_week_ago = datetime.now() - timedelta(days=7)

# Поиск платежей
search_result = await client.payment.search_links(
    amount_from=1000,
    amount_to=5000,
    creation_time_from=one_week_ago,
    currencies=["RUB", "USD"],
    statuses=["Opened", "Closed"],
    sorting="creationTime desc",
    max_result_count=50
)

# Обработка результатов поиска
if "items" in search_result and search_result["items"]:
    print(f"Найдено платежей: {len(search_result['items'])}")
    
    for item in search_result["items"]:
        print(f"Платеж {item['id']}: {item['amount']} {item['currency']}, статус: {item['status']}")
```

### Работа с вебхуками

#### Получение публичного ключа

```python
# Получение публичного ключа для проверки подписей вебхуков
public_key = await client.webhook.get_public_key()

# Принудительное обновление ключа
refreshed_key = await client.webhook.get_public_key(force_refresh=True)
```

#### Проверка подписи вебхука вручную

```python
# Проверка подписи вебхука
signature = "base64_encoded_signature_from_header"
webhook_data = '{"orderId": "123", "transactionStatus": "Success"}'

is_valid = await client.webhook.verify_signature(signature, webhook_data)
if is_valid:
    # Обработка данных вебхука
    webhook_json = json.loads(webhook_data)
    # ...
```

#### Обработка вебхука в aiohttp-сервере

```python
from aiohttp import web

# Пример обработчика вебхуков для aiohttp
async def webhook_handler(request):
    # Получение подписи из заголовка
    signature = request.headers.get('X-Signature')
    if not signature:
        return web.Response(status=400, text="Отсутствует подпись")
    
    # Получение данных вебхука
    webhook_data = await request.text()
    
    # Получение клиента API
    client = PaymentClient.get_instance()
    
    try:
        # Проверка подписи и обработка данных
        processed_data = await client.webhook.process_webhook(signature, webhook_data)
        
        # Обработка платежа в зависимости от статуса транзакции
        status = processed_data.get('transactionStatus')
        order_id = processed_data.get('orderId')
        
        if status == 'Success':
            # Логика для успешного платежа
            print(f"Платеж по заказу {order_id} успешно завершен")
        elif status == 'Failed':
            # Логика для неуспешного платежа
            print(f"Платеж по заказу {order_id} не прошел")
        
        # Возвращаем успешный ответ
        return web.Response(status=200, text="OK")
    
    except ValueError as e:
        # Ошибка проверки подписи или формата данных
        return web.Response(status=400, text=str(e))

# Настройка сервера
app = web.Application()
app.router.add_post('/payment/webhook', webhook_handler)

# Запуск сервера
web.run_app(app, host='localhost', port=8080)
```

### Использование контекстного менеджера

```python
import asyncio
from wata import PaymentClient

async def main():
    # Инициализация клиента
    PaymentClient.initialize(
        api_key="your_api_key_here",
        base_url="https://api.payment-provider.com"
    )
    
    # Использование контекстного менеджера для автоматического закрытия клиента
    async with PaymentClient.get_instance() as client:
        # Создание тестового платежа
        payment_result = await client.payment.create(
            amount=100,
            currency="RUB",
            description="Тестовый платеж через контекстный менеджер"
        )
        
        print(f"ID платежа: {payment_result['id']}")
    
    # Соединение автоматически закрыто

asyncio.run(main())
```

## Иерархическое логирование

Библиотека поддерживает иерархическое логирование для всех компонентов:

```
wata_api.client               # Логгер основного клиента
├── wata_api.client.http      # Логгер HTTP-клиента
├── wata_api.client.payment   # Логгер модуля платежей
└── wata_api.client.webhook   # Логгер модуля вебхуков
```

Это позволяет гибко настраивать уровни логирования для разных компонентов:

```python
import logging

# Настройка логирования
logging.getLogger("wata_api.client").setLevel(logging.INFO)
logging.getLogger("wata_api.client.http").setLevel(logging.DEBUG)
logging.getLogger("wata_api.client.payment").setLevel(logging.WARNING)
```

## Обработка ошибок

Библиотека предоставляет собственный класс исключений `ApiError`:

```python
from wata.exceptions import ApiError

try:
    payment = await client.payment.create(amount=100, currency="RUB")
except ApiError as e:
    print(f"Код ошибки: {e.error_code}")
    print(f"Сообщение: {e.message}")
    print(f"HTTP-статус: {e.status_code}")
```

## Требования

- Python 3.7+
- aiohttp
- cryptography

## Лицензия

MIT