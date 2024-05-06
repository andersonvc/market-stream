FROM python:3.12.3-slim-bullseye
RUN mkdir /app
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

RUN pip install poetry==1.8.2

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./

RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR;
COPY alpaca_crypto_client /app

CMD ["poetry", "run", "python", "/app/main.py"]