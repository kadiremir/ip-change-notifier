FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 STATE_FILE=/data/last_ip.json
WORKDIR /app
COPY app/ /app/
RUN useradd -r -u 1000 notifier && mkdir /data && chown notifier /data
USER notifier
VOLUME /data
CMD ["python", "main.py"]
