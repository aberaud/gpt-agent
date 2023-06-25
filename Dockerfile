FROM alpine:3.18

RUN apk add --no-cache \
        build-base cmake ninja bash git wget curl ipython \
        python3 python3-dev py3-pip \
        py3-yaml py3-dotenv py3-aiohttp py3-beautifulsoup4 py3-numpy py3-scipy py3-cryptography py3-cffi

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app/ .

ENV USER=agent
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home /project \
    "$USER"
USER $USER
WORKDIR /project
EXPOSE 8080
CMD ["python", "/app/agent_runner.py"]
