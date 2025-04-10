import asyncio
import aiohttp
import decimal
import logging
import json
import base64
from datetime import datetime
from typing import Dict, Any, Optional, Union, List

class ApiError(Exception):
    """Исключение, связанное с ошибками API"""
    def __init__(self, status_code, message, response_data=None):
        self.status_code = status_code
        self.message = message
        self.response_data = response_data
        # Избегаем повторения кода статуса в сообщении
        if message.startswith(f"HTTP {status_code}"):
            error_text = message
        else:
            error_text = f"{message}"
        super().__init__(f"API Error {status_code}: {error_text}")


class ApiTimeoutError(ApiError):
    """Исключение при превышении времени ожидания запроса"""
    def __init__(self, message="Превышено время ожидания ответа от API"):
        super().__init__(408, message)


class ApiConnectionError(ApiError):
    """Исключение при проблемах с подключением к API"""
    def __init__(self, message="Ошибка подключения к API"):
        super().__init__(0, message)


class AsyncHttpClient:
    """HTTP клиент с использованием aiohttp и JWT аутентификацией"""
    
    def __init__(self, 
                 base_url: str, 
                 jwt_token: str, 
                 timeout: int = 30,
                 max_retries: int = 3,
                 retry_delay: float = 0.5,
                 logger: Optional[logging.Logger] = None):
        """
        Инициализация HTTP клиента
        
        :param base_url: Базовый URL API
        :param jwt_token: JWT токен для аутентификации
        :param timeout: Таймаут для запросов в секундах
        :param max_retries: Максимальное количество повторных попыток при ошибках
        :param retry_delay: Задержка между повторными попытками в секундах
        :param logger: Логгер (опционально)
        """
        self._base_url = base_url
        self._jwt_token = jwt_token
        self._timeout = aiohttp.ClientTimeout(
            total=timeout,
            connect=min(10, timeout / 3),  # Таймаут на установку соединения
            sock_connect=min(10, timeout / 3),  # Таймаут на установку соединения на уровне сокета
            sock_read=timeout  # Таймаут на чтение данных
        )
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._session = None
        self._lock = None  # Будет инициализирован при первом вызове _ensure_session
    
    async def _ensure_session(self):
        """Обеспечивает создание сессии, если она еще не создана"""
        # Инициализируем лок при первом вызове
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()
        
        # Используем лок для предотвращения race conditions при создании сессии
        async with self._lock:
            if self._session is None or self._session.closed:
                self.logger.debug("Создание новой aiohttp сессии")
                
                # Дополнительные заголовки для всех запросов
                headers = {
                    "Authorization": f"Bearer {self._jwt_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Python-AsyncHttpClient/1.0"
                }
                
                # Настройка трассировки для отладки на уровне DEBUG
                trace_config = aiohttp.TraceConfig()
                
                # Логирование только на DEBUG уровне
                async def on_request_start(session, trace_config_ctx, params):
                    self.logger.debug(f"Запрос: {params.method} {params.url}")
                
                async def on_request_end(session, trace_config_ctx, params):
                    self.logger.debug(f"Ответ: {params.method} {params.url} - {params.response.status}")
                
                trace_config.on_request_start.append(on_request_start)
                trace_config.on_request_end.append(on_request_end)
                
                self._session = aiohttp.ClientSession(
                    timeout=self._timeout,
                    headers=headers,
                    trace_configs=[trace_config],
                    raise_for_status=False  # Будем обрабатывать статусы вручную
                )
    
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            self.logger.debug("Закрытие aiohttp сессии")
            await self._session.close()
            self._session = None
    
    def _build_url(self, endpoint: str) -> str:
        """Формирование полного URL из эндпоинта"""
        # Убираем ведущий слеш из эндпоинта, если он есть
        if endpoint.startswith('/'):
            endpoint = endpoint[1:]
        
        # Убираем завершающий слеш из base_url, если он есть
        base_url = self._base_url
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        
        return f"{base_url}/{endpoint}"
    
    async def _process_response(self, response):
        """
        Обработка ответа от API
        
        :param response: Объект ответа aiohttp
        :return: Обработанный объект ответа
        :raises ApiError: Если произошла ошибка API
        """
        try:
            # Проверяем статус ответа
            if 200 <= response.status < 300:
                # Пытаемся прочитать тело ответа как JSON
                try:
                    data = await response.json()
                except ValueError:
                    # Если ответ не JSON, читаем как текст
                    data = await response.text()
                    self.logger.warning(f"Ответ не в формате JSON: {data[:100]}...")
            else:
                # Пытаемся получить детали ошибки
                try:
                    error_data = await response.json()
                except ValueError:
                    error_data = await response.text()
                
                # Формируем сообщение об ошибке без повторения кода статуса
                if isinstance(error_data, dict) and 'message' in error_data:
                    error_message = error_data.get('message')
                else:
                    error_message = f"Ошибка {response.status}"
                    
                self.logger.error(f"API вернул ошибку: {error_message}")
                raise ApiError(response.status, error_message, error_data)
            
            # Создаем объект ответа с атрибутом data
            class Response:
                def __init__(self, data, status=None, headers=None):
                    self.data = data
                    self.status = status
                    self.headers = headers
            
            return Response(data, response.status, dict(response.headers))
            
        except ApiError:
            # Пробрасываем ApiError дальше
            raise
        except Exception as e:
            # Оборачиваем все другие исключения
            self.logger.error(f"Ошибка при обработке ответа: {str(e)}")
            import traceback
            self.logger.debug(f"Стек вызовов: {traceback.format_exc()}")
            raise ApiError(0, f"Ошибка при обработке ответа: {str(e)}")
    
    async def _execute_with_retry(self, request_func):
        """
        Выполнение запроса с механизмом повторных попыток
        
        :param request_func: Асинхронная функция, выполняющая запрос
        :return: Результат запроса
        """
        last_exception = None
        retry_log_level = logging.DEBUG  # Для промежуточных попыток используем DEBUG уровень
        
        for attempt in range(1, self._max_retries + 1):
            try:
                return await request_func()
            except (aiohttp.ClientError, ApiConnectionError, ApiTimeoutError) as e:
                last_exception = e
                
                if attempt < self._max_retries:
                    # Экспоненциальная задержка между попытками
                    delay = self._retry_delay * (2 ** (attempt - 1))
                    
                    # Для первой попытки логируем на уровне WARNING, для остальных - на DEBUG
                    if attempt == 1:
                        self.logger.warning(f"Не удалось выполнить запрос: {str(e)}. Повторная попытка через {delay:.2f} сек...")
                    else:
                        self.logger.log(retry_log_level, f"Попытка {attempt} не удалась. Повторная попытка через {delay:.2f} сек...")
                    
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    # Последняя попытка всегда логируется на уровне ERROR
                    if attempt > 1:  # Только если были повторные попытки
                        self.logger.error(f"Все {self._max_retries} попыток выполнить запрос не удались")
            except ApiError:
                # Ошибки API пробрасываем напрямую без дополнительного логирования
                # так как они уже залогированы в _process_response
                raise
            except Exception as e:
                # Не повторяем попытки для других ошибок
                self.logger.error(f"Критическая ошибка при выполнении запроса: {str(e)}")
                import traceback
                self.logger.debug(f"Стек вызовов: {traceback.format_exc()}")
                raise
        
        # Если все попытки не удались, выбрасываем последнее исключение
        if isinstance(last_exception, aiohttp.ClientConnectorError):
            raise ApiConnectionError(f"Не удалось подключиться к API после {self._max_retries} попыток")
        elif isinstance(last_exception, asyncio.TimeoutError):
            raise ApiTimeoutError(f"Превышено время ожидания после {self._max_retries} попыток")
        else:
            # Другие ошибки aiohttp.ClientError
            raise ApiError(0, f"Ошибка клиента после {self._max_retries} попыток")
    
    async def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None):
        """
        Выполнить GET запрос
        
        :param endpoint: API эндпоинт
        :param params: Параметры запроса
        :return: Объект ответа с данными
        :raises ApiError: При ошибках API
        :raises ApiTimeoutError: При превышении времени ожидания
        :raises ApiConnectionError: При проблемах с подключением
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        # Логируем запрос только на уровне DEBUG
        self.logger.debug(f"GET {url}")
        
        async def make_request():
            try:
                async with self._session.get(url, params=params) as response:
                    return await self._process_response(response)
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                # Общие ошибки клиента aiohttp
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
    async def post(self, endpoint: str, data: Dict[str, Any]):
        """
        Выполнить POST запрос
        
        :param endpoint: API эндпоинт
        :param data: Данные запроса
        :return: Объект ответа с данными
        :raises ApiError: При ошибках API
        :raises ApiTimeoutError: При превышении времени ожидания
        :raises ApiConnectionError: При проблемах с подключением
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        # Логируем запрос только на уровне DEBUG
        self.logger.debug(f"POST {url}")
        
        async def make_request():
            try:
                async with self._session.post(url, json=data) as response:
                    return await self._process_response(response)
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                # Общие ошибки клиента aiohttp
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
class BaseApiModule:
    """Базовый класс для всех модулей API"""
    
    def __init__(self, http_client: AsyncHttpClient, logger=None):
        self._http_client = http_client
        self.logger = logger or logging.getLogger(self.__class__.__name__)

class ExampleModule(BaseApiModule):
    """Модуль для работы с платежами"""
    
    def __init__(self, http_client: AsyncHttpClient, logger=None):
        super().__init__(http_client, logger)

    async def example_method(
        self,
        amount: Union[decimal.Decimal, float, int],
        currency: str,
    ) -> Dict[str, Any]:
        
        # Формируем данные запроса
        data = {
            "amount": float(amount),  # API ожидает число, не строку
            "currency": currency
        }
        
        result = await self._http_client.post("api/h2h/links", data=data)
        return result.data

class Client:
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
        self.payments = ExampleModule(self._http, logger=logger)
    
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