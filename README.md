# ComplaintLens

Multilingual (English/French) complaint understanding, routing and verified response, with guaranteed-risk automation.
NLP semester project 2026–2027, by Mohamed Aziz Mansour and Rimel Zouari.

The live demo runs as the support desk of **LunaGo**, a fictional ride and food-delivery app in Montréal. A customer writes from any channel. ComplaintLens cleans the message, masks personal data, detects the language and understands it. It then links the message to the customer's trip, retrieves the relevant policy and drafts a cited reply. The reply is verified, and the system decides whether to send it, wait for an agent, or escalate. Every step is visible live in the console.

## Live demo

| | |
|---|---|
| LunaGo website (EN/FR) | https://kirazul.github.io/ComplainLens/ |
| ComplaintLens console | https://kirazul.github.io/ComplainLens/console/ |
| API (docs) | https://api-production-a4e30.up.railway.app/docs |

Send a complaint from any of these channels and watch it appear in the console within seconds:

| Channel | How | Where the reply goes |
|---|---|---|
| Email | write to `lunagocare@fldubai.com` | console (this free inbox receives only) |
| Contact form | website, "Contact support" | the ticket's tracking page |
| Live chat | website, "Chat with us" (every page) | the chat itself; the conversation continues there |
| Trip rating | website, "Rate a trip" (stars + comment) | the ticket's tracking page |
| Community forum | [GitHub Discussions](https://github.com/Kirazul/ComplainLens/discussions) of this repository | a comment in the thread |

Every ticket is a conversation: a customer can keep writing in the chat or on the ticket page, and
the AI reads the whole conversation again. Once an agent has replied, the AI only drafts.

The console is for staff only: sign in with a username and password. The first administrator is
created at startup from `ADMIN_USERNAME` / `ADMIN_PASSWORD` (locally, without a password:
`admin` / `admin`). Administrators add agents on the **Team** page; anyone can change their own
password from the account menu. Lost password: `uv run complaintlens set-password admin`.

In a conversation the agent sees the AI's suggestion in the reply box (send it, edit it, or write
their own), why the AI decided what it did, and the **Trip check**: which ride or order the message
was linked to, why, and the facts from the record that the reply may state (every number in a reply
is checked against them). The API sleeps when idle to stay within the free plan: the first request
after a pause can take about 20 seconds.

- Plan and research: [`docs/plan.md`](docs/plan.md)
- Project proposal: [`docs/proposal.md`](docs/proposal.md)
- Annotation guidelines: [`eval/annotation_guidelines.md`](eval/annotation_guidelines.md)

## Layout

| Path | What |
|---|---|
| `src/complaintlens/` | Python package: pipeline stages, RAG, store, channels (email, forum), API, CLI |
| `apps/web/` | Next.js app: LunaGo public site (`/en`, `/fr`) and ComplaintLens console (`/console`) |
| `company/help_center/` | LunaGo Help Center (EN/FR), the RAG knowledge base |
| `ml/scripts/` | Data preparation, EDA, baselines, training |
| `reports/results/` | Every reported number, as JSON |
| `tests/` | Python tests (`uv run pytest`) |
| `infra/`, `.github/workflows/` | Docker images; CI, website deploy, forum relay |

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
With an email inbox, the API reads it every 30 seconds while in use: either a free mail.tm inbox
(`uv run complaintlens inbox-create lunagocare` prints the settings; receive only), or any
IMAP/SMTP mailbox such as Gmail with an app password, which also replies in the same thread.
See `.env.example` for every setting.

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

## How it is hosted (free)

| Part | Where | How it updates |
|---|---|---|
| Website and console | GitHub Pages (static export) | workflow `pages.yml` on every push to `main` touching `apps/web` or the Help Center; the API address comes from the repository variable `API_URL` |
| API, models, database | Railway (Docker image `infra/api.Dockerfile`, SQLite on a 500 MB volume at `/app/data`) | `railway up --service api` from the repository root |
| Community forum relay | GitHub Actions, workflow `relay.yml` | runs on each new Discussion, and hourly to collect email and post agents' replies |

Railway service variables: `LLM_API_KEY`, `EMAIL_INBOX`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`,
`ADMIN_PASSWORD`, `CHANNEL_TOKEN`, `PUBLIC_BASE_URL`, `CORS_ORIGINS`, `DATABASE_URL`
(`sqlite:////app/data/app.db`) and `RAILWAY_RUN_UID=0` (the volume is owned by root). The service
uses the Dockerfile at `infra/api.Dockerfile`, health check `/api/health`, and sleeps when idle.
GitHub: secret `CHANNEL_TOKEN` (same value as on Railway) and variable `API_URL`.

The embedding model is loaded from its official int8 file so the whole service fits the 1 GB
container; the measured cost is in `reports/results/retrieval_int8.json` (not significant).

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

Every number in the plan and the report comes from a JSON file in `reports/results/`, written by
the script named in its docstring. For example:

```powershell
uv run python ml/scripts/eda_first_contacts.py data/interim/uber_first_contacts.parquet --out reports/results/eda_uber_first_contacts.json
uv run python ml/scripts/baseline_complaints2019.py --out reports/results/baseline_complaints2019.json
uv run python ml/scripts/eval_retrieval.py --models sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --out reports/results/retrieval_helpcenter.json
uv run python ml/scripts/eval_quantization.py --out reports/results/retrieval_int8.json
```
