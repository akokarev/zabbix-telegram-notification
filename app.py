import os
import logging
from flask import Flask, request, jsonify
import requests
from threading import Timer
import redis
from dotenv import load_dotenv
import subprocess

load_dotenv() # Загрузка переменных окружения из файла .env


app = Flask(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DELAY = int(os.getenv('DELAY', 300))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Настройка подключения к Redis
try:
    redis_client = redis.StrictRedis(host='redis', port=6379, db=0, decode_responses=True)
    if redis_client.ping():
        logging.info("Успешное подключение к базе Redis")
except redis.ConnectionError as e:
    logging.error("Не удалось подключиться к базе Redis")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=data)
        response_json = response.json()
        if response.status_code == 200 and response_json.get("ok"): # Успешная отправка
            logging.info(f"Сообщение отправлено в Telegram")
            return response_json
        else: # Ошибка при отправке
            logging.error(f"Ошибка отправки в Telegram: {response_json.get('description')}")
            return None
    except Exception as e:
        # Логирование исключений (ошибок сети, времени ожидания и прочее)
        logging.error(f"Исключение при отправке сообщения в Telegram: {e}")
        return None

def delete_message_after_delay(message_id, event_id, delay=DELAY):
    redis_client.set(f"timer_{event_id}", delay) # Сохраняем информацию о запланированном удалении
    Timer(delay, lambda: delete_message(message_id)).start()
    Timer(delay + 10, lambda: delete_event_from_messages(event_id)).start()

def delete_message(message_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    data = {
        "chat_id": CHAT_ID,
        "message_id": message_id
    }
    response = requests.post(url, data=data)    
    if response.status_code == 200:
        logging.info(f"Сообщение {message_id} успешно удалено")
    else:
        logging.error(f"Ошибка удаления сообщения {message_id}: {response.text}")

def delete_event_from_messages(event_id, delay=DELAY):
    if redis_client.exists(f"message_{event_id}"):
        redis_client.delete(f"message_{event_id}")
        logging.info(f"Удалено событие {event_id} из redis после {delay + 10} секунд")
    if redis_client.exists(f"timer_{event_id}"):
        redis_client.delete(f"timer_{event_id}")
        logging.info(f"Удален таймер {event_id} из redis после {delay + 10} секунд")

def check_pending_timers():
    # Получаем все ключи с таймерами
    keys = redis_client.keys('timer_*')
    for key in keys:
        event_id = key.split('_')[1]
        remaining_time = redis_client.get(key)
        
        # Проверяем, есть ли в Redis сообщение для удаления
        message_id = redis_client.get(f"message_{event_id}")
        if message_id:
            logging.info(f"Восстановление таймера для удаления сообщения {message_id} для события {event_id}, осталось {remaining_time} секунд")
            delete_message_after_delay(message_id, event_id, int(remaining_time))

@app.route('/notify', methods=['POST'])
def notify():
    data = request.json.get('monitorJSON', {})
    text = data.get('text', '')

    logging.info(f"Received JSON: {request.json}")

    lines = text.split('\n')
    if len(lines) < 2:
        return jsonify({"status": "error", "message": "Invalid message format"}), 400

    subject = lines[0].strip().lower()
    message_body = '\n'.join(lines[1:]).strip()

    if 'problem' in subject: 
        trigger_name, host_name, host_ip, severity, event_time, last_value, event_id = parse_message_body(message_body)
        message = f"🚨 <b>ПРОБЛЕМА</b>: {trigger_name} <b>НА</b> {host_name} 🚨\n\n" \
                  f"Хост: {host_ip}\n" \
                  f"Серьёзность: {severity}\n" \
                  f"Дата/Время: {event_time}\n" \
                  f"Текущее значение: {last_value}\n\n" \
                  f"📍 <b>Номер проблемы</b>: {event_id}"
        response = send_telegram_message(message)
        if response:
            message_id = response.get("result", {}).get("message_id")
            if message_id:
                redis_client.set(f"message_{event_id}", message_id)
                logging.info(f"Сообщение отправлено и сохранено в Redis: event_id={event_id}, message_id={message_id}")
            else:
                logging.error(f"Не удалось получить message_id от Telegram для event_id={event_id}")
        else:
            logging.error(f"Ошибка отправки сообщения в Telegram для event_id={event_id}")

    elif 'update' in subject: 
        user, action, event_message, host_ip, severity, event_time, last_value, event_age, event_id = parse_update_message(message_body)
        message_id = redis_client.get(f"message_{event_id}")
        if message_id:
            logging.info(f"Found message_id: {message_id} for event_id: {event_id}")
            message = f"🔄 <b>ОБНОВЛЕНИЕ</b>: Пользователь <b>{user}</b> выполнил действие <b>{action}</b>\n\n" \
                    f"Сообщение: {event_message}\n" \
                    f"Хост: {host_ip}\n" \
                    f"Серьёзность: {severity}\n" \
                    f"Дата/Время: {event_time}\n" \
                    f"Текущее значение: {last_value}\n" \
                    f"Длительность: {event_age}\n\n" \
                    f"📍 <b>Номер проблемы</b>: {event_id}"
            delete_message(message_id) 
            response = send_telegram_message(message)
        if response:
            message_id = response.get("result", {}).get("message_id")
            if message_id:
                redis_client.set(f"message_{event_id}", message_id)
                logging.info(f"Сообщение отправлено и сохранено в Redis: event_id={event_id}, message_id={message_id}")
            else:
                logging.error(f"Не удалось получить message_id от Telegram для event_id={event_id}")
        else:
            logging.error(f"Ошибка отправки сообщения в Telegram для event_id={event_id}")

    elif 'recovery' in subject: 
        trigger_name, host_name, host_ip, recovery_time, event_age, event_id = parse_message_body(message_body, recovery=True)
        message_id = redis_client.get(f"message_{event_id}")
        if message_id:
            logging.info(f"Found message_id: {message_id} for event_id: {event_id}")
            message = f"✅ <b>ВОССТАНОВЛЕНО</b>: {trigger_name} <b>НА</b> {host_name} ✅\n\n" \
                      f"Хост: {host_ip}\n" \
                      f"Дата/Время восстановления: {recovery_time}\n" \
                      f"Продолжительность: {event_age}\n\n" \
                      f"📍 <b>Номер проблемы</b>: {event_id}\n\n" \
                      f"👍 Проблема решена."
            delete_message(message_id)
            response = send_telegram_message(message)
        if response:
            message_id = response.get("result", {}).get("message_id")
            if message_id:
                redis_client.set(f"message_{event_id}", message_id)
                logging.info(f"Сообщение отправлено и сохранено в Redis: event_id={event_id}, message_id={message_id}")
                delete_message_after_delay(message_id, event_id)
            else:
                logging.error(f"Не удалось получить message_id от Telegram для event_id={event_id}")
        else:
            logging.error(f"Ошибка отправки сообщения в Telegram для event_id={event_id}")

    return jsonify({"status": "success"})

@app.route('/notify', methods=['POST'])
def notify():
    data = request.json.get('monitorJSON', {})
    text = data.get('text', '')

    logging.info(f"Received JSON: {request.json}")

    lines = text.split('\n')
    if len(lines) < 2:
        return jsonify({"status": "error", "message": "Invalid message format"}), 400

    subject = lines[0].strip().lower()
    message_body = '\n'.join(lines[1:]).strip()

    # Проверяем наличие команды в сообщении
    if 'ping' in subject or 'traceroute' in subject:
        command_type, host_ip = parse_message_body(message_body)  # Предполагаем, что у вас есть функция parse_command для извлечения команды и IP
        if command_type and host_ip:
            if command_type == 'ping':
                result = execute_command(f'ping -c 4 {host_ip}')
            elif command_type == 'traceroute':
                result = execute_command(f'traceroute {host_ip}')
            else:
                result = {"status": "error", "message": "Unsupported command."}

            # Отправка результата в Telegram
            message = f"Команда: {command_type}\nРезультат:\n{result.get('output', result.get('message'))}"
            send_telegram_message(message)
            return jsonify({"status": "success"}), 200


def execute_command(command):
    """ Выполняет команду и возвращает результат. """
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
        return {"status": "success", "output": output.decode()}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.decode()}
    
def is_valid_ip(ip):
    """ Проверяет, является ли строка допустимым IP-адресом. """
    import re
    # Регулярное выражение для проверки IP-адреса
    pattern = re.compile(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$')
    return pattern.match(ip) is not None

def parse_message_body(body, recovery=False):
    lines = body.split('\r\n')
    if not recovery:
        trigger_name = lines[0].split(': ')[1]
        host_name = lines[1].split(': ')[1]
        host_ip = lines[2].split(': ')[1]
        severity = lines[3].split(': ')[1]
        event_time = lines[4].split(': ')[1]
        last_value = lines[5].split(': ')[1]
        event_id = lines[6].split(': ')[1]
        return trigger_name, host_name, host_ip, severity, event_time, last_value, event_id
    else:
        trigger_name = lines[0].split(': ')[1]
        host_name = lines[1].split(': ')[1]
        host_ip = lines[2].split(': ')[1]
        recovery_time = lines[3].split(': ')[1]
        event_age = lines[4].split(': ')[1]
        event_id = lines[5].split(': ')[1]
        return trigger_name, host_name, host_ip, recovery_time, event_age, event_id

def parse_update_message(body):
    """Парсит тело сообщения для обновлений"""
    lines = body.split('\r\n')
    user = lines[0].split(': ')[1]
    action = lines[1].split(': ')[1]
    event_message = lines[2].split(': ')[1]
    host_ip = lines[3].split(': ')[1]
    severity = lines[4].split(': ')[1]
    event_time = lines[5].split(': ')[1]
    last_value = lines[6].split(': ')[1]
    event_age = lines[7].split(': ')[1]
    event_id = lines[8].split(': ')[1]
    return user, action, event_message, host_ip, severity, event_time, last_value, event_age, event_id

if __name__ == '__main__':
    check_pending_timers()
    logging.info(f"Используемый delay удаления сообщения: {DELAY} секунд")
    app.run(host='0.0.0.0', port=5000)