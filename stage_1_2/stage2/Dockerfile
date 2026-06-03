FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

CMD sh -c "python make_mixed_demo_alerts.py && python redis_publication.py --alerts outputs/demo_mixed_alerts.json --host ${REDIS_HOST:-redis} --port ${REDIS_PORT:-6379} --stream ${REDIS_STREAM:-ai_alerts} --delay ${PUBLISH_DELAY:-2}"
