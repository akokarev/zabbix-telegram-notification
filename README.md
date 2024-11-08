# Уведомления в Telegram с обновлением состояния события и удалением после тайм-аута

Этот проект представляет собой Flask-сервис, который интегрируется с вебхуками Zabbix для отправки уведомлений в Telegram. Данные о сообщениях хранятся в базе данных Redis, что обеспечивает их сохранение и управление даже при перезагрузке сервиса. Проект поддерживает удаление сообщений в Telegram на основе событий (проблема, обновление, восстановление), приходящих из Zabbix.

## Основные возможности
- **Интеграция с Zabbix**: Сервис принимает события из Zabbix через вебхук, обрабатывает их и отправляет уведомления в указанный чат Telegram.
- **Управление сообщениями**: Поддерживается отправка уведомлений о проблемах, обновлениях и восстановлении с автоматическим удалением сообщений по мере необходимости.
- **Хранение в Redis**: Данные о сообщениях (ID сообщений, ID событий, таймеры задержки) сохраняются в Redis для их восстановления после перезагрузки сервиса.
- **Настраиваемая задержка**: Возможность настройки задержки для удаления сообщений о восстановлении через переменные окружения.
- **Логирование**: Весь процесс логируется: успешные подключения к Redis, отправка сообщений в Telegram, а также любые возникающие ошибки.

## Требования
- **Python 3.8+**
- **Flask**
- **Redis**
- **Zabbix Webhook**
- **Токен Telegram бота**

## Начало работы

### 1. Клонирование репозитория
```bash
git clone https://github.com/yourusername/telegram-zabbix-notifier.git
cd telegram-zabbix-notifier
```

### 2. Создание файла окружения
Для настройки переменных окружения откройте .env в корне проекта и укажите следующие параметры:
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
DELAY=300  # Время задержки перед удалением сообщения в секундах
```

### 3. Запуск Docker контейнеров

Для запуска проекта с помощью Docker используйте Docker Compose. Убедитесь, что Docker и Docker Compose установлены, затем выполните команду для сборки и запуска контейнеров:
```bash
docker compose up -d --build
```

### 4. Настройка интеграции с Zabbix

Для настройки вебхуков в Zabbix выполните следующие шаги:

Перейдите в Оповещения → Способы оповещений.
Импортируйте файл Flask.yml.
Перейдите в Пользователи → Ваш пользователь → Оповещения
Добавьте оповещение 
- **Тип: Flask**
- **Отправлять на: http://<Ваш zabbix-telegram-notification сервер>:5000/notify**

### 5. Проверка логов
Для мониторинга состояния сервиса можно использовать Docker логи:
```bash
docker compose logs -f
```

### 6. Хранение данных в Redis
Redis используется для хранения:
- **ID событий**
- **ID сообщений Telegram**
- **Задержек и таймеров для удаления сообщений**
После перезагрузки данные из Redis восстанавливаются, обеспечивая управление отложенными или ожидающими удаления сообщениями.

### 7. Логирование
Процесс логирования предоставляет важную информацию о статусе запросов:
- **Успешное подключение к Redis:** Логируется успешное подключение к Redis.
- **Отправка сообщения:** Логируется успешная отправка сообщения в Telegram.
- **Обработка ошибок:** Если запрос к API Telegram завершается неудачей, логируется ошибка с указанием ее причины (например, "Not Found").
- **Удаление сообщений:** Логируется успешное удаление сообщения из Telegram и удаление соответствующей записи из Redis.

Пример логов:
```bash
INFO:root:Подключение к Redis на redis:6379 установлено
INFO:root:Получено событие Zabbix: Обнаружена проблема на Host123
INFO:root:Сообщение отправлено в Telegram: 🚨 <b>ПРОБЛЕМА</b>: Высокая загрузка CPU <b>НА</b> Host123 🚨
INFO:root:ID события 12345 и ID сообщения 67890 сохранены в Redis
INFO:root:Сообщение ID 67890 успешно удалено из Telegram
ERROR:root:Ошибка отправки в Telegram: Not Found
  ```
### Лицензия
Проект распространяется под лицензией MIT. Вы можете свободно использовать, модифицировать и распространять его.
