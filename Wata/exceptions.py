# ./exceptions.py

"""
Классы исключений для работы с API.
"""

import logging
from .logger import setup_logger

class ApiError(Exception):
    """
    Ошибка при работе с API.
    """
    
    # Словарь с описаниями ошибок по их кодам
    ERROR_CODES = {
        "Payment:PL_1001": "Некорректная сумма платежной ссылки (сумма слишком маленькая или слишком большая)",
        "Payment:PL_1002": "Некорректная валюта платежной ссылки (создание ссылок в этой валюте запрещено)",
        "Payment:PL_1003": "Платежная ссылка недоступна либо уже оплачена",
        "Payment:CRY_1001": "Ошибка шифрования карточных данных",
        "Payment:TRA_1001": "Некорректный формат карточных данных при создании транзакции",
        "Payment:TRA_1002": "Некорректный номер карты при создании транзакции",
        "Payment:TRA_1003": "Некорректный срок действия карты при создании транзакции",
        "Payment:TRA_1004": "Некорректное значение CVV при создании транзакции",
        "Payment:TRA_1005": "Некорректная сумма при создании транзакции",
        "Payment:TRA_1013": "Данный способ оплаты не поддерживается",
        "Payment:TRA_2001": "Данный тип карты не поддерживается шлюзом",
        "Payment:TRA_2002": "Недостаточно средств",
        "Payment:TRA_2003": "Ошибка конфигурации магазина, обратитесь в поддержку",
        "Payment:TRA_2004": "Подозрение на мошенничество",
        "Payment:TRA_2006": "Отказ эмитента проводить онлайн-операцию",
        "Payment:TRA_2007": "Карта потеряна",
        "Payment:TRA_2009": "Отказ сети проводить операцию или неправильный CVV-код",
        "Payment:TRA_2010": "Карта не предназначена для онлайн-платежей",
        "Payment:TRA_2011": "Эмитент не найден",
        "Payment:TRA_2012": "Отказ по желанию держателя карты",
        "Payment:TRA_2013": "Ошибка на стороне эквайера — неверно сформирована транзакция",
        "Payment:TRA_2014": "Неизвестный эмитент карты",
        "Payment:TRA_2015": "Карта не предназначена для платежей",
        "Payment:TRA_2017": "Карта украдена",
        "Payment:TRA_2018": "Карта просрочена или неверно указан срок действия",
        "Payment:TRA_2019": "Неверный PIN-код",
        "Payment:TRA_2020": "Ограничение на карте",
        "Payment:TRA_2021": "Транзакция не разрешена по карте",
        "Payment:TRA_2022": "Превышена сумма по карте",
        "Payment:TRA_2023": "Карта заблокирована из-за нарушений безопасности",
        "Payment:TRA_2024": "Превышен лимит операций по карте",
        "Payment:TRA_2999": "Невозможно провести платеж",
    }
    
    def __init__(self, status_code, message=None, response_data=None, error_code=None, logger=None, logger_name=None):
        """
        Инициализация исключения.
        
        :param status_code: HTTP-статус ответа
        :param message: Сообщение об ошибке
        :param response_data: Полные данные ответа API
        :param error_code: Код ошибки из API
        :param logger: Готовый экземпляр логгера (приоритетнее, чем logger_name)
        :param logger_name: Имя логгера для создания, если logger не передан
        """
        self.status_code = status_code
        self.response_data = response_data
        self.error_code = error_code
        
        # Инициализация логгера
        if logger:
            self.logger = logger
        
        elif logger_name:
            self.logger = setup_logger(name=logger_name, level=logging.INFO)
        
        else:
            self.logger = setup_logger(name="wata_api.error", level=logging.INFO)
        
        # Извлечение информации об ошибке из ответа
        self.error_message = message
        self.error_details = None
        self.validation_errors = []
        
        if response_data and 'error' in response_data:
            error = response_data['error']
            
            # Обновляем код ошибки, если он указан в ответе
            if error.get('code'):
                self.error_code = error['code']
            
            # Обновляем сообщение об ошибке, если оно указано в ответе
            if error.get('message'):
                self.error_message = error['message']
            
            # Сохраняем детали ошибки, если они указаны
            if error.get('details'):
                self.error_details = error['details']
            
            # Сохраняем ошибки валидации, если они указаны
            if error.get('validationErrors'):
                self.validation_errors = error['validationErrors']
        
        # Если код ошибки известен, добавляем его описание к сообщению
        if self.error_code and self.error_code in self.ERROR_CODES:
            self.error_description = self.ERROR_CODES[self.error_code]
        else:
            self.error_description = None
        
        # Формируем финальное сообщение об ошибке
        final_message = self._build_message()
        
        # Логируем ошибку
        self.logger.error(final_message)
        
        # Логируем детали валидации отдельно, чтобы не перегружать основное сообщение
        if self.validation_errors:
            for error in self.validation_errors:
                members = ", ".join(error.get('members', []))
                message = error.get('message', 'Ошибка валидации')
                self.logger.error(f"Валидация: {message} (поля: {members})")
                
        super().__init__(final_message)
    
    def _build_message(self):
        """
        Построение информативного сообщения об ошибке.
        
        :return: Строка с подробным описанием ошибки
        """
        parts = []
        
        # Добавляем HTTP-статус
        parts.append(f"HTTP {self.status_code}")
        
        # Добавляем код ошибки, если он есть
        if self.error_code:
            parts.append(f"Код: {self.error_code}")
        
        # Добавляем описание кода ошибки, если оно есть
        if self.error_description:
            parts.append(f"Описание: {self.error_description}")
        
        # Добавляем сообщение об ошибке, если оно есть
        if self.error_message:
            parts.append(f"Сообщение: {self.error_message}")
        
        # Добавляем детали ошибки, если они есть
        if self.error_details:
            parts.append(f"Детали: {self.error_details}")
        
        # Добавляем информацию об ошибках валидации, если они есть
        if self.validation_errors:
            validation_messages = []
            for error in self.validation_errors:
                fields = ", ".join(error.get('members', []))
                message = error.get('message', 'Ошибка валидации')
                validation_messages.append(f"{message} (поля: {fields})")
            
            parts.append(f"Ошибки валидации: {'; '.join(validation_messages)}")
        
        return " | ".join(parts)
    
    def has_validation_errors(self):
        """
        Проверка наличия ошибок валидации.
        
        :return: True, если есть ошибки валидации, иначе False
        """
        return len(self.validation_errors) > 0
    
    def get_validation_errors_for_field(self, field_name):
        """
        Получение ошибок валидации для конкретного поля.
        
        :param field_name: Имя поля
        :return: Список сообщений об ошибках валидации для указанного поля
        """
        messages = []
        for error in self.validation_errors:
            members = error.get('members', [])
            if field_name in members:
                messages.append(error.get('message', 'Ошибка валидации'))
        return messages