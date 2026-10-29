ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 \
    XDG_CACHE_HOME=/tmp/unlock-cache
WORKDIR /engine
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock
COPY src ./src
COPY tests ./tests
RUN pip install --no-deps --no-build-isolation .
RUN useradd --uid 10001 --create-home engine
USER engine
ENTRYPOINT ["unlock-engine"]
CMD ["--help"]
