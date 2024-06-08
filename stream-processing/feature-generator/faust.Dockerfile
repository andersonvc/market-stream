FROM python:3.11.9-slim-bookworm as requirements

ENV POETRY_VERSION=1.8.3
RUN pip install poetry==${POETRY_VERSION}

COPY poetry.lock pyproject.toml ./
RUN mkdir /src
RUN poetry export -f requirements.txt --without-hashes -o /src/requirements.txt 

FROM python:3.11.9-slim-bookworm as app

RUN adduser appuser
WORKDIR /home/appuser 
USER appuser:appuser 
ENV PATH=/home/appuser/.local/bin:${PATH}

COPY --from=requirements /src/requirements.txt .
RUN echo $(poetry --version)
RUN pip install --no-cache-dir --user -r requirements.txt 

