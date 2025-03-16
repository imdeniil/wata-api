# ./logger.py
import logging

def setup_logger(name="wata", level=logging.INFO):
    """
    Настройка логгера для модуля.
   
    :param name: Имя логгера
    :param level: Уровень логирования
    :return: Настроенный логгер
    """
    logger = logging.getLogger(name)
   
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
   
    logger.setLevel(level)
    # Отключаем распространение логов к родительским логгерам
    logger.propagate = False
    return logger

class BaseComponent:
    """
    Базовый класс для всех компонентов API с иерархическим логированием.
    """
   
    def __init__(self, component_name, parent_logger_name=None, base_logger_name="wata_api", log_level=logging.INFO):
        """
        Инициализация базового компонента.
       
        :param component_name: Имя текущего компонента
        :param parent_logger_name: Имя родительского логгера (если этот компонент вложенный)
        :param base_logger_name: Базовое имя логгера, используется только если parent_logger_name не указан
        :param log_level: Уровень логирования
        """
        # Определяем полное имя логгера
        if parent_logger_name:
            self.logger_name = f"{parent_logger_name}.{component_name}"
        else:
            self.logger_name = f"{base_logger_name}.{component_name}"
       
        # Настраиваем логгер
        self.logger = setup_logger(name=self.logger_name, level=log_level)
       
    def create_subcomponent(self, component_class, component_name, log_level=None, **kwargs):
        """
        Создаёт и возвращает подкомпонент с корректным логгером.
       
        :param component_class: Класс создаваемого компонента
        :param component_name: Имя создаваемого компонента
        :param log_level: Уровень логирования для подкомпонента (если None, наследуется от родителя)
        :param kwargs: Дополнительные параметры для инициализации компонента
        :return: Экземпляр созданного компонента
        """
        if log_level is None:
            log_level = self.logger.level
       
        return component_class(
            component_name=component_name,
            parent_logger_name=self.logger_name,
            log_level=log_level,
            **kwargs
        )