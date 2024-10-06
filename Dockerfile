FROM python:latest

RUN pip install flask requests
RUN pip install python-telegram-bot
RUN pip install redis

COPY app.py /app/app.py

WORKDIR /app

ENV TELEGRAM_BOT_TOKEN=""
ENV TELEGRAM_CHAT_ID=""

CMD ["python", "app.py"]