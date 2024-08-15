FROM python:3.12.4-slim-bullseye
RUN apt-get update && apt-get install -y \
    ffmpeg

RUN pip3 install --upgrade pip

WORKDIR /app

COPY requirements.txt .

RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

COPY . .

CMD ["python3", "run.py"]
