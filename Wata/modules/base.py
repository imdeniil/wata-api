import logging
from typing import Optional

from ..http import AsyncHttpClient

class BaseApiModule:
    """Базовый класс для всех модулей API"""
    
    def __init__(self, http_client: AsyncHttpClient, logger=None):
        self._http_client = http_client
        self.logger = logger or logging.getLogger(self.__class__.__name__)