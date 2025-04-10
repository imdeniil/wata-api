
class ApiError(Exception):
    """Исключение, связанное с ошибками API"""
    def __init__(self, status_code, message, response_data=None):
        self.status_code = status_code
        self.message = message
        self.response_data = response_data
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