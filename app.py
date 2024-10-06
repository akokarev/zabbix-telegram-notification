import os
import logging
from flask import Flask, request, jsonify
import requests
from threading import Timer
import redis

# Настройка подключения к Redis
redis_client = redis.StrictRedis(host='192.168.252.253', port=5279, db=0, decode_responses=True) 

app = Flask(__name__)

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DELAY = int(os.getenv('DELAY', 300))

# Настройка логирования
logging.basicConfig(level=logging.INFO)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    response = requests.post(url, data=data)
    return response.json()

def delete_message_after_delay(message_id, event_id, delay=DELAY):
    Timer(delay, lambda: delete_message(message_id)).start()
    Timer(delay + 10, lambda: delete_event_from_messages(event_id)).start()

def delete_message(message_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage"
    data = {
        "chat_id": CHAT_ID,
        "message_id": message_id
    }
    requests.post(url, data=data)

def delete_event_from_messages(event_id, delay=DELAY):
    if redis_client.exists(f"message_{event_id}"):
        redis_client.delete(f"message_{event_id}")
        logging.info(f"Удалено событие {event_id} из messages после {delay + 10} секунд")

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
        message_id = response.get("result", {}).get("message_id")
        if message_id:
            redis_client.set(f"message_{event_id}", message_id) 

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
            new_message_id = response.get("result", {}).get("message_id")
            if new_message_id:
                redis_client.set(f"message_{event_id}", new_message_id)
        else:
            logging.warning(f"No message_id found for event_id: {event_id}")

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
            new_message_id = response.get("result", {}).get("message_id")
            if new_message_id:
                redis_client.set(f"message_{event_id}", new_message_id)
                delete_message_after_delay(new_message_id, event_id)

    return jsonify({"status": "success"})

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
    logging.info(f"Using delay: {DELAY} seconds")
    app.run(host='0.0.0.0', port=5000)
