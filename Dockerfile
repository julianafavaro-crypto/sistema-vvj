FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN printf '#!/bin/sh\nexec gunicorn app:app --bind "0.0.0.0:${PORT}" --workers 2\n' > /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/bin/sh", "/app/start.sh"]
