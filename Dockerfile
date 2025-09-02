FROM public.ecr.aws/docker/library/python:3.11.10-slim-bookworm
WORKDIR /workdir
RUN <<eot
    set -ex

    pip install --upgrade pip
    pip install psutil ipython pandas numpy matplotlib plotly docx
eot