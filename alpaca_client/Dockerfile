FROM python:3.9.9-alpine3.15
RUN apk update
RUN apk add postgresql-dev gcc python3-dev musl-dev libffi-dev
RUN apk --no-cache add curl

ENV POETRY_VERSION=1.1.12
RUN pip3 install "poetry==$POETRY_VERSION"

WORKDIR /app
COPY poetry.lock pyproject.toml /app/

RUN poetry update && poetry install

COPY main.py /app/
