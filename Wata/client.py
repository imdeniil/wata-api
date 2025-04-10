import logging
from typing import Optional

from .http import AsyncHttpClient
from .exceptions import ApiError
from .modules.payments import PaymentsModule
from .modules.webhooks import WebhookModule

class PaymentClient:
    """Основной API клиент с вложенной структурой"""
    
    def __init__(self, 
                base_url: str,
                jwt_token: str,
                timeout: int = 30,
                max_retries: int = 3,
                retry_delay: float = 0.5,
                logger: Optional[logging.Logger] = None):
        """
        Инициализация API клиента
        
        :param base_url: Базовый URL API
        :param jwt_token: JWT токен для авторизации
        :param timeout: Таймаут для запросов в секундах
        :param max_retries: Максимальное количество повторных попыток при ошибках
        :param retry_delay: Задержка между повторными попытками в секундах
        :param logger: Логгер (опционально)
        """
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        
        # Инициализация HTTP клиента
        self._http = AsyncHttpClient(
            base_url=base_url,
            jwt_token=jwt_token,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay,
            logger=logger
        )
        
        # Инициализация модулей API
        self.payments = PaymentsModule(self._http, logger=logger)
        self.webhook = WebhookModule(self._http, logger=logger)
    
    async def __aenter__(self):
        """Вход в контекстный менеджер"""
        await self._http._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        await self._http.close()
        
        # Логируем только неизвестные ошибки, но не ApiError, которые уже логируются
        if exc_type is not None and not issubclass(exc_type, ApiError):
            self.logger.error(f"Ошибка при использовании API клиента: {exc_type.__name__}: {str(exc_val)}")
        
        # Не подавляем исключения
        return False
    
    async def close(self):
        """Закрыть соединение клиента"""
        await self._http.close()
        
    @property
    def is_connected(self):
        """Проверка активности соединения"""
        return self._http._session is not None and not self._http._session.closed