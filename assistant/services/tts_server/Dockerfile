FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends wget && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Voice models are mounted here at runtime
VOLUME ["/models"]

EXPOSE 10400

ENTRYPOINT ["./entrypoint.sh"]
