FROM python:3.13-alpine

LABEL maintainer="id00l"
LABEL description="DockerVol: A simple Docker volume management web application."

ENV DOCKERVOL_HOST=0.0.0.0 \
    DOCKERVOL_PORT=5000 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
# docker-cli : arrêt des conteneurs pendant l'archivage, si le socket Docker est monté.
RUN apk add --no-cache docker-cli && pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY src/ src/

# Archives and the log file are written to the working directory: keep them outside the container.
WORKDIR /archives
VOLUME /archives
EXPOSE 5000

CMD ["python", "/app/main.py"]
