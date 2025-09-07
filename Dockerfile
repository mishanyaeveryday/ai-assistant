FROM public.ecr.aws/docker/library/python:3.11.10-slim-bookworm

WORKDIR /app

COPY main.py .

RUN <<eot
    set -ex
    pip install --upgrade pip
    pip install psutil ipython pandas numpy matplotlib plotly python-docx beautifulsoup4 requests
eot