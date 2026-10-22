FROM python:3.13-slim-bookworm@sha256:a881a81282cca8c57f97014867fa651def1b3799030cc6b1cff45ed55ba8ef36 AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src PATH=/opt/venv/bin:$PATH HOME=/tmp XDG_CACHE_HOME=/tmp/cache
RUN python -m venv /opt/venv
WORKDIR /app
COPY --chmod=0644 app/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY app/src ./src
COPY app/migrations ./migrations
COPY app/alembic.ini ./alembic.ini
ARG APP_VERSION=development
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.source="https://github.com/naiin/devPlatformDeveloper"
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "platform_app.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --chmod=0644 app/requirements-dev.lock ./requirements-dev.lock
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.lock
COPY app/tests ./tests
COPY app/pyproject.toml ./pyproject.toml
COPY scripts/release.py /scripts/release.py
USER 10001:10001
CMD ["pytest", "-q"]

FROM app AS runtime
USER root
# Installers are build tools, not application dependencies. Remove their
# vendored libraries and bundled wheels from the published runtime surface.
RUN /opt/venv/bin/python -m pip uninstall -y pip \
    && /usr/local/bin/python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip
USER 10001:10001
