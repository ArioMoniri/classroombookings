# Pod CI python image: the backend's pinned base + make/git (backend `make check`) + PyYAML (validate.sh).
ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends make git \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pyyaml==6.0.2
# The gates run with --user <smartsched-ci uid>; nothing in the image needs root at run time.
USER 65534
