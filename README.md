# ComplaintLens

Multilingual (English/French) complaint understanding, routing and verified response, with guaranteed-risk automation.
NLP semester project 2026–2027, by Mohamed Aziz Mansour and Rimel Zouari.

- Plan and research: [`docs/plan.md`](docs/plan.md)
- Project proposal: [`docs/proposal.md`](docs/proposal.md)

## Setup

Requires [uv](https://docs.astral.sh/uv/). Python 3.12 is installed automatically.

```powershell
uv sync            # create the environment from the lockfile
uv run pytest      # run the tests
```

## Data

Data files are not stored in git. Download the *Customer Support on Twitter* dataset with the Kaggle CLI
(free account; licence CC BY-NC-SA 4.0):

```powershell
uv tool install kaggle --python 3.12 --with six   # the CLI forgets to declare `six`
kaggle auth login                                  # opens the browser
kaggle datasets download thoughtvector/customer-support-on-twitter -p data/raw/twcs --unzip
```

Then build the cleaned Uber conversations:

```powershell
uv run python -m complaintlens.data.twcs data/raw/twcs/twcs/twcs.csv --brand Uber_Support --out data/interim/uber_first_contacts.parquet
```
