FROM python:3.10.15-slim-bullseye

WORKDIR /home/choreouser

ENV PM2_HOME=/tmp

COPY 12.py /home/choreouser/12.py

RUN pip3 install websocket-client &&\
     addgroup --gid 10001 choreo &&\
     adduser --disabled-password  --no-create-home --uid 10001 --ingroup choreo choreouser &&\
     usermod -aG sudo choreouser


ENTRYPOINT [ "python3", "12.py" ]

USER 10001