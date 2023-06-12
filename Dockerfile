FROM alpine:3.18

RUN apk add --no-cache \
        bash git wget python3 py3-pip ipython

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV USER=agent
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home /project \
    "$USER"
USER $USER
WORKDIR /project
EXPOSE 8080
CMD ["python", "/app/agent.py"]
