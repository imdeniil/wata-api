
from .base import BaseApiModule

class SteamModule(BaseApiModule):
    """Модуль для работы с вебхуками"""

    def __init__(self, http_client, logger=None):
        super().__init__(http_client, logger)
        self._http_client._base_url = "https://acquiring.foreignpay.ru"