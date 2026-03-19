FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
