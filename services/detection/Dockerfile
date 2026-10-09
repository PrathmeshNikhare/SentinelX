# Detection worker image (D-079). Build context: the repo root.
FROM python:3.12.5-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/services/detection
COPY services/detection/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY contracts/ /app/contracts/
COPY fixtures/ /app/fixtures/
COPY scripts/container-env.sh /app/scripts/container-env.sh
COPY services/detection/sentinelx_detection ./sentinelx_detection
# The Isolation Forest is trained deterministically from the seeded baseline (D-049): same artefact on every build.
RUN python -m sentinelx_detection.train
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app
ENTRYPOINT ["sh", "/app/scripts/container-env.sh"]
CMD ["python", "-m", "sentinelx_detection.worker"]
