FROM alpine:3.18

LABEL maintainer="id00l"
LABEL description="DockerVol: A simple Docker volume management web application."
LABEL version="0.1.0"

ENV DOCKERVOL_VERSION=0.1.0
ENV DOCKERVOL_HOST=0.0.0.0
ENV DOCKERVOL_PORT=5000

RUN apk add --no-cache python3 py3-pip
RUN pip install --no-cache-dir flask
RUN mkdir -p /app/src
COPY src/ /app/src/
COPY main.py /app/
WORKDIR /app

CMD ["python3", "main.py"]
