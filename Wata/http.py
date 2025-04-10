import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional

from .exceptions import ApiError, ApiTimeoutError, ApiConnectionError

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
        """
        Формирование полного URL из эндпоинта
        
        :param endpoint: Относительный путь эндпоинта
        :return: Полный URL запроса
        """
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
        :raises ApiError: При ошибках API
        :raises ApiTimeoutError: При превышении времени ожидания
        :raises ApiConnectionError: При проблемах с подключением
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
        
        GET запрос используется для получения данных без изменения состояния на сервере.
        Этот метод идемпотентный, что означает многократное выполнение одного и того же 
        запроса не должно оказывать дополнительного воздействия на сервер.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param params: Словарь с параметрами запроса, которые будут добавлены к URL как query string
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            response = await client.get("api/users", params={"limit": 10, "offset": 0})
            users = response.data
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
        
        POST запрос используется для создания новых ресурсов или отправки данных, 
        которые будут обработаны на сервере. Этот метод не является идемпотентным,
        что означает повторное выполнение того же запроса может привести к созданию
        дубликатов или другим побочным эффектам.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param data: Словарь с данными, которые будут отправлены в теле запроса как JSON
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            user_data = {"name": "Иван", "email": "ivan@example.com"}
            response = await client.post("api/users", data=user_data)
            created_user = response.data
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
    
    async def put(self, endpoint: str, data: Dict[str, Any]):
        """
        Выполнить PUT запрос
        
        PUT запрос используется для полного обновления существующего ресурса.
        Этот метод идемпотентный, что означает многократное выполнение одного и того же 
        запроса даст одинаковый результат. При использовании PUT предполагается, 
        что вы отправляете полное представление ресурса, которое заменит существующее.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param data: Словарь с данными, которые будут отправлены в теле запроса как JSON
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            updated_user = {"id": 123, "name": "Иван Петров", "email": "ivan@example.com"}
            response = await client.put("api/users/123", data=updated_user)
            result = response.data
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        self.logger.debug(f"PUT {url}")
        
        async def make_request():
            try:
                async with self._session.put(url, json=data) as response:
                    return await self._process_response(response)
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
    async def delete(self, endpoint: str, params: Optional[Dict[str, Any]] = None):
        """
        Выполнить DELETE запрос
        
        DELETE запрос используется для удаления ресурса с сервера.
        Этот метод идемпотентный, что означает повторное удаление одного и того же
        ресурса не должно вызывать ошибку (хотя второй запрос может вернуть статус 404).
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param params: Словарь с параметрами запроса, которые будут добавлены к URL как query string
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            response = await client.delete("api/users/123")
            if response.status == 204:
                print("Пользователь успешно удален")
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        self.logger.debug(f"DELETE {url}")
        
        async def make_request():
            try:
                async with self._session.delete(url, params=params) as response:
                    return await self._process_response(response)
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
    async def patch(self, endpoint: str, data: Dict[str, Any]):
        """
        Выполнить PATCH запрос
        
        PATCH запрос используется для частичного обновления существующего ресурса.
        В отличие от PUT, этот метод предназначен для применения частичных изменений.
        Таким образом, вы отправляете только те поля, которые нужно изменить, а не 
        полное представление ресурса.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param data: Словарь с данными для частичного обновления, которые будут отправлены как JSON
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            patch_data = {"name": "Иван Сидоров"}  # Обновляем только имя
            response = await client.patch("api/users/123", data=patch_data)
            updated_user = response.data
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        self.logger.debug(f"PATCH {url}")
        
        async def make_request():
            try:
                async with self._session.patch(url, json=data) as response:
                    return await self._process_response(response)
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
    async def head(self, endpoint: str, params: Optional[Dict[str, Any]] = None):
        """
        Выполнить HEAD запрос
        
        HEAD запрос идентичен GET запросу, но сервер не возвращает тело ответа.
        Этот метод используется для получения метаданных о ресурсе без загрузки
        самого ресурса. Полезно для проверки доступности ресурса, получения заголовков
        (например, Last-Modified) или определения размера файла перед скачиванием.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :param params: Словарь с параметрами запроса, которые будут добавлены к URL как query string
        :return: Объект ответа с полями data (пустой словарь), status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            response = await client.head("api/files/report.pdf")
            content_length = int(response.headers.get("Content-Length", 0))
            print(f"Размер файла: {content_length} байт")
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        self.logger.debug(f"HEAD {url}")
        
        async def make_request():
            try:
                async with self._session.head(url, params=params) as response:
                    # HEAD не имеет тела ответа, поэтому мы не можем вызвать _process_response
                    if response.status >= 400:
                        error_message = f"Ошибка {response.status}"
                        self.logger.error(f"API вернул ошибку: {error_message}")
                        raise ApiError(response.status, error_message, {})
                    
                    # Создаем объект ответа только с заголовками
                    class Response:
                        def __init__(self, status=None, headers=None):
                            self.data = {}  # Пустые данные для HEAD запроса
                            self.status = status
                            self.headers = headers
                    
                    return Response(response.status, dict(response.headers))
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)
    
    async def options(self, endpoint: str):
        """
        Выполнить OPTIONS запрос
        
        OPTIONS запрос используется для определения возможностей сервера или параметров
        коммуникации для конкретного ресурса. Этот метод возвращает заголовки, которые
        описывают доступные варианты взаимодействия с ресурсом. 
        Часто используется для предварительных проверок CORS (Cross-Origin Resource Sharing)
        или для получения информации о поддерживаемых HTTP-методах.
        
        :param endpoint: API эндпоинт, относительный путь от базового URL
        :return: Объект ответа с полями data, status и headers
        :raises ApiError: При ошибках API (статус != 2xx)
        :raises ApiTimeoutError: При превышении времени ожидания запроса
        :raises ApiConnectionError: При проблемах с подключением к API
        
        Пример использования:
            response = await client.options("api/users")
            allowed_methods = response.headers.get("Allow", "")
            cors_methods = response.headers.get("Access-Control-Allow-Methods", "")
            print(f"Разрешенные методы: {allowed_methods}")
            print(f"Методы CORS: {cors_methods}")
        """
        await self._ensure_session()
        url = self._build_url(endpoint)
        
        self.logger.debug(f"OPTIONS {url}")
        
        async def make_request():
            try:
                async with self._session.options(url) as response:
                    if response.status >= 400:
                        error_message = f"Ошибка {response.status}"
                        self.logger.error(f"API вернул ошибку: {error_message}")
                        raise ApiError(response.status, error_message, {})
                    
                    # Пытаемся прочитать тело ответа как JSON, но для OPTIONS это не обязательно
                    try:
                        data = await response.json()
                    except ValueError:
                        # Если ответ не JSON или пустой, создаем пустой словарь
                        data = {}
                    
                    class Response:
                        def __init__(self, data, status=None, headers=None):
                            self.data = data
                            self.status = status
                            self.headers = headers
                    
                    return Response(data, response.status, dict(response.headers))
            except aiohttp.ClientResponseError as e:
                raise ApiError(e.status, str(e))
            except asyncio.TimeoutError:
                raise ApiTimeoutError()
            except aiohttp.ClientError as e:
                raise ApiConnectionError(str(e))
        
        return await self._execute_with_retry(make_request)