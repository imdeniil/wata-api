# ./ http_client.py

"""
HTTP-клиент для выполнения асинхронных запросов к API.
"""

import aiohttp
import json
import logging
from .exceptions import ApiError
from .logger import BaseComponent

class HttpClient(BaseComponent):
    """
    Асинхронный HTTP-клиент для работы с API.
    """
    
    def __init__(self, api_key, base_url, timeout=30, 
                component_name="http", parent_logger_name=None, 
                base_logger_name=None, log_level=None, **kwargs):
        """
        Инициализация HTTP-клиента.
        
        :param api_key: Ключ API для авторизации
        :param base_url: Базовый URL API
        :param timeout: Таймаут запросов в секундах
        :param component_name: Имя компонента для логгера
        :param parent_logger_name: Имя родительского логгера
        :param base_logger_name: Базовое имя логгера
        :param log_level: Уровень логирования
        :param kwargs: Дополнительные параметры для сессии
        """
        # Инициализация базового компонента для настройки логгера
        super().__init__(
            component_name=component_name,
            parent_logger_name=parent_logger_name,
            base_logger_name=base_logger_name,  # Просто передаем параметр дальше
            log_level=log_level
        )
        
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session = None
        self.session_params = kwargs
        
        self.logger.debug(f"Инициализирован HTTP-клиент для {self.base_url}")
    
    async def _ensure_session(self):
        """
        Убедиться, что сессия создана.
        """
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout, **self.session_params)
            self.logger.debug("Создана новая HTTP-сессия")
    
    async def request(self, method, endpoint, data=None, params=None, headers=None):
        """
        Выполнение HTTP-запроса к API.
        
        :param method: HTTP-метод (GET, POST, PUT, DELETE и т.д.)
        :param endpoint: Конечная точка API
        :param data: Данные для отправки в теле запроса
        :param params: Параметры строки запроса
        :param headers: Дополнительные заголовки
        :return: Результат запроса в виде JSON
        :raises ApiError: В случае ошибки API или HTTP-клиента
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Подготовка заголовков с авторизацией
        request_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        if headers:
            request_headers.update(headers)
        
        self.logger.debug(f"Выполняется запрос {method} {url}")
        
        try:
            async with self.session.request(
                method, 
                url, 
                json=data, 
                params=params, 
                headers=request_headers
            ) as response:
                content = await response.text()
                
                try:
                    response_data = json.loads(content) if content else {}
                except json.JSONDecodeError:
                    response_data = {"content": content}
                
                if response.status >= 400:
                    # Извлечение информации о коде ошибки, если она доступна
                    error_code = None
                    error_message = f"API вернул ошибку: {response.status}"
                    
                    if 'error' in response_data and 'code' in response_data['error']:
                        error_code = response_data['error']['code']
                    
                    if 'error' in response_data and 'message' in response_data['error']:
                        error_message = response_data['error']['message']
                    
                    self.logger.error(f"Ошибка API: {response.status} | {error_code or 'Без кода'} | {error_message}")
                    
                    # Детальное логирование ошибок валидации
                    if 'error' in response_data and 'validationErrors' in response_data['error']:
                        for error in response_data['error']['validationErrors']:
                            members = ", ".join(error.get('members', []))
                            message = error.get('message', 'Ошибка валидации')
                            self.logger.error(f"Ошибка валидации: {message} (поля: {members})")
                    
                    raise ApiError(
                        status_code=response.status,
                        message=error_message,
                        response_data=response_data,
                        error_code=error_code,
                        logger=self.logger  # Передаем логгер в исключение
                    )
                
                self.logger.debug(f"Успешный ответ: {response.status}")
                return response_data
        
        except aiohttp.ClientError as e:
            self.logger.error(f"Ошибка HTTP-клиента: {str(e)}")
            raise ApiError(
                status_code=0,
                message=f"Ошибка HTTP-клиента: {str(e)}",
                response_data=None,
                logger=self.logger  # Передаем логгер в исключение
            )
    
    async def get(self, endpoint, params=None, headers=None):
        """
        Выполнение GET-запроса.
        """
        return await self.request("GET", endpoint, params=params, headers=headers)
    
    async def post(self, endpoint, data=None, params=None, headers=None):
        """
        Выполнение POST-запроса.
        """
        return await self.request("POST", endpoint, data=data, params=params, headers=headers)
    
    async def put(self, endpoint, data=None, params=None, headers=None):
        """
        Выполнение PUT-запроса.
        """
        return await self.request("PUT", endpoint, data=data, params=params, headers=headers)
    
    async def delete(self, endpoint, data=None, params=None, headers=None):
        """
        Выполнение DELETE-запроса.
        """
        return await self.request("DELETE", endpoint, data=data, params=params, headers=headers)
    
    async def close(self):
        """
        Закрытие сессии и освобождение ресурсов.
        """
        if self.session is not None:
            await self.session.close()
            self.session = None
            self.logger.debug("HTTP-сессия закрыта")