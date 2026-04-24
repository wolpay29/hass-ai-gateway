FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Voice models are mounted here at runtime
VOLUME ["/models"]

EXPOSE 10400

CMD ["python", "main.py"]
