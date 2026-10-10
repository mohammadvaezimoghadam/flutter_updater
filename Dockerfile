ARG REGISTRY=""
FROM ${REGISTRY}python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt || \
    (echo "Primary PyPI registry failed/unreachable. Trying Tsinghua mirror..." && \
     pip install --no-cache-dir --default-timeout=1000 -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple/) || \
    (echo "Tsinghua mirror failed/unreachable. Falling back to devneeds mirror..." && \
     pip install --no-cache-dir --default-timeout=1000 -r requirements.txt --index-url https://pypi.devneeds.ir/simple/)

COPY . .

RUN mkdir -p /app/patches /app/data /app/releases

EXPOSE 8080

CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
