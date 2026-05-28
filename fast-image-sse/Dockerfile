FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install fastapi uvicorn boto3 redis jinja2 python-multipart

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]