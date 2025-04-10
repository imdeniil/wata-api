class ApiError(Exception):
    """Базовое исключение для всех ошибок API"""
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
    
    @property
    def is_server_error(self):
        """Является ли ошибка серверной (5xx)"""
        return 500 <= self.status_code < 600
    
    @property
    def is_client_error(self):
        """Является ли ошибка клиентской (4xx)"""
        return 400 <= self.status_code < 500
    
    @property
    def is_retryable(self):
        """Можно ли повторить запрос при данной ошибке"""
        # Обычно временные ошибки: 408, 429, 500, 502, 503, 504
        retryable_codes = {408, 429, 500, 502, 503, 504}
        return self.status_code in retryable_codes


# Ошибки соединения и таймаута

class ApiTimeoutError(ApiError):
    """Исключение при превышении времени ожидания запроса"""
    def __init__(self, message="Превышено время ожидания ответа от API"):
        super().__init__(408, message)


class ApiConnectionError(ApiError):
    """Исключение при проблемах с подключением к API"""
    def __init__(self, message="Ошибка подключения к API"):
        super().__init__(0, message)


# Ошибки авторизации и доступа

class ApiAuthError(ApiError):
    """Ошибка авторизации (401 Unauthorized)"""
    def __init__(self, message="Ошибка авторизации", response_data=None):
        super().__init__(401, message, response_data)


class ApiForbiddenError(ApiError):
    """Ошибка доступа (403 Forbidden)"""
    def __init__(self, message="Доступ запрещен", response_data=None):
        super().__init__(403, message, response_data)


# Ошибки валидации и запроса

class ApiValidationError(ApiError):
    """Ошибка валидации данных (400 Bad Request или 422 Unprocessable Entity)"""
    def __init__(self, status_code=400, message="Ошибка валидации данных", response_data=None):
        super().__init__(status_code, message, response_data)
        
        # Извлекаем поля с ошибками, если они есть в ответе
        self.field_errors = {}
        
        if isinstance(response_data, dict):
            # Проверяем разные форматы ошибок валидации
            if 'errors' in response_data and isinstance(response_data['errors'], dict):
                self.field_errors = response_data['errors']
            elif 'fields' in response_data and isinstance(response_data['fields'], dict):
                self.field_errors = response_data['fields']
            elif 'validationErrors' in response_data and isinstance(response_data['validationErrors'], list):
                # Преобразуем список ошибок в словарь поле -> ошибки
                for error in response_data['validationErrors']:
                    if 'field' in error and 'message' in error:
                        field = error['field']
                        if field not in self.field_errors:
                            self.field_errors[field] = []
                        self.field_errors[field].append(error['message'])


class ApiRateLimitError(ApiError):
    """Превышен лимит запросов (429 Too Many Requests)"""
    def __init__(self, message="Превышен лимит запросов", response_data=None):
        super().__init__(429, message, response_data)
        
        # Извлекаем информацию о времени до сброса ограничений
        self.retry_after = None
        
        if isinstance(response_data, dict) and 'retryAfter' in response_data:
            self.retry_after = response_data['retryAfter']
        elif response_data and hasattr(response_data, 'headers') and 'Retry-After' in response_data.headers:
            self.retry_after = response_data.headers['Retry-After']


# Ошибки ресурсов

class ApiResourceNotFoundError(ApiError):
    """Ресурс не найден (404 Not Found)"""
    def __init__(self, message="Ресурс не найден", response_data=None):
        super().__init__(404, message, response_data)


class ApiResourceGoneError(ApiError):
    """Ресурс больше не существует (410 Gone)"""
    def __init__(self, message="Ресурс больше не существует", response_data=None):
        super().__init__(410, message, response_data)


# Серверные ошибки

class ApiServerError(ApiError):
    """Внутренняя ошибка сервера (500 Internal Server Error)"""
    def __init__(self, message="Внутренняя ошибка сервера", response_data=None):
        super().__init__(500, message, response_data)


class ApiServiceUnavailableError(ApiError):
    """Сервис временно недоступен (503 Service Unavailable)"""
    def __init__(self, message="Сервис временно недоступен", response_data=None):
        super().__init__(503, message, response_data)


class ApiGatewayError(ApiError):
    """Ошибка шлюза (502 Bad Gateway или 504 Gateway Timeout)"""
    def __init__(self, status_code=502, message="Ошибка шлюза", response_data=None):
        super().__init__(status_code, message, response_data)


# Ошибки парсинга и контента

class ApiParsingError(ApiError):
    """Ошибка при парсинге ответа API"""
    def __init__(self, message="Ошибка при парсинге ответа API", original_exception=None):
        super().__init__(0, message)
        self.original_exception = original_exception


class ApiContentTypeError(ApiError):
    """Ошибка при получении ответа с неожиданным типом контента"""
    def __init__(self, content_type, expected_type, message=None):
        self.content_type = content_type
        self.expected_type = expected_type
        
        if not message:
            message = f"Получен неожиданный тип контента: {content_type}, ожидался: {expected_type}"
            
        super().__init__(0, message)


# Фабрика исключений для создания правильного типа по коду статуса

def create_api_error(status_code, message, response_data=None):
    """
    Создает соответствующий экземпляр исключения на основе кода статуса HTTP
    
    :param status_code: Код статуса HTTP
    :param message: Сообщение об ошибке
    :param response_data: Данные ответа (если есть)
    :return: Экземпляр соответствующего класса исключения
    """
    # Ошибки авторизации
    if status_code == 401:
        return ApiAuthError(message, response_data)
    elif status_code == 403:
        return ApiForbiddenError(message, response_data)
    
    # Ошибки валидации и запроса
    elif status_code == 400:
        return ApiValidationError(status_code, message, response_data)
    elif status_code == 422:
        return ApiValidationError(status_code, message, response_data)
    elif status_code == 429:
        return ApiRateLimitError(message, response_data)
    
    # Ошибки ресурсов
    elif status_code == 404:
        return ApiResourceNotFoundError(message, response_data)
    elif status_code == 410:
        return ApiResourceGoneError(message, response_data)
    
    # Серверные ошибки
    elif status_code == 500:
        return ApiServerError(message, response_data)
    elif status_code == 503:
        return ApiServiceUnavailableError(message, response_data)
    elif status_code in (502, 504):
        return ApiGatewayError(status_code, message, response_data)
    elif status_code == 408:
        return ApiTimeoutError(message)
    
    # Общая ошибка API для других кодов статуса
    else:
        return ApiError(status_code, message, response_data)