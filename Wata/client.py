"""
Основной клиент для работы с платежным API.
"""
from .http_client import HttpClient
from .modules.payment import PaymentModule
from .modules.webhook import WebhookModule
from .logger import BaseComponent
import logging

class AutoSingletonMeta(type):
    """
    Метакласс для автоматического получения или создания экземпляра при вызове методов.
    """
    def __getattr__(cls, name):
        """
        Вызывается, когда атрибут не найден в классе.
        Пытается найти атрибут в экземпляре.
        """
        # Получаем или создаем экземпляр
        try:
            instance = cls.get_instance()
        except ValueError as e:
            raise AttributeError(f"Атрибут '{name}' не найден. Для доступа к методам экземпляра необходимо инициализировать клиент: {str(e)}")
        
        # Проверяем, есть ли атрибут в экземпляре
        if hasattr(instance, name):
            attr = getattr(instance, name)
            
            # Если это метод, возвращаем функцию, которая вызывает его на экземпляре
            if callable(attr):
                def method_proxy(*args, **kwargs):
                    return attr(*args, **kwargs)
                return method_proxy
            else:
                # Если это не метод, просто возвращаем атрибут
                return attr
        else:
            raise AttributeError(f"Атрибут '{name}' не найден ни в классе, ни в экземпляре")

class PaymentClient(BaseComponent, metaclass=AutoSingletonMeta):
    """
    Основной клиент для работы с платежным API.
    Реализует паттерн Singleton для однократной инициализации с автоматическим
    получением экземпляра при вызове методов.
    """
    _instance = None
    _init_params = None
   
    @classmethod
    def initialize(cls, api_key, base_url, base_logger_name="wata_api", log_level=logging.INFO, **kwargs):
        """
        Инициализация клиента с заданными параметрами.
       
        :param api_key: Ключ API для авторизации
        :param base_url: Базовый URL API
        :param base_logger_name: Базовое имя логгера (по умолчанию "wata_api")
        :param log_level: Уровень логирования (по умолчанию INFO)
        :param kwargs: Дополнительные параметры для HTTP-клиента
        """
        # Сохраняем параметры инициализации
        cls._init_params = {
            'api_key': api_key,
            'base_url': base_url,
            'component_name': "client",
            'parent_logger_name': None,
            'base_logger_name': base_logger_name,
            'log_level': log_level,
            **kwargs
        }
        
        if cls._instance is None:
            cls._instance = cls(
                api_key=api_key,
                base_url=base_url,
                component_name="client",
                parent_logger_name=None,
                base_logger_name=base_logger_name,
                log_level=log_level,
                **kwargs
            )
        return cls._instance
   
    @classmethod
    def get_instance(cls):
        """
        Получение существующего экземпляра клиента.
        Если экземпляр не существует, но есть параметры инициализации,
        создает новый экземпляр.
        """
        if cls._instance is None:
            if cls._init_params:
                # Если есть сохраненные параметры, создаем экземпляр
                params = cls._init_params.copy()
                cls._instance = cls(**params)
            else:
                raise ValueError("Клиент не инициализирован. Используйте метод initialize() с необходимыми параметрами.")
        return cls._instance
   
    def __init__(self, api_key, base_url, component_name="client",
                parent_logger_name=None, base_logger_name="wata_api",
                log_level=logging.INFO, **kwargs):
        """
        Конструктор клиента.
        """
        # Проверяем обязательные параметры
        if not api_key or not base_url:
            raise ValueError("Для инициализации клиента необходимы параметры api_key и base_url.")
            
        # Инициализация базового компонента для настройки логгера
        super().__init__(
            component_name=component_name,
            parent_logger_name=parent_logger_name,
            base_logger_name=base_logger_name,
            log_level=log_level
        )
       
        self.logger.info(f"Инициализация клиента API для {base_url}")
       
        # Создаем HTTP-клиент как подкомпонент
        self._http_client = self.create_subcomponent(
            HttpClient,
            component_name="http",
            api_key=api_key,
            base_url=base_url,
            **kwargs
        )
       
        # Инициализация модулей как подкомпоненты
        self.payment = self.create_subcomponent(
            PaymentModule,
            component_name="payment",
            http_client=self._http_client
        )
       
        self.webhook = self.create_subcomponent(
            WebhookModule,
            component_name="webhook",
            http_client=self._http_client
        )
       
        self.logger.debug("Клиент API успешно инициализирован")
   
    async def close(self):
        """
        Закрытие соединений и освобождение ресурсов.
        """
        self.logger.debug("Закрытие клиента API")
        await self._http_client.close()
   
    async def __aenter__(self):
        """
        Поддержка контекстного менеджера (async with).
        """
        return self
   
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Закрытие соединений при выходе из контекстного менеджера.
        """
        if exc_type:
            self.logger.error(f"Ошибка при выполнении операций: {exc_val}")
        await self.close()