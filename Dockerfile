# syntax=docker/dockerfile:1.7
# Governed LLM Gateway API runtime image.
#
# The image carries code only. Deployment configuration (model registry, provider
# runtime, client auth, policy router, ranking artifact) is mounted at run time and
# provider credentials arrive through the process environment from a real secret
# manager, so nothing baked here can widen what a deployment authorizes. There is no
# default CMD on purpose: the entrypoint requires explicit artifact flags and exits
# non-zero without them.

ARG PYTHON_IMAGE=python:3.13.12-slim-bookworm@sha256:a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6

# PYTHON_IMAGE's default is pinned by digest above; the ARG exists so a deployment can
# rebuild on an internal mirror of the same image.
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Resolve dependencies from the lockfile before the sources land, so a source-only
# change cannot invalidate the dependency layer. Every workspace member's manifest is
# required for resolution even though only the API and its dependencies get installed.
COPY pyproject.toml uv.lock ./
COPY packages/gateway-contracts/pyproject.toml packages/gateway-contracts/
COPY packages/gateway-core/pyproject.toml packages/gateway-core/
COPY packages/gateway-client/pyproject.toml packages/gateway-client/
COPY apps/gateway-api/pyproject.toml apps/gateway-api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package governed-llm-gateway-api

COPY packages/gateway-contracts/src packages/gateway-contracts/src
COPY packages/gateway-core/src packages/gateway-core/src
COPY apps/gateway-api/src apps/gateway-api/src

# --no-editable builds real wheels, so the runtime stage needs the virtualenv alone and
# never the sources. The consumer SDK is deliberately absent: nothing in a Gateway
# deployment imports it.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package governed-llm-gateway-api


# PYTHON_IMAGE's default is pinned by digest above; the ARG exists so a deployment can
# rebuild on an internal mirror of the same image.
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS runtime

# The virtualenv records its interpreter path, so runtime must resolve the same
# interpreter at the same location. Both stages therefore pin one identical base digest.
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 10001 gateway \
    && useradd --system --uid 10001 --gid gateway --home-dir /app --shell /usr/sbin/nologin gateway

COPY --from=builder --chown=root:root /app/.venv /app/.venv
COPY --chown=root:root LICENSE README.md /app/

# Deployment artifacts are mounted here read-only; the image ships none of them.
VOLUME ["/config"]

USER gateway:gateway
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/livez',timeout=2).status==200 else 1)"]

ENTRYPOINT ["governed-llm-gateway"]
