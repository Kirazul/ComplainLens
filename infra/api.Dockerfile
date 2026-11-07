# ComplaintLens API image (also used as a Hugging Face Docker Space: port 7860, user 1000).
# Models are rebuilt inside the image from public data, so no model weights live in git.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    RETRIEVAL=dense

RUN useradd --create-home --uid 1000 user
WORKDIR /app

# 1. Dependencies first (cached layer while only the code changes).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. Code and the small assets the service needs at runtime.
COPY src ./src
COPY company ./company
COPY eval ./eval
COPY reports/results ./reports/results
COPY ml/scripts ./ml/scripts
RUN uv sync --frozen --no-dev

# 3. Rebuild the classical models from the public 2019 data (exact evaluated configuration) and
#    pre-download the multilingual embedding model, so the first request is fast.
RUN uv run --no-sync python ml/scripts/fetch_complaints2019.py \
 && uv run --no-sync python ml/scripts/train_classical.py \
 && uv run --no-sync python -c "from complaintlens.rag.knowledge import KnowledgeBase; \
from complaintlens.rag.retrieval import build_retriever; \
from complaintlens.settings import get_settings; \
print(build_retriever(KnowledgeBase.load(get_settings().help_center_dir)).name)"

RUN chown -R user:user /app
USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health')"
CMD ["uv", "run", "--no-sync", "complaintlens", "serve", "--host", "0.0.0.0", "--port", "7860"]
