# ComplaintLens

Multilingual (English/French) complaint understanding, routing and verified response, with guaranteed-risk automation.
NLP semester project 2026–2027, by Mohamed Aziz Mansour and Rimel Zouari.

The live demo runs as the support desk of **LunaGo**, a fictional ride and food-delivery app in Montréal. A customer writes by email or on the website. ComplaintLens cleans the message, masks personal data, detects the language and understands it. It then links the message to the customer's trip, retrieves the relevant policy and drafts a cited reply. The reply is verified, and the system decides whether to send it, wait for an agent, or escalate. Every step is visible live in the console.

- Plan and research: [`docs/plan.md`](docs/plan.md)
- Project proposal: [`docs/proposal.md`](docs/proposal.md)
- Annotation guidelines: [`eval/annotation_guidelines.md`](eval/annotation_guidelines.md)

## Layout

| Path | What |
|---|---|
| `src/complaintlens/` | Python package: pipeline stages, RAG, store, email channel, API, CLI |
| `apps/web/` | Next.js app: LunaGo public site (`/en`, `/fr`) and ComplaintLens console (`/console`) |
| `company/help_center/` | LunaGo Help Center (EN/FR), the RAG knowledge base |
| `ml/scripts/` | Data preparation, EDA, baselines, training |
| `reports/results/` | Every reported number, as JSON |
| `tests/` | Python tests (`uv run pytest`) |

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed automatically), Node 24 and pnpm.

```powershell
uv sync                                   # Python environment from the lockfile
uv run python ml/scripts/train_classical.py   # needs the 2019 complaint data, see "Data"
copy .env.example .env                    # then fill in the keys (optional, see below)
uv run complaintlens check                # verifies the LLM key and the mailbox, if configured
uv run complaintlens serve                # API on http://localhost:8000 (docs: /docs)
```

In a second terminal:

```powershell
cd apps/web
pnpm install
pnpm dev                                  # http://localhost:3000/en and http://localhost:3000/console
```

Without keys the system still runs end to end: understanding falls back to the classical models and every answer waits for an agent.
With `LLM_API_KEY` (free Groq key), replies are drafted with retrieval and verified.
With `EMAIL_ADDRESS` and `EMAIL_PASSWORD` (a Gmail app password), the API reads the inbox every 15 seconds and replies by email in the same thread.

Process one message from the command line and print its trace:

```powershell
uv run complaintlens send "J'ai été facturé deux fois pour ma course d'hier soir !" --sender you@example.com
```

## Run everything with Docker (one command)

```powershell
docker compose up --build      # website :3000, console :3000/console, API :8000/docs
```

The API image downloads the public 2019 complaint data, retrains the classical models and fetches
the embedding model at build time, so no model weights are stored in git.

## Deploy (free)

- **API → Hugging Face Docker Space.** In the GitHub repository settings, add the secret `HF_TOKEN`
  (a Hugging Face write token) and the variable `HF_SPACE` (e.g. `your-name/complaintlens-api`).
  Every push to `main` then deploys `infra/api.Dockerfile` (workflow `deploy-space.yml`).
  Set the Space secrets `LLM_API_KEY`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `PUBLIC_BASE_URL`, and
  optionally `DATABASE_URL` (a free Neon Postgres, `postgresql+psycopg://...`) to keep tickets
  across restarts.
- **Website → Vercel.** Import the repository, set the root directory to `apps/web` and the
  environment variable `NEXT_PUBLIC_API_URL` to the Space URL (`https://<user>-<space>.hf.space`).

## Data

Data files are not stored in git.

1. *Customer Support on Twitter* (Kaggle, CC BY-NC-SA 4.0), downloaded with the Kaggle CLI:

   ```powershell
   uv tool install kaggle --python 3.12 --with six   # the CLI forgets to declare `six`
   kaggle auth login                                  # opens the browser
   kaggle datasets download thoughtvector/customer-support-on-twitter -p data/raw/twcs --unzip
   uv run python -m complaintlens.data.twcs data/raw/twcs/twcs/twcs.csv --brand Uber_Support --out data/interim/uber_first_contacts.parquet
   ```

2. *Complaints on Twitter* (Preoțiuc-Pietro et al., 2019) and its severity labels (Jin & Aletras, 2021):

   ```powershell
   curl -o data/raw/complaints2019/complaints-data.csv https://raw.githubusercontent.com/danielpreotiuc/complaints-social-media/master/complaints-data.csv
   curl -L -o data/raw/complaints2019/complaint_severity_data.csv https://archive.org/download/complaint_severity_data/complaint_severity_data.csv
   ```

## Reproduce the reported numbers

```powershell
uv run python ml/scripts/eda_first_contacts.py data/interim/uber_first_contacts.parquet --out reports/results/eda_uber_first_contacts.json
uv run python ml/scripts/baseline_complaints2019.py --out reports/results/baseline_complaints2019.json
```
