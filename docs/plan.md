# ComplaintLens: Research Findings and Master Plan

**Team:** Mohamed Aziz Mansour · Rimel Zouari
**Module:** NLP Semester Project 2026–2027 (Dr. Nizar Omheni)
**Status:** the professor approved the topic (confirmed by the team on 2026-11-07). Research and baselines are done; the build has started, beginning with the live email chain. The proposal is in [`proposal.md`](proposal.md).

---

## 0. The plan in one screen

We create a **fictional ride-hailing and food-delivery company** ("LunaGo": one app for rides and food delivery), operating in **Montréal**. It covers both because 49% of real Uber support conversations are about rides and 16% about food delivery (§5.1). Montréal is a naturally bilingual English/French city. The company is real in every way that matters for the demo:
- a public website (Help Center, complaint form, live chat);
- a real email address (`support@<our-domain>`);
- a Telegram support bot;
- a customer database of riders, drivers and trips.

All of it is hosted for free.

Behind it runs **ComplaintLens**, the NLP system we build. When the professor sends a message through **any** of those channels, the following happens:

1. **It arrives.** It is converted into one common format, whatever the channel.
2. **It is understood.**
   - Language (EN/FR).
   - Message type: complaint, request, feedback, praise or spam. This also decides whether it needs an answer.
   - Category: fare and billing, driver behaviour, safety, lost item, cancellation, app bug, account, promotion, accessibility.
   - Severity, and risk flags (a safety incident is *always* escalated to a human).
   - Entities: trip date, amount, place, card digits (masked).
3. **It is linked.** The system finds the customer from their email address or chat account, finds the trip they are talking about, and finds similar or duplicate complaints and the recurring problem they belong to.
4. **It is routed.** It goes to the right team (Billing, Safety, Lost and Found, Tech, Driver Operations) with a priority score and a deadline.
5. **It is answered.**
   - A reply is drafted with **RAG**: the company's Help Center policies, plus **verified facts from the trip record** ("your ride on 3 Nov cost $18.40 including a $4.10 surge").
   - A **verifier** checks that every claim in the draft is supported by a source.
   - A **statistically guaranteed gate** decides whether it can be sent automatically or must wait for a human.
6. **It is sent back** on the same channel. The professor receives the email reply in their own inbox, with a ticket number and a tracking link.
7. **It is monitored.** Across all tickets, the system detects emerging problems ("overcharge complaints tripled since app version 5.2") and suggests probable causes.

A **live console** shows the professor every stage of their own message as it runs, with outputs, confidence scores, evidence and milliseconds.

The **intelligence** is trained and evaluated on **real data**: real customer complaints sent to `@Uber_Support` and other transport brands, with the companies' real replies, from the public *Customer Support on Twitter* dataset. It is also evaluated on our own human-annotated English and French test sets. The fictional company exists only so that a live demo can send real emails without impersonating Uber.

**How we win.** The rubric rewards *scientific quality over complexity* (spec §8.2). The channels and the website make an unforgettable demo (C7). The grade is earned by rigor: every NLP component has a **baseline, a metric, confidence intervals and an error analysis**, and five research questions carry the claims (C3 + C4 + C5 = 55 of the 100 points).

---

## 1. Verdict on the idea, and the risks we remove

The idea is strong: a real industry problem, genuinely NLP (classification, extraction, retrieval, clustering, generation), bilingual, and a demo that anyone can understand in 10 seconds ("send a complaint, watch what happens").

| Risk | Fix |
|---|---|
| **Kitchen-sink project** (spec §13, first pitfall) | Scope tiers (§12). The channels are *engineering*, so they don't need research claims. The *science* is concentrated in five research questions (§8). |
| **"We just called an API"** (spec §9: a pretrained model or API alone ≠ competence) | Our own contributions are explicit: the taxonomy and annotation guidelines; human gold sets with measured agreement; fine-tuned and distilled encoders that beat the LLM they learn from on cost and latency; a leakage-safe protocol; a reply verifier; a conformal gate; a trend detector evaluated with controlled injections. |
| **Impersonating a real company** | We never send anything as Uber. The live company is fictional and clearly labelled "a student project" in the website footer and every email. |
| **Fake-looking data** | Models are trained and tested on *real* complaints. Synthetic content (the fictional company's trips and policies) is used only to make the demo work, and is labelled as synthetic everywhere. No headline result is computed on synthetic data. |
| **Free services failing during the defence** | Every external service has a fallback (§10.3), and the whole system also runs locally with one command. |

---

## 2. What the professor grades, and how we target each point

| Code | Criterion (points) | "Excellent" requires (spec §8.3) | Our answer |
|---|---|---|---|
| C1 | Problem formulation (10) | Precise I/O, scope, constraints, measurable objectives, prior work | §3 formal spec with out-of-scope behaviour; five research questions with targets |
| C2 | Data and preprocessing (10) | Provenance, licence, EDA that informs design, every step justified | Datasheet per dataset; EDA notebook; preprocessing table with a "why" column (§6.1) |
| C3 | Methodology (25) | Justified against alternatives; understanding of internals | Every stage compares at least two methods; we fine-tune and distill ourselves; architecture decision records |
| C4 | Experimental design (20) | No leakage, baselines, ablations, seeds and CIs, human eval with criteria | Conversation-level, time-based split; dedup; 5 seeds; bootstrap CIs; significance tests; blind human evaluation with κ |
| C5 | Error analysis (10) | Error categories with examples and causes; honest limits | Error taxonomy per task; interactive error browser in the console; threats-to-validity section |
| C6 | Report and reproducibility (10) | Reproducible from README; ethics; AI disclosure | One-command reproduction; pinned versions; model cards and datasheets; ACL-style report |
| C7 | Defence (15, individual) | Working demo; every member answers on *every* part | The professor sends a complaint *themselves* and watches it live; both members rehearse all modules |

Spec §7.3 says the professor may ask us to *run the system on a new input* and to *trace any number back to its experiment*. Our whole demo is built around the first. For the second, the console's **Experiments** page links every number to its config, seed and commit.

---

## 3. Problem definition (spec §4A)

**Input.** One customer message from any channel: free text from 1 to about 1,000 words, optional subject line, sender identity (email address / chat ID), channel, timestamp, and conversation thread (earlier messages).

**Output.** A `Ticket` record:

| Field | Values |
|---|---|
| `language` | `en`, `fr`, `other` → `other` is routed to a human |
| `message_type` | `complaint`, `request` (question or demand), `feedback` (suggestion), `praise`, `spam_or_irrelevant` |
| `response_required` | yes/no + urgency: `immediate`, `24h`, `standard` |
| `category` | fare & billing · driver behaviour · **safety incident** · lost item · cancellation & no-show · **delivery order** · app & technical · account & access · promotions & credits · accessibility · other |
| `severity` | 1–4 (no explicit reproach → disapproval → accusation → blame; Trosborg, as used by Jin & Aletras 2021) |
| `risk_flags` | `safety`, `injury`, `harassment_discrimination`, `legal_threat`, `fraud_account_takeover`, `media_threat`, `vulnerable_person` |
| `sentiment`, `emotion` | negative/neutral/positive; anger, frustration, anxiety, disappointment, gratitude |
| `entities` | DATE/TIME, MONEY, LOCATION, TRIP_REF, DRIVER_REF, PAYMENT_REF, PERSON (masked) |
| `customer`, `trip` | linked records, with match confidence |
| `similar`, `duplicates`, `cluster` | ticket IDs, problem cluster with label |
| `team`, `priority`, `sla` | routing destination, score 0–100 with explanation, deadline |
| `reply` | text + citations + verification result + decision: `auto_sent` / `awaiting_approval` / `escalated` / `no_reply` |

**Constraints.** Free hosting with CPU-only inference. Understanding and routing take < 1.5 s p95; a full answer takes < 8 s. Personal data is masked before any external API call. Zero cost.

**Out-of-scope behaviour.**
- Other languages, gibberish or spam: no auto-reply; tagged and routed.
- Low confidence on any decision: escalate to a human.
- Missing information (no trip found): the reply asks a precise clarifying question instead of guessing.
- Safety, injury or legal: never automated; immediate escalation.

---

## 4. The complaint taxonomy ("many types of complaints")

Messages differ along **independent axes**. Mixing them into one label list is the classic mistake, so each gets its own field:

1. **Communicative intent** (`message_type`). This answers "is it really a complaint, or just a comment?"
2. **Need for action** (`response_required`). "Worst app ever lol" is a complaint with nothing to answer; "Where is my refund?" is a request that needs an answer.
3. **Topic** (`category`). The ride-hailing tree in §3, with sub-categories (e.g. fare & billing → surge, double charge, wrong route, cancellation fee, refund delay).
4. **Expressed severity versus business risk.** A calm message reporting an assault is low *expressed* severity but maximum *risk*. Keeping them separate is what makes the routing safe.

The **annotation guidelines** (definitions, decision rules, borderline examples) are written first. They are tested on a pilot, revised, and their reliability is measured with Cohen's κ.

---

## 5. Data plan (spec §4B, criterion C2)

### 5.1 Datasets

| # | Dataset | What it is | Lang. | Size | Licence | Role |
|---|---|---|---|---|---|---|
| **D1** | **Customer Support on Twitter** (TWCS; Kaggle `thoughtvector/customer-support-on-twitter`) | Real tweets between customers and the support accounts of ~100 large brands, with timestamps and reply links | EN (mostly) | ~3M tweets in total; `@Uber_Support` is one of the largest brands. Exact counts come from the EDA | CC BY-NC-SA 4.0 (as declared by HF mirrors; confirm on Kaggle) | **Main real data:** Uber conversations (primary), plus other transport brands (airlines, rail) for robustness. Complaints, agent replies, real timestamps for trend evaluation |
| **D2** | **Complaints on Twitter** (Preoțiuc-Pietro et al., ACL 2019; GitHub `danielpreotiuc/complaints-social-media`) + **severity labels** (Jin & Aletras, NAACL 2021) | Expert-labelled tweets across 9 domains: complaint vs. not, 4 severity levels | EN | ~3.4k | research use (verify) | Published labelled benchmark for `message_type` and `severity`; lets us compare with **published results** (spec §4E) |
| **D3** | **Customer Support Tickets** (Bueck; Kaggle/HF `Tobi-Bueck/customer-support-tickets`) | Tickets in email form (subject + body) with department, priority and the agent's answer | EN (+DE unused) | ~62k | CC BY-NC 4.0 | Email-style text for robustness; priority labels. **Likely synthetic** → auxiliary only, never headline |
| **D4** | **ComplaintLens Gold-EN** (ours) | ~1,000 real `@Uber_Support` customer tweets/threads, annotated with the full schema | EN | ~1,000 | CC BY-NC-SA (inherits D1) | **Test set** for all classification tasks |
| **D5** | **ComplaintLens Gold-FR** (ours) | French rider messages: written natively by French speakers in the Montréal setting, plus human post-edited translations of a D4 sample (kept separate, because translated text is easier) | FR | 400–600 | CC BY 4.0 | **French test set** (cross-lingual transfer) |
| **D6** | **LunaGo Help Center** (ours, labelled fictional) | ~40 bilingual policy articles: fares and surge, cancellation fees, refunds, lost items, safety procedures, account security, accessibility, promotions | EN/FR | ~40 docs | ours | RAG knowledge base. Because we wrote it, faithfulness is checkable fact by fact |
| **D7** | **LunaGo operations DB** (synthetic, generated with a seeded script) | Riders, drivers, vehicles, trips (route, fare breakdown, surge, payment), refunds, lost-item reports, app versions, city zones | — | ~5k riders, ~100k trips | ours | Lets replies *verify* facts; gives the metadata for root-cause analysis. Demo only, no NLP claims |

**Verified so far (2026-11-07):**
- **D1 profiled** (`reports/results/eda_uber_first_contacts.json`):
  - **Size:**
    - 2,811,774 tweets, 108 brands. Licence CC BY-NC-SA 4.0 (confirmed by Kaggle).
    - `@Uber_Support` is the 3rd-largest brand (56,270 replies). `@AskLyft` (11,809 replies) gives a second ride-hailing company for a **train-on-Uber, test-on-Lyft** generalisation check.
  - **Shape of the Uber data:**
    - **41,855 Uber first contacts**, almost all from Oct–Dec 2017; a few date back to 2014 and are filtered out.
    - 95% are a single tweet; median 22 words (p90 39).
    - Uber's median first reply is 8.2 minutes.
    - 242 exact-duplicate texts.
  - **Ride vs. food (keyword estimate):** ~49% mention rides, ~16% food delivery. → **Decision:** the fictional company's single app offers rides *and* food delivery, with a `delivery_order` category.
  - **Collection bias:** the dataset was built around company replies. Only 19 of 19,762 customer-started threads tagging `@Uber_Support` went unanswered. → "Did the company reply?" **cannot** be used as a "response required" label; that label comes only from human annotation. This is a limitation for the report.
  - **Real incident found in EDA:** the busiest day, **14 Nov 2017 (1,333 conversations vs. ~800 on typical busy days)**, was a **free Krispy Kreme doughnut promotion on Uber Eats that crashed the app**. The top lifted words that day were *doughnuts, krispy, kreme, crashed, promotion, free*. This is our headline real event for trend detection and for the Replay demo.
  - **Data breach:** the 21 Nov 2017 disclosure leaves only a weak trace (at most 16 breach/hack mentions in a day), because customers write to support about their own problems rather than about news.
- **D1 downloaded via the Kaggle CLI:** a single `twcs/twcs.csv` (516 MB uncompressed).
- **D2 downloaded from GitHub:**
  - `complaints-data.csv` has no header; its columns are `id, text, is_complaint, domain`.
  - **3,449 tweets: 1,232 complaints (35.7%) / 2,217 non-complaints.**
  - Domains: random_reply 739, random_tweet 737, services 336, software 292, electronics 290, apparel 261, **transport 247**, retail 198, food 128, other 128, cars 93.
- **Severity labels downloaded** from archive.org (`complaint_severity_data`):
  - Same 3,449 tweets.
  - Labels 0 = not a complaint, then 1–4 = 436 / 376 / 224 / 196, matching the authors' corrected table.
  - **Data-quality problems:**
    - Tweet IDs were corrupted by a spreadsheet (`2.26E+16`), so they cannot be joined by ID.
    - The text is lower-cased and re-tokenised.
  - The text has `<user>`/`<url>` placeholders and decoded HTML entities, and words with curly apostrophes were dropped.
  - **Finding:** both releases share the same row order, and the complaint labels agree on all 3,449 rows.
  - **Decision:** align by row position, *verified* per row by text similarity (all ≥ 0.9, except one row the spreadsheet turned into `#NAME?`, which is flagged). Train on the original text, because casing and punctuation carry intensity ("NEVER AGAIN!!!").
  - Implemented and tested in `src/complaintlens/data/complaints2019.py`.
- No public French complaint dataset with a clear licence exists on Kaggle or Hugging Face. We searched; for example, `BenGaia/avis-clients` has an unknown licence. That is why D5 is ours.
- Public Hugging Face copies of D1 either drop the timestamps (`TNE-AI/...`, `MohammadOthman/...`) or now require a login (`Rakuto/...`). The original Kaggle file is the reliable source: one download with a free Kaggle account.
- We also evaluated the US CFPB complaint database (verified: 19M complaints, CC0, narratives in the FOIA archive). We set it aside because it is about banks, not ride-hailing, and is far heavier to download. It stays a documented alternative.

### 5.2 Labels: where they come from (and why that is a contribution)
D1 has no category labels. We use a modern, defensible recipe:

1. **Human gold labels** (D4, D5): double annotation in **Argilla** (free, hosted on a Hugging Face Space), pilot → κ → revised guidelines → full set; 30% double-annotated and adjudicated. Test-only.
2. **Silver labels for training:** an LLM labels ~20–30k D1 messages using the *same guidelines* as the humans. We **measure the silver-label accuracy against the gold labels** instead of trusting it.
3. **Distillation:** we fine-tune a small multilingual encoder on the silver labels (plus D2's human labels). Research question RQ1 tests whether the student **matches or beats its LLM teacher** at ~1/100 of the cost and latency, which is the reason to train it at all.
4. **Free weak signals:** in D1, whether the company replied, and how fast, is a real behavioural signal used for analysis (not as ground truth).

### 5.3 Data-understanding checks planned (EDA)
- Tweet length.
- Thread depth.
- Language mix.
- Class balance after annotation.
- Volume over time per brand.
- Share of messages the company answered.
- Reply delay.
- Near-duplicates (bots, copy-paste).
- How often customers write in multiple tweets (we merge consecutive tweets into one message).
- Brand-name and handle frequency: these must be masked, or the models learn "mentions Uber" instead of the complaint.

Each finding is written next to the design decision it caused.

---

### 5.4 First baseline results (milestone 3, 2026-11-07)
Source: `reports/results/baseline_complaints2019.json` (code: `ml/scripts/baseline_complaints2019.py`); published numbers in `reports/results/published_reference_complaints2019.json`.

**Protocol:** D2, stratified 10-fold CV with duplicate tweets kept in one fold, × 5 seeds; default hyperparameters (no tuning); macro-F1 (mean ± std).

| Task | Majority (ours / published) | Best published non-neural | **Ours: TF-IDF word+char + LR** | Best published transformer |
|---|---|---|---|---|
| Complaint vs. not | 39.1 / 39.1 | 79.0 | **81.5 ± 0.2** | 88.2 |
| Severity 1–4 | 13.1 / 13.0 | 43.5 | **46.2 ± 1.1** (QWK 0.50) | 55.7 |

- **Majority-class scores match the papers** to within 0.1, an independent check of our data alignment and metric.
- **Word+char features beat char-only** on both tasks (paired bootstrap: +1.6 points, p = 0.0005; +2.6 points, p = 0.013).
- **Duplicate grouping changed scores by less than the seed variance** (ablation file `baseline_complaints2019_ungrouped_ablation.json`): only 64 duplicates (1.9%) here. We report it as checked, not as a problem.
- **Caveat:** same protocol as the papers but different fold assignment; the papers also tuned hyperparameters in an inner loop and we did not, which, if anything, favours them.
- **Target for our fine-tuned encoder:** close the gap to the 88.2 / 55.7 transformer results.

### 5.5 First trend-detection results (RQ4, 2026-11-07)
Source: `reports/results/trends_uber.json` (code: `src/complaintlens/trends.py`, `ml/scripts/eval_trends.py`).

**Protocol:**
- Real `@Uber_Support` stream, daily bins.
- Thresholds are chosen on October under the same alarm budget (≤ 3 incidents/day) and applied unchanged to November.
- Injection: 10/20/40 real messages about a moderately rare topic (2–15 messages/day) are added on a random day; 3 seeds × 60 trials.

| Method | Recall +10 | +20 | +40 | Incidents/day Oct / Nov |
|---|---|---|---|---|
| **Bursting terms, rate-based Poisson z-score** | **0.73** | **0.94** | **1.00** | 2.08 / 4.94 |
| Fixed count threshold (baseline) | 0.00 | 0.00 | 0.00 | 1.12 / 2.19 |

- **Real event (14 Nov 2017, Uber Eats × Krispy Kreme promotion crash):**
  - Top incident of the day: "krispy, kreme" (102 messages, z = 101).
  - Hourly replay: onset 13:00 UTC (5 messages), surge at 14:00 (195 messages), **first alert at 14:00, a 1-hour delay**.
- **Interpretation:** at a comparable alarm budget, a fixed threshold cannot see emerging niche problems; rates (not raw counts) make busy days harmless (unit-tested).
- **Limitations:**
  - November exceeds the budget (4.94/day), partly because of genuine incidents (promotion crash, breach disclosure, Black Friday); these cannot be separated from false alarms without labels.
  - Spelling variants (`#krispykreme` vs "krispy kreme") form separate incidents → **improvement:** merge near-duplicate terms.
  - The term-level method does not yet use embeddings (BERTopic comes next and will be compared on the same protocol).

### 5.6 First retrieval results (RQ3 retrieval part, 2026-11-07)
Source: `reports/results/retrieval_helpcenter.json`.

Set: `eval/retrieval_questions.jsonl`, 70 customer-style questions (35 EN + 35 FR, one per Help Center section), written before any comparison.

| Retriever | Recall@1 | Recall@3 | MRR@10 [95% CI] | Median latency |
|---|---|---|---|---|
| BM25 (from scratch) | 0.40 | 0.53 | 0.49 [0.39, 0.59] | 0.05 ms |
| **Dense: paraphrase-multilingual-MiniLM-L12-v2 (ONNX)** | **0.50** | **0.70** | **0.62 [0.52, 0.72]** | 65 ms |
| Hybrid BM25 + dense (RRF, k = 60) | 0.40 | 0.63 | 0.54 [0.44, 0.63] | 72 ms |

- **Dense vs. BM25:** +0.128 MRR, paired bootstrap p = 0.018. **Hybrid vs. BM25:** +0.044, p = 0.06 (not significant).
- **Finding that contradicts our prior assumption:** equal-weight RRF *hurts* when one retriever is much weaker. On customer wording, BM25 adds noise to the dense ranking. **Decision:** dense by default; hybrid kept as an option for exact-match queries (amounts, codes).
- **Protocol caveat:** this set has now been used to *select* the retriever, so it is a **development set**. Final retrieval numbers must come from a **second held-out set written by the team** (planned, together with the reranker and the larger embedding models: Qwen3-Embedding-0.6B, EmbeddingGemma-300M, multilingual-e5-large, bge-reranker-v2-m3).

### 5.7 First automation-gate results (RQ2, 2026-11-07)
Source: `reports/results/gate_complaints2019.json` (code: `src/complaintlens/gate.py`, `ml/scripts/eval_gate.py`).

**Method:** selective risk control, Learn-then-Test (Angelopoulos et al., 2021).
- A fixed grid of 50 confidence thresholds is defined in advance.
- Each threshold gets an exact binomial test of "error among automated > α", with Bonferroni correction.
- The loosest passing threshold is kept. Guarantee: error among automated ≤ α with probability ≥ 1 − δ (δ = 10%).
- Why not fixed-sequence testing: it stops at the first strict threshold, where too few messages are accepted to reject anything (documented in the code).

**Protocol:** complaint vs. not, TF-IDF word+char LR; 10 seeds of 60/20/20 train/calibration/test (duplicates grouped); ≈690 calibration messages.

| Method | Automated (mean, range) | Error among automated (mean / max) | Violations of α |
|---|---|---|---|
| Gate α = 2% | 0% (refused 10/10) | – | 0 |
| Gate α = 5% | 0% (refused 10/10) | – | 0 |
| **Gate α = 10%** | **36.8% (0–52%)** | **3.9% / 6.3%** | **0** (1 refusal) |
| Fixed confidence ≥ 0.8 (no guarantee) | 31.0% | 3.2% / 4.5% | – |
| Fixed confidence ≥ 0.9 (no guarantee) | 8.7% | 2.0% / 5.3% | – |

- **Interpretation:** a guarantee costs evidence. With ≈690 calibration examples and this model, ≤ 5% cannot be *proven*, so the gate refuses (the safe behaviour). At 10% it automates more than the 0.8 rule *and* carries a guarantee. The 0.9 rule exceeded 5% on one seed, which is exactly the risk a guarantee removes.
- **Levers** (to be measured, not tuned on this test):
  - more calibration data (gold sets + silver labels);
  - a more accurate model (fine-tuned encoder);
  - a smaller pre-registered grid (smaller Bonferroni penalty).
- **Report deliverable:** a curve of "automation rate vs. calibration size" at α = 5%.

## 6. The pipeline, stage by stage
Each NLP stage lists the proposed method, the **baseline** it must beat, and the **metric**.

### 6.1 Channels, ingestion and preprocessing
- **Channel adapters → one `Message` schema:**

| Channel | How it reaches us (all free) |
|---|---|
| **Email** `support@<domain>` | Cloudflare Email Routing → Cloudflare Email Worker → our API webhook (instant, no polling). Fallback: a Gmail address polled over IMAP |
| **Website form + live chat** | Next.js site → API |
| **Telegram bot** | Telegram Bot API webhook → API |
| **Ride feedback** (rating + comment after a trip, in the demo rider app) | Website → API |
| *Stretch:* social mentions | Bluesky API (free) |

- **Email-specific cleaning:**
  - Strip quoted earlier messages, signatures and HTML.
  - Keep threads together using `Message-ID` / `In-Reply-To` headers.
  - Attachments are listed, not processed.
- **Preprocessing decisions (each justified):**

| Step | Applied to | Why / why not |
|---|---|---|
| Unicode NFKC, whitespace, emoji kept | all | Emojis carry sentiment ("😡"); encoding noise does not |
| Brand names and @handles → `[COMPANY]` / `[USER]` in training data | D1, D2 | Otherwise models learn the brand, not the complaint, and cannot transfer to LunaGo |
| **No lower-casing, no stop-word removal, accents kept** for transformers | neural models | Casing helps entities; "not" / "ne…pas" flip meaning; "côte" ≠ "cote"; pretrained models need their own tokenizer (spec §4C) |
| Lower-casing + word/char n-grams | TF-IDF baseline only | Standard for linear models; char n-grams absorb typos and French elisions |
| Merge consecutive tweets from the same customer | D1 | Customers split one complaint over several tweets |
| Near-duplicate removal (MinHash, Jaccard ≥ 0.8) before splitting | all | Prevents copy-paste and bot messages from leaking between train and test |

- **PII masking** (before storage and before any external LLM call):
  - Presidio (email, phone, card numbers with Luhn check, addresses) plus GLiNER-PII (names), with typed placeholders.
  - **Metric:** recall per PII type on 200 annotated messages; recall first, because a leak is worse than an over-mask.
  - **Baseline:** regex only.

### 6.2 Language identification
- **Proposed:** `lingua-py` restricted to EN/FR with a confidence threshold. Low confidence or mixed language → `other`/`mixed` → human.
- **Baselines:** fastText `lid.176`.
- **Metric:** accuracy by text length (short texts are the hard case).
- Small on purpose: with two languages this is nearly solved, so we measure it and move on.

### 6.3 Message type + response-required triage ("should we answer?")
- **Proposed:** fine-tuned **mmBERT** (modern multilingual encoder; beats XLM-R on XTREME/XNLI; 8k context), trained on D2 human labels plus D1 silver labels. Calibrated with temperature scaling, and feeding the conformal gate (§6.9).
- **Baselines:**
  - Majority class.
  - TF-IDF + logistic regression (the best model in the original D2 paper, F1 ≈ 77.5, which is a **published reference point**).
  - Zero-shot LLM (the teacher).
- **Metrics:** macro-F1; PR-AUC for `response_required`; ECE (calibration).

### 6.4 Category, severity, risk flags
- **Category:** fine-tuned mmBERT (multi-label: one message can be about a fare *and* a driver).
  - Baselines: TF-IDF + LinearSVC; frozen embeddings + logistic regression; zero-shot LLM.
  - Metrics: macro-F1, per-class F1, top-2 accuracy.
- **Severity:** ordinal classifier on D2 labels.
  - Metrics: macro-F1 and quadratic-weighted κ (confusing level 1 with 4 is worse than 3 with 4).
- **Risk flags:** classifier + lexicon (French and English safety vocabulary).
  - **Recall on `safety` is the critical metric:** a missed safety case is the worst possible error. The decision threshold is set for ≥ 95% recall on validation, and the precision that results is reported.
  - Baseline: lexicon only.
- **Extra:** a **SetFit learning curve** (8 / 16 / 64 labels per class), answering "how many labels does a new company need?".

### 6.5 Entities and customer/trip linking
- **Entities:** **GLiNER** (multilingual zero-shot) with our labels (DATE/TIME, MONEY, LOCATION, TRIP_REF, DRIVER_REF, PAYMENT_REF).
  - Baseline: spaCy + regex.
  - Metric: span F1 on 200 annotated messages.
- **Customer linking:** sender email / Telegram ID → rider record (exact match).
- **Trip linking:**
  - Rank the rider's trips by agreement with the extracted entities (date, amount, place), using a simple, explainable score.
  - Metric: top-1 accuracy on 150 linked test cases.
  - If ambiguous, the reply *asks*: "Was it your trip on 3 Nov at 18:40 from Old Port?"
- **Demo trick:** the first time *any* new email address writes in, the system creates a demo rider profile with a few synthetic recent trips. So the professor can test from their own address and still see verification working.

### 6.6 Representation, similar cases, duplicates, clusters
- **Embeddings:** benchmark Qwen3-Embedding-0.6B, EmbeddingGemma-300M, multilingual-e5 and BGE-M3 on *our* retrieval tests, and pick the best quality per CPU millisecond. Matryoshka truncation to 256 dimensions is used if the measured loss is < 1 point, because it saves free-tier database space.
- **Hybrid search:** BM25 + dense, fused with Reciprocal Rank Fusion, plus a multilingual cross-encoder reranker on the top 50.
  - Metrics: Recall@10, MRR, nDCG@10.
  - Baselines: BM25 alone, dense alone.
- **Duplicates:** threshold tuned on labelled pairs. Customers often send the same complaint by email *and* chat, so duplicates are merged into one ticket.
- **Clusters (problem discovery):** **BERTopic** (UMAP → HDBSCAN → c-TF-IDF) on multilingual embeddings, so French and English complaints about the same problem land together.
  - Baselines: LDA; k-means on TF-IDF.
  - Metrics: NMI/ARI vs. human categories; NPMI coherence; a human word-intrusion test.

### 6.7 Trends, alerts, root cause
- **Detector:** weekly and daily counts per cluster and per category; seasonal Poisson z-score + CUSUM; BERTrend-style weak/strong signal status.
  - Baseline: fixed count threshold.
- **Evaluation:**
  - **(a) Controlled injection:** insert bursts of real complaints of known size into the real D1 background stream. Measure precision, recall and **detection delay**.
  - **(b) Real events in D1:**
    - The **Uber Eats × Krispy Kreme promotion crash (14 Nov 2017)**, already visible in EDA as the busiest day.
    - The **data-breach disclosure (21 Nov 2017)**, a deliberately *weak* signal, to test sensitivity.
    - Other brands' real incidents in the same period (e.g. Apple's iOS 11.1 autocorrect bug), to show the detector is not tuned to one company.
    
    Dates come from public reporting and are checked against the counts.
- **Root cause ("probable cause hypotheses"):** for an alert, test which trip metadata (app version, OS, city zone, vehicle type, payment method, hour, driver) is over-represented versus the baseline period. We use a Fisher exact test with **Benjamini–Hochberg** correction, ranked by lift, plus a grounded summary.
  - **Evaluation:** controlled simulation in D7, where we plant known causes (e.g. "app 5.2 on Android double-charges") and measure whether the method finds them (precision@k).
  - We call them *hypotheses* because correlation is not causation, and say so.

### 6.8 Priority and routing
- `priority = f(risk flags, severity, response_required, emotion intensity, customer impact (amount), cluster growth, waiting time)`. It is a transparent weighted formula, shown as a waterfall chart in the console. Routing rules map category + risk to a team and a deadline (e.g. safety → Safety team, immediate).
- **Validation:** agreement with human priority judgments on 200 tickets (Kendall τ), compared with sorting by recency (baseline) and by sentiment only.

### 6.9 Answering: RAG + tool facts + verifier + gate
This is where RAG is genuinely necessary (§7).

| Situation | Action |
|---|---|
| praise / feedback | short personalised acknowledgement, auto-sent |
| request answerable from the Help Center (e.g. "how do cancellation fees work?") | RAG answer, **auto-sent if the gate allows** |
| billing complaint with a matched trip | RAG + trip facts → draft with a *proposed* action (refund amount computed by policy) → **human approves** (money is never auto-granted) |
| safety / injury / harassment / legal, or severity 4 | **never automatic**: immediate escalation, plus a safe human-written acknowledgement template |
| low confidence anywhere, or verification failed | escalate with the draft attached |
| spam / irrelevant | no reply |

- **Conformal gate:** split conformal prediction on a calibration set guarantees that *among auto-handled messages, the misrouting rate is ≤ α* (e.g. 5%). We report the **automation rate vs. α** curve, which tells a manager "at 5% risk, we automate X% of the volume".

---

## 7. RAG: where it is genuinely needed, and how it is proven

RAG appears in three places only. In each, a model without retrieval fails in a specific, measurable way.

| Use | What fails without it | Sources retrieved | Baselines |
|---|---|---|---|
| **R1. Verified replies** | The LLM invents fees, refund delays, procedures, *and trip facts* | Help Center (D6) + the customer's trip record via **tool calls** (D7) + how similar past tickets were resolved | template reply; LLM without retrieval; RAG without trip facts; RAG without verifier |
| **R2. Ops assistant** ("why did fare complaints rise this week?", "show safety tickets from Plateau zone") | The LLM has no access to company data; aggregate questions need counts, not guesses | hybrid search with metadata filters + aggregation tools | LLM without retrieval; dense-only; no reranker |
| **R3. Cluster and alert explanations** | Keyword lists are unreadable; free summaries can misstate facts | the cluster's representative tickets + root-cause statistics | c-TF-IDF keyword label, rated by humans |

**Design choices, each justified:**
- **Chunking:**
  - Help Center articles are chunked by section, with the article title prepended ("contextual chunk headers"), because a chunk like "within 5 business days" is meaningless without its title.
  - Tickets are short, so one ticket is one document.
- **Retrieval:** hybrid BM25 + dense with RRF, then a cross-encoder rerank of the top 50 down to 5. Cross-lingual by construction: a French complaint retrieves the right English or French article.
- **Generation:**
  - Structured output: `{reply, citations[], facts_used[], proposed_action, confidence}`.
  - Every factual sentence must cite a chunk ID or a trip field.
  - Written in the customer's language and the company's tone (D6 style guide).
- **Verifier (the "verify if needed" step):**
  - The draft is split into atomic claims, and each is checked against its cited source (NLI model, with an LLM judge as a comparison).
  - If any claim is unsupported, the draft is **blocked** and sent to a human, with the failing claim highlighted.
  - **Metric:** how many planted wrong claims it catches (recall), and how often it blocks correct drafts (false-alarm rate).
- **Abstention:** if retrieval finds no relevant policy, the system says so and routes to a human; it never improvises.
- **Evaluation** (spec §4F requires factual correctness, faithfulness, reliability across runs, metric limitations):
  - Retrieval: Recall@k, MRR, nDCG@10 on 150 held-out questions with gold articles (written before tuning).
  - Generation: claim-level **faithfulness**, citation precision and recall, fact correctness against the trip DB, policy-violation rate, correct language.
  - **Blind human evaluation:** for real D1 complaints, raters see two anonymised replies, *ours* and the **real Uber agent's reply**, and judge them on empathy, clarity and actionability, without knowing which is which. Both team members plus 3–5 volunteers rate them; we report κ.
  - **LLM-as-judge** with one narrow rubric per criterion, **validated against the human ratings** (κ / Spearman). Judge model pinned, date recorded.
  - Reliability: 3 runs per item; variance reported.
  - Cost and latency per reply.

---

## 8. Research questions and experimental protocol (C4 / C5)

| RQ | Question | Primary metric | Must beat |
|---|---|---|---|
| **RQ1** | Can a small fine-tuned multilingual encoder, distilled from LLM silver labels plus human labels, **match or beat its LLM teacher and classical baselines** for triage and categorization, and how well does it **transfer to French**? | macro-F1 on Gold-EN and Gold-FR; cost and latency per message | TF-IDF + LR/SVM; zero-shot LLM; published D2 result |
| **RQ2** | Can the reply decision be automated with a **guaranteed error bound**, and what automation rate does that allow? | automation rate at α = 5%; empirical coverage | fixed softmax threshold |
| **RQ3** | Do RAG + verified trip facts + a claim verifier produce **more faithful and more useful replies** than simpler variants, and how do they compare with **real human agent replies**? | faithfulness; blind human preference | no-RAG; RAG without facts; RAG without verifier |
| **RQ4** | Does embedding clustering + statistical burst detection **detect emerging issues earlier** than count thresholds? | detection delay; precision/recall | count threshold; LDA |
| **RQ5** *(extended)* | Does the metadata over-representation test recover **planted root causes**? | precision@k | random / most-frequent value |

**Protocol rules (spec §10):**
- **Split by conversation and by time.**
  - Train on the earlier weeks of D1, validate on the middle weeks, test on the last weeks.
  - No conversation is split across sets, because tweets from one thread would leak.
  - Gold sets are sampled from the **test period only**.
- **Near-duplicates removed across splits** before splitting.
- **All fitted transformations** (TF-IDF vocabulary, label encoders, UMAP, calibration) fit on train only (scikit-learn `Pipeline`). Calibration and conformal sets are separate from train.
- **The test set is used once**, at the end. All model and prompt selection happens on validation.
- **5 seeds** for every neural run. Report mean ± std, **bootstrap 95% CI**, and paired significance tests (Dror et al. 2018). Differences inside run-to-run noise are **not** called improvements.
- **Ablations:**
  - Without brand masking (shows shortcut learning).
  - Without dedup (shows leakage inflation).
  - Silver-only vs. silver + human labels.
  - Without reranker / hybrid retrieval.
  - Without trip facts / without verifier.
  - Embedding 768 vs. 256 dimensions.
  - INT8 vs. FP32 (accuracy and latency).
- **Error analysis:**
  - 100 sampled errors per main task.
  - Categories: sarcasm, multi-issue message, too short or context in an earlier tweet, label ambiguity, translationese, brand-specific jargon, out-of-domain.
  - Examples and plausible causes for each; frequency tables, not just a confusion matrix.

---

## 9. Architecture and tech stack (free, fast, production-grade)

```
 CUSTOMER SIDE (LunaGo)                          COMPANY SIDE (ComplaintLens)
 ┌──────────────────────────┐                      ┌───────────────────────────────────────────┐
 │ Website: Help Center,    │──┐                   │ FastAPI  ─►  Postgres job queue  ─► Worker │
 │ complaint form, chat,    │  │   HTTPS           │                                   pipeline│
 │ demo rider app           │  ├──────────────────►│  1 normalize + PII mask   6 embed/similar  │
 ├──────────────────────────┤  │                   │  2 language               7 cluster/trends │
 │ Email support@domain     │──┤ Cloudflare Email  │  3 type/needs-reply       8 route/priority │
 │  (Cloudflare Worker)     │  │ Worker → webhook  │  4 category/severity/risk 9 RAG + trip     │
 ├──────────────────────────┤  │                   │  5 entities + link trip     facts + verify │
 │ Telegram bot             │──┘                   │                          10 gate → send   │
 └──────────────────────────┘                      └──────────────┬────────────────────────────┘
          ▲  replies on the same channel (Resend email, Telegram, chat)  │
          └────────────────────────────────────────────────────────────────┘
                                   Postgres + pgvector (tickets, vectors, trips, audit log)
                                                  ▲
                         Live console (Next.js): Inbox · Ticket X-ray · Topics · Trends · Experiments
```

| Layer | Choice | Why (vs. alternatives) |
|---|---|---|
| Language / packages | **Python 3.12** with **uv** (already installed on your PC) | Most reliable for ML wheels; lockfile = exact reproducibility (spec §4H) |
| Training | PyTorch + Transformers + Sentence-Transformers + SetFit; scikit-learn baselines | Standard, documented in the spec's references |
| GPU | Your **RTX 5060 Ti 8 GB** (needs the CUDA 12.8+ PyTorch build for Blackwell); Kaggle free GPUs as backup | mmBERT-base fine-tuning fits in 8 GB with bf16 + gradient accumulation |
| Tracking | **MLflow** (local) + exported `results/*.json` | Every number traces to run, config, seed and commit |
| Inference | **ONNX Runtime**, INT8 quantization | 2–4× faster on CPU; the accuracy cost is measured |
| API | **FastAPI** + Pydantic v2 | Async, typed; auto OpenAPI → typed frontend client |
| Jobs | **Postgres-based queue** (`SELECT … FOR UPDATE SKIP LOCKED`) | Durable and retryable with no extra service (no Redis to host) |
| Live updates | **Server-Sent Events** | The console updates the moment a stage finishes |
| Database | **Postgres + pgvector** (HNSW, `halfvec`) | One store for tickets, trips, vectors and full-text search; SQL for analytics |
| LLM | **Open-weights model** through the **Groq free tier**; the same model family locally via **Ollama** as a fallback | Free and fast; open weights → reproducible; model ID and date pinned |
| Frontend | **Next.js 16** + TypeScript strict + Tailwind v4 + **shadcn/ui** + TanStack Query/Table + **ECharts** + WebGL scatter for the topic map + **next-intl** (EN/FR) | Best-in-class React stack; fully bilingual interface |
| Email in / out | **Cloudflare Email Routing + Email Worker** (inbound, free, unlimited) / **Resend** (outbound, free: ~3,000/month, 100/day) | Real `support@` address on our own domain; replies thread correctly in the professor's mailbox |
| Chat | **Telegram Bot API** (free) | A second real channel in two minutes of setup |
| Annotation | **Argilla** on a free HF Space | Both members annotate online; κ computed automatically |
| Quality | ruff, pyright, pytest, Playwright, pre-commit, GitHub Actions | A green CI badge is visible proof of engineering quality |
| Report | LaTeX, ACL template (Overleaf, free) | Looks like a real NLP paper |

### 9.1 Free hosting map

| Piece | Free host | Notes |
|---|---|---|
| Domain | **GitHub Student Developer Pack** (free 1st year: Namecheap `.me`, get.tech `.tech`, Name.com) | Needs student verification; renewal after a year is paid, which doesn't matter for the defence |
| DNS + email inbound | **Cloudflare** (free) | Email Routing is on the free plan |
| Email outbound | **Resend** free tier | 100/day is plenty for the demo |
| Website + console | **Vercel Hobby** | Auto-deploys from GitHub |
| API + models + worker | **Hugging Face Spaces** (Docker, CPU Basic 2 vCPU / 16 GB) | Kept awake by a scheduled ping. Fallback: Oracle Cloud Always Free VM (4 ARM cores / 24 GB) or Student Pack credits |
| Database | **Neon** free Postgres + pgvector | ~100 compute-hours/month and 0.5–1 GB, enough for the demo |
| LLM | **Groq** free tier | Rate-limited; replies cached; local Ollama fallback |
| Models and datasets | **Hugging Face Hub** | Model cards and datasheets (both cited in the spec's references) |

### 9.2 Performance budget (measured and displayed in the console)

| Stage | Target p95 (2 vCPU) |
|---|---|
| Normalize + PII + language | < 60 ms |
| All classifier heads (INT8 ONNX) | < 400 ms |
| Embedding + hybrid search + rerank | < 500 ms |
| Understanding + routing total | **< 1.5 s** |
| Reply: retrieval + generation + verification | < 6 s (streamed) |
| Email round-trip (send → reply in inbox) | < 30 s |

---

## 10. What the professor sees: the demo

### 10.1 The two websites
- **LunaGo (public):** landing page, Help Center (EN/FR), "Contact support" form, live chat bubble, ticket-tracking page, and a demo rider account showing recent trips.
- **ComplaintLens console (staff):**
  1. **Live:** new messages appear in real time, with each stage lighting up as it completes.
  2. **Inbox:** priority-sorted queue with team filters.
  3. **Ticket X-ray:**
     - The original message with highlighted entities and masked PII.
     - Each decision with its confidence and a *why*.
     - The linked trip.
     - Similar tickets.
     - The draft with **clickable citations** and the **verifier's claim-by-claim check**.
     - The gate decision.
     - An approve / edit / send button.
     - Full timing per stage.
  4. **Topics:** an interactive map of all complaints by cluster (EN and FR mixed).
  5. **Trends and alerts:** time series, anomaly markers, root-cause panel.
  6. **Ask:** the ops assistant (R2), with cited ticket IDs.
  7. **Replay:** stream a real historical period (the week of 14 Nov 2017) and watch the "promotion crash" alert fire, with *doughnuts / crashed / promotion* as its explanation.
  8. **Experiments:** every table and figure in the report, linked to config, seed and commit, plus an **error browser**.

### 10.2 Script for the 5-minute live demo
1. The professor emails `support@…` from their own phone: *"J'ai été facturé deux fois pour ma course d'hier soir !"* ("I was charged twice for my ride last night!")
2. On the projector, the console's Live view runs the 10 stages:
   - French, complaint, needs a reply, Billing, severity 2;
   - trip found;
   - double charge confirmed in the trip record;
   - draft with citations, verifier ✔.
   
   The gate holds it for approval (money is involved), we click approve, and the professor's phone receives the reply in French with a ticket number.
3. The professor writes in the chat: *"The driver was driving dangerously and I felt unsafe"*. It is instantly escalated to Safety, with no automatic reply beyond the safe acknowledgement. This shows the system knows when **not** to automate.
4. Open Trends: replay 14 Nov 2017; the alert fires within hours; the explanation reads "free-doughnut promotion → app crashes on food orders".
5. Open Experiments: "every number in our report is here, with the run that produced it."

### 10.3 Defence safety net
- A warm-up call 10 minutes before the defence.
- LLM outputs cached for scripted inputs.
- Gmail fallback if the domain email fails.
- The whole stack runs **locally** with one command (Docker Compose) if the Wi-Fi fails.
- A recorded backup video, used only if the professor authorises it (spec §6).

---

## 11. Repository layout and engineering standards

```
complaintlens/
├─ apps/
│  ├─ api/               FastAPI: ingestion webhooks, ticket API, SSE, auth
│  ├─ web/               Next.js: LunaGo public site + ComplaintLens console
│  └─ email-worker/      Cloudflare Email Worker (TypeScript, ~50 lines)
├─ src/complaintlens/    the NLP library, one module per stage
│  ├─ channels/ preprocess/ pii/ langid/ classify/ extract/ link/
│  ├─ embed/ search/ cluster/ trends/ rootcause/ priority/ rag/ verify/ gate/
│  └─ schemas.py         Message, Ticket (single source of truth)
├─ ml/
│  ├─ configs/           one YAML per experiment (seed, model, hyperparameters, prompt)
│  ├─ scripts/           prepare_data, label_silver, train, evaluate, export_onnx
│  └─ notebooks/         EDA only
├─ eval/                 annotation guidelines, gold sets, metrics, significance tests
├─ company/              LunaGo Help Center (EN/FR), synthetic-DB generator, style guide
├─ reports/              LaTeX report, slides, figures/, results/*.json
├─ infra/                Dockerfiles, docker-compose, deploy workflows
└─ tests/                unit, integration, end-to-end
```

**Rules:**
- No number in the report without a results file.
- No notebook-only logic.
- Every module has tests.
- Every model has a card.
- Reused code is attributed (spec §11).
- The AI-use disclosure is kept current (spec §9).

---

## 12. Scope tiers (anti-pitfall: "define a minimal viable version first")

| Tier | Content |
|---|---|
| **Core** (must ship, fully evaluated) | Email + web form + chat channels; preprocessing + PII; language ID; triage; category; severity + risk; entities + trip linking; similar/duplicates; clustering; trends; priority + routing; RAG replies with trip facts + verifier + conformal gate; console (Live, Inbox, Ticket X-ray, Topics, Trends, Experiments); free deployment; RQ1–RQ4 |
| **Extended** | Telegram bot; ops assistant (R2); root cause + RQ5; Replay; INT8 + multi-task ablations; SetFit learning curve |
| **Stretch** | Emotion; Bluesky channel; voice messages (Whisper); active learning from agent edits |

If time runs short, we cut Stretch first, then Extended. Core is never cut.

---

## 13. Timeline and team split

The defence date is not announced yet ("final teaching week before the vacation"). The plan assumes **~7 weeks** and compresses if needed.

| Week | Spec milestone | Work |
|---|---|---|
| W0 (now) | M1 proposal | Submit proposal; repo, CI, environment; download D1; EDA; annotation guidelines v1; claim the free domain |
| W1 | M2 validation + M3 data | Gold pilot + κ; splits + dedup; **all baselines running** (spec §13: "implement the baseline early"); silver labelling |
| W2 | M4 pipeline | Fine-tune encoders; PII + language ID; API + DB + job queue; email in/out end-to-end ("hello world" ticket) |
| W3 | M4 | Embeddings benchmark → hybrid search → clustering → trends + injection benchmark; Help Center + synthetic DB |
| W4 | M4 | RAG + trip tools + verifier + gate; console core pages; chat channel |
| W5 | M5 experiments | 5-seed runs, CIs, significance, ablations; blind human evaluation; error analysis; full online deployment |
| W6 | M5/M6 | Report (8–15 pages), slides, model cards and datasheets; README tested on a clean machine |
| W7 | M7 defence | Demo rehearsal ×3; each member questions the other on the *other's* modules |

**Equitable split** (both annotate; both review every pull request, so each can defend everything, spec §5.1):
- **Aziz:** classification models and distillation, conformal gate, ONNX serving, API + job queue + channels (email, chat), deployment, trend detection.
- **Rimel:** data pipeline + EDA + datasheets, PII and language ID, embeddings/search/clustering, Help Center + RAG + verifier and their evaluation, console frontend.
- **Shared:** annotation, error analysis, report, slides.

Each person owns at least one research question end to end.

---

## 14. Ethics (spec §4I)
- **No impersonation:** LunaGo is fictional and labelled as a student project on every page and email. Real brand names are masked in training data.
- **Privacy:**
  - PII is masked before storage and before any external API call.
  - D1 handles are already anonymised by the dataset authors, and we mask names in text as well.
  - Demo users' data is deleted after the defence.
- **Automation harm:** money is never auto-granted; safety, injury and legal cases are never automated; the error bound is statistical and disclosed.
- **Bias:** performance compared across EN/FR, native vs. translated French, short vs. long texts, and informal writing. Non-native or informal writers must not be deprioritised.
- **Misuse:** the risk of using triage to *ignore* complaints is discussed. The design surfaces severe cases first.
- **Licences:** D1 is CC BY-NC-SA → our derived data inherits CC BY-NC-SA and stays non-commercial; D3 is CC BY-NC.

---

## 15. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Student Pack domain not available in time | Gmail address (IMAP in / SMTP out), with the same pipeline |
| Hugging Face free CPU quota denied | Oracle Always Free VM, or Student Pack credits; local Docker as the last resort |
| Groq limits hit during the demo | Cached outputs + local Ollama |
| Slow internet | One-time downloads, resumable (`curl -C -`); models cached locally |
| French gold set small | Report confidence intervals honestly; keep native and translated French separate |
| Not enough time | Cut Stretch, then Extended |

---

## 16. Decisions still needed from you
1. **Defence date** and **proposal deadline**.
2. **Team:** just the two of you? (The spec allows 1–3.)
3. **Company name:** decided: **LunaGo**, one app for rides and food delivery (no separate "Eats" brand). A web search on 2026-11-07 found no ride or delivery company with this name.
4. **Student verification:** does your school email qualify for the GitHub Student Developer Pack? It gives us the free domain.
5. **Kaggle account:** create one (free) for the D1 download.

---

## 17. Sources consulted (2026-11-07)
- Professor's specification v1.0 (10 Oct 2026).
- *Customer Support on Twitter* (Kaggle `thoughtvector`); Hardalov et al., *Towards Automated Customer Support*, [arXiv:1809.00303](https://arxiv.org/pdf/1809.00303); HF copies: [TNE-AI](https://huggingface.co/datasets/TNE-AI/customer-support-on-twitter-conversation), [MohammadOthman](https://huggingface.co/datasets/MohammadOthman/mo-customer-support-tweets-945k), [Rakuto](https://huggingface.co/datasets/Rakuto/twitter_customer_support_dialogue/blob/main/README.md).
- Preoțiuc-Pietro et al., [ACL 2019](https://aclanthology.org/P19-1495/), [data](https://www.github.com/danielpreotiuc/complaints-social-media); Jin & Aletras, [NAACL 2021](https://arxiv.org/pdf/2103.12428.pdf).
- Bueck tickets, [HF](https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets); [arXiv:2603.27355](https://arxiv.org/pdf/2603.27355).
- CFPB (evaluated, set aside): live API (CC0, 18,996,256 records) and [narratives archive](https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/).
- mmBERT, [arXiv:2509.06888](https://arxiv.org/pdf/2509.06888), [blog](https://huggingface.co/blog/mmbert); MrBERT, [arXiv:2602.21379](https://arxiv.org/pdf/2602.21379).
- Qwen3 Embedding, [arXiv:2506.05176](https://arxiv.org/pdf/2506.05176); MMTEB, [arXiv:2502.13595](https://arxiv.org/html/2502.13595v3).
- GLiNER, [PyPI](https://pypi.org/project/GLiNER/); GLiNER2-PII, [overview](https://pioneer.ai/research/gliner2-pii-a-multilingual-model-for-personally-identifiable-information-extraction).
- BERTrend, [arXiv:2411.05930](https://arxiv.org/pdf/2411.05930); FineWeb2 LID comparison, [arXiv:2506.20920](https://arxiv.org/pdf/2506.20920).
- Conformal prediction and human decisions, [arXiv:2401.13744](https://arxiv.org/html/2401.13744v1); cost-sensitive conformal abstention, [arXiv:2607.27143](https://arxiv.org/pdf/2607.27143).
- Free services:
  - [Cloudflare Email Service pricing](https://developers.cloudflare.com/email-service/platform/pricing/);
  - [Email Workers announcement](https://blog.cloudflare.com/announcing-route-to-workers);
  - [Resend free tier](https://automationatlas.io/answers/resend-free-tier-explained-2026/);
  - [GitHub Student Pack domains (Name.com)](https://www.name.com/support/articles/360036364834-signing-up-for-github-student-developer-pack);
  - [Neon free plan](https://neon.com/faqs/free-plan-limits-and-quotas);
  - [Groq free tier](https://eesel.ai/blog/groq-pricing);
  - [HF Spaces quota reports](https://discuss.huggingface.co/t/question-about-the-cpu-basic-quota-limit/176628).
- Kaggle/HF search for French complaint data: none with a clear licence (e.g. [avis-clients](https://huggingface.co/datasets/BenGaia/avis-clients/commit/a2d07eefc49032eb7f9b30b3a7af304d1c845e5f)).

Items marked *verify* are checked in week 1, before any claim enters the report.
