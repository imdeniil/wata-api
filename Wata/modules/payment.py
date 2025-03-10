"""
Модуль для работы с платежами.
"""

import decimal
from datetime import datetime
from typing import Optional, Dict, Any, Union, List
import logging

from ..exceptions import ApiError
from ..logger import BaseComponent

class PaymentModule(BaseComponent):
    """
    Модуль для работы с платежами.
    """
    
    def __init__(self, http_client, component_name="payment", parent_logger_name=None, 
                 base_logger_name="wata_api", log_level=logging.INFO):
        """
        Инициализация модуля.
        
        :param http_client: HTTP-клиент для выполнения запросов
        :param component_name: Имя компонента
        :param parent_logger_name: Имя родительского логгера
        :param base_logger_name: Базовое имя логгера (используется только если parent_logger_name не указан)
        :param log_level: Уровень логирования
        """
        # Инициализация базового компонента для настройки логгера
        super().__init__(
            component_name=component_name,
            parent_logger_name=parent_logger_name,
            base_logger_name=base_logger_name,
            log_level=log_level
        )
        
        self._http_client = http_client
    
    async def create(
        self,
        amount: Union[decimal.Decimal, float, int],
        currency: str,
        description: Optional[str] = None,
        order_id: Optional[str] = None,
        success_redirect_url: Optional[str] = None,
        fail_redirect_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Создание платежа.
        
        :param amount: Сумма платежа (обязательный параметр)
        :param currency: Валюта платежа (RUB, EUR, USD) (обязательный параметр)
        :param description: Описание заказа
        :param order_id: Идентификатор заказа в системе мерчанта
        :param success_redirect_url: URL для редиректа при успешной оплате
        :param fail_redirect_url: URL для редиректа при неуспешной оплате
        :return: Информация о созданном платеже
        :raises ApiError: Если произошла ошибка при создании платежа
        """
        self.logger.info(f"Создание нового платежа на сумму {amount} {currency}")
        
        # Преобразуем amount в строку с 2 знаками после запятой
        if isinstance(amount, (int, float)):
            amount = decimal.Decimal(str(amount))
        
        # Округляем до 2 знаков после запятой
        amount = amount.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
        
        # Формируем данные запроса
        data = {
            "amount": float(amount),  # API ожидает число, не строку
            "currency": currency
        }
        
        # Добавляем необязательные параметры, если они указаны
        if description:
            data["description"] = description
        
        if order_id:
            data["orderId"] = order_id
        
        if success_redirect_url:
            data["successRedirectUrl"] = success_redirect_url
        
        if fail_redirect_url:
            data["failRedirectUrl"] = fail_redirect_url
        
        try:
            # Отправляем запрос на создание платежа
            result = await self._http_client.post("api/h2h/links", data=data)
            self.logger.info(f"Платеж успешно создан")
            return result
        except ApiError as e:
            # Обработка специфических ошибок платежей
            if e.error_code == "Payment:PL_1001":
                self.logger.error(f"Ошибка создания платежа: некорректная сумма {amount}")
            elif e.error_code == "Payment:PL_1002":
                self.logger.error(f"Ошибка создания платежа: неподдерживаемая валюта {currency}")
            else:
                self.logger.error(f"Ошибка создания платежа: {e}")
            
            # Пробрасываем исключение дальше
            raise
    
    async def get_link_by_uuid(self, uuid: str) -> Dict[str, Any]:
        """
        Получение платежной ссылки по UUID.
        
        :param uuid: Идентификатор платежной ссылки (UUID)
        :return: Информация о платежной ссылке
        :raises ApiError: Если произошла ошибка при получении платежной ссылки
        """
        self.logger.info(f"Получение платежной ссылки по UUID: {uuid}")
        
        try:
            result = await self._http_client.get(f"api/h2h/links/{uuid}")
            self.logger.debug(f"Успешно получена информация о платежной ссылке {uuid}")
            return result
        except ApiError as e:
            if e.error_code == "Payment:PL_1003":
                self.logger.error(f"Платежная ссылка {uuid} недоступна или уже оплачена")
            else:
                self.logger.error(f"Ошибка получения платежной ссылки {uuid}: {e}")
            raise

    async def search_links(
        self,
        amount_from: Optional[Union[decimal.Decimal, float, int]] = None,
        amount_to: Optional[Union[decimal.Decimal, float, int]] = None,
        creation_time_from: Optional[Union[datetime, str]] = None,
        creation_time_to: Optional[Union[datetime, str]] = None,
        order_id: Optional[str] = None,
        currencies: Optional[Union[str, List[str]]] = None,
        statuses: Optional[Union[str, List[str]]] = None,
        sorting: Optional[str] = None,
        skip_count: Optional[int] = None,
        max_result_count: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Поиск платежных ссылок с фильтрацией.
        
        :param amount_from: Минимальная сумма платежа
        :param amount_to: Максимальная сумма платежа
        :param creation_time_from: Дата создания от (datetime или строка в формате ISO)
        :param creation_time_to: Дата создания до (datetime или строка в формате ISO)
        :param order_id: Идентификатор заказа в системе мерчанта
        :param currencies: Валюта или список валют (RUB, EUR, USD)
        :param statuses: Статус или список статусов платежной ссылки (Opened, Closed)
        :param sorting: Поле для сортировки (orderId, creationTime, amount)
                    с опциональным суффиксом 'desc' для сортировки по убыванию
        :param skip_count: Количество записей, которые нужно пропустить (по умолчанию 0)
        :param max_result_count: Количество записей в ответе (по умолчанию 10, максимум 1000)
        :return: Список платежных ссылок и метаданные
        :raises ApiError: Если произошла ошибка при поиске платежных ссылок
        """
        self.logger.info("Выполняется поиск платежных ссылок")
        
        # Подготовка параметров запроса
        params = {}
        
        # Обработка числовых параметров
        if amount_from is not None:
            if isinstance(amount_from, (int, float)):
                amount_from = decimal.Decimal(str(amount_from))
            amount_from = amount_from.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
            params["amountFrom"] = float(amount_from)
        
        if amount_to is not None:
            if isinstance(amount_to, (int, float)):
                amount_to = decimal.Decimal(str(amount_to))
            amount_to = amount_to.quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_HALF_UP)
            params["amountTo"] = float(amount_to)
        
        # Обработка параметров даты
        if creation_time_from is not None:
            if isinstance(creation_time_from, datetime):
                creation_time_from = creation_time_from.isoformat()
            params["creationTimeFrom"] = creation_time_from
        
        if creation_time_to is not None:
            if isinstance(creation_time_to, datetime):
                creation_time_to = creation_time_to.isoformat()
            params["creationTimeTo"] = creation_time_to
        
        # Обработка параметра идентификатора заказа
        if order_id is not None:
            params["orderId"] = order_id
        
        # Обработка параметров валюты
        if currencies is not None:
            if isinstance(currencies, list):
                currencies = ",".join(currencies)
            params["currencies"] = currencies
        
        # Обработка параметров статусов
        if statuses is not None:
            if isinstance(statuses, list):
                statuses = ",".join(statuses)
            params["statuses"] = statuses
        
        # Обработка параметра сортировки
        if sorting is not None:
            params["sorting"] = sorting
        
        # Обработка параметров пагинации
        if skip_count is not None:
            params["skipCount"] = skip_count
        
        if max_result_count is not None:
            params["maxResultCount"] = max_result_count
        
        self.logger.debug(f"Параметры поиска: {params}")
        
        try:
            # Выполняем запрос на поиск платежных ссылок
            result = await self._http_client.get("api/h2h/links/", params=params)
            
            # Логирование результатов
            if "items" in result:
                self.logger.info(f"Найдено {len(result['items'])} платежных ссылок")
            else:
                self.logger.warning("API вернул ответ без элемента 'items'")
            
            return result
        except ApiError as e:
            self.logger.error(f"Ошибка при поиске платежных ссылок: {e}")
            raise