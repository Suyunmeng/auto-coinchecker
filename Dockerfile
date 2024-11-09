FROM python:3.10.15-slim-bullseye

WORKDIR /home/choreouser

ENV PM2_HOME=/tmp

COPY app/ /home/choreouser/

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js 和 PM2
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs &&\
    npm install -g pm2

RUN apt update &&\
     apt-get install -y shellinabox

RUN pip3 install websocket-client requests &&\
     addgroup --gid 10001 choreo &&\
     adduser --disabled-password  --no-create-home --uid 10001 --ingroup choreo choreouser &&\
     usermod -aG sudo choreouser


ENTRYPOINT [ "bash", "/home/choreouser/run.sh" ]

USER 10001