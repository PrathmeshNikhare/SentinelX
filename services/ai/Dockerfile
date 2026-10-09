# AI service image (D-079). Build context: the repo root.
FROM python:3.12.5-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/app/.hf-cache
WORKDIR /app/services/ai
COPY services/ai/requirements.txt ./
# PyPI's Linux torch pulls CUDA; the CPU build comes from the PyTorch index and satisfies the torch==2.14.1 pin (D-070).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 \
 && pip install --no-cache-dir -r requirements.txt
COPY contracts/ /app/contracts/
COPY fixtures/ /app/fixtures/
COPY scripts/container-env.sh /app/scripts/container-env.sh
COPY services/ai/sentinelx_ai ./sentinelx_ai
# Bake the pinned embedding model into the image, then forbid Hub access at runtime (D-070).
RUN python -c "from sentinelx_ai.knowledge import SentenceEmbedder; SentenceEmbedder().encode(['warm-up'])"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/app/scripts/container-env.sh"]
CMD ["python", "-m", "sentinelx_ai"]
