"""
Модуль для работы с вебхуками платежного API.
"""
import base64
import json
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from ..logger import BaseComponent

class WebhookModule(BaseComponent):
    """
    Модуль для работы с вебхуками платежного API.
    """
    def __init__(self, http_client, component_name="webhook", parent_logger_name=None, 
                 base_logger_name="wata_api", log_level=logging.INFO):
        """
        Инициализация модуля вебхуков.
       
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
        self._public_key = None
        
    async def get_public_key(self, force_refresh=False):
        """
        Получение публичного ключа для проверки подписи вебхуков.
    
        :param force_refresh: Принудительное обновление ключа из API
        :return: Публичный ключ в формате PEM
        """
        if self._public_key is None or force_refresh:
            self.logger.debug("Запрос публичного ключа для проверки вебхуков")
            response = await self._http_client.get("api/h2h/public-key")
        
            if isinstance(response, dict) and 'value' in response:
                # Сохраняем именно строку с ключом, а не весь словарь
                self._public_key = response['value']
                self.logger.debug("Публичный ключ для проверки вебхуков получен")
            else:
                self.logger.error("Ошибка при получении публичного ключа: ответ не содержит поле 'value'")
                raise ValueError("Ответ API не содержит публичный ключ")
            
        return self._public_key
        
    async def verify_signature(self, signature, data):
        """
        Проверка подписи вебхука.
       
        :param signature: Подпись из заголовка X-Signature
        :param data: Данные вебхука (JSON в виде строки)
        :return: True, если подпись верна, False в противном случае
        """
        try:
            # Получение публичного ключа
            public_key_pem = await self.get_public_key()
           
            # Преобразование PEM строки в объект публичного ключа
            public_key = load_pem_public_key(public_key_pem.encode('utf-8'))
           
            # Декодирование подписи из base64
            decoded_signature = base64.b64decode(signature)
           
            # Проверка подписи
            public_key.verify(
                decoded_signature,
                data.encode('utf-8'),
                padding.PKCS1v15(),
                hashes.SHA512()
            )
           
            self.logger.debug("Подпись вебхука проверена успешно")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при проверке подписи вебхука: {str(e)}")
            return False
            
    async def process_webhook(self, signature, data):
        """
        Обработка вебхука с проверкой подписи.
    
        :param signature: Подпись из заголовка X-Signature
        :param data: Данные вебхука (JSON в виде строки)
        :return: Обработанные данные вебхука или None, если подпись неверна
        :raises ValueError: Если подпись недействительна
        """
        # Проверяем подпись
        if not await self.verify_signature(signature, data):
            self.logger.warning("Получен вебхук с недействительной подписью")
            raise ValueError("Недействительная подпись вебхука")
    
        # Если подпись верна, обрабатываем данные
        webhook_data = json.loads(data)
    
        # Минимальная информация для info-уровня - только самое необходимое
        self.logger.info(
            f"Получен вебхук: "
            f"orderId={webhook_data.get('orderId')}, "
            f"transactionId={webhook_data.get('transactionId')}, "
            f"status={webhook_data.get('transactionStatus')}"
        )
        
        # Полная информация для debug-уровня
        self.logger.debug(
            f"Детали вебхука {webhook_data.get('transactionId')}: "
            f"transactionType={webhook_data.get('transactionType')}, "
            f"errorCode={webhook_data.get('errorCode')}, "
            f"errorDescription={webhook_data.get('errorDescription')}, "
            f"terminalName={webhook_data.get('terminalName')}, "
            f"amount={webhook_data.get('amount')} {webhook_data.get('currency')}, "
            f"orderDescription={webhook_data.get('orderDescription')}, "
            f"paymentTime={webhook_data.get('paymentTime')}, "
            f"commission={webhook_data.get('commission')}, "
            f"email={webhook_data.get('email')}"
        )
        
        # Отдельное логирование при наличии ошибок (для любого уровня логирования)
        if webhook_data.get('errorCode') or webhook_data.get('errorDescription'):
            self.logger.warning(
                f"Ошибка в транзакции {webhook_data.get('transactionId')}: "
                f"код={webhook_data.get('errorCode')}, "
                f"описание={webhook_data.get('errorDescription')}"
            )
    
        # Возвращаем данные вебхука
        return webhook_data