FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main_simple.py .
EXPOSE 8000
CMD ["uvicorn", "main_simple:app", "--host", "0.0.0.0", "--port", "8000"]
