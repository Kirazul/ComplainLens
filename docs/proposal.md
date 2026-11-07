# Project Proposal: NLP Semester Project 2026–2027

**Team members:** Mohamed Aziz Mansour · Rimel Zouari
**Provisional title:** *ComplaintLens: Multilingual Complaint Understanding, Routing and Verified Response, with Guaranteed-Risk Automation*

### 1. Problem statement
Support teams receive customer messages through many channels (email, forms, chat, social media) and in more than one language. For each one, an agent must decide:
- Is it a real complaint, or just a comment?
- Does it need an answer, and how urgently?
- What is it about, and which team handles it?
- Is it dangerous (safety, legal)?
- What is the correct, policy-compliant reply?

Done by hand, this is slow, inconsistent and risky, and recurring problems are noticed late.

**Input → output.** One message (text, channel, sender, thread) →
- language (EN/FR);
- message type (complaint / request / feedback / praise / spam) and *response required*;
- category;
- expressed severity (4 levels) and risk flags;
- entities linked to the customer's record;
- similar and duplicate tickets, and the recurring-problem cluster;
- an explainable priority and a routing destination;
- a reply grounded in company policy and **verified customer-record facts**, with an automation decision (auto-send / human approval / escalation).

At corpus level: emerging-issue alerts with probable-cause hypotheses.

**Use case.** A ride-hailing and food-delivery support desk. For a live demonstration, the system runs as the support desk of a **fictional** bilingual company ("LunaGo", one app for rides and food delivery), with a real website, email address and chat bot, so that anyone can send a complaint and watch it being processed end to end. Out-of-scope inputs, and all safety and legal cases, go to a human.

### 2. Objectives (measurable)
1. **Understanding:** a fine-tuned multilingual encoder, distilled from LLM silver labels plus human labels, matches or beats its LLM teacher and a TF-IDF baseline in macro-F1 on our human-annotated test set (5 seeds, 95% bootstrap CI), at a fraction of the cost. Zero-shot transfer to French is measured.
2. **Safe automation:** split conformal prediction auto-handles messages with misrouting ≤ 5%. We report the automation rate this allows.
3. **Verified replies:** RAG with customer-record facts and a claim verifier is more faithful (claim-level faithfulness, citation precision) than no-retrieval and partial variants. It is rated blind against **real human agent replies**.
4. **Emerging issues:** clustering + burst detection detects injected and real bursts earlier than a count threshold (detection delay, precision/recall).

### 3. Data (all downloaded and profiled)
- **Customer Support on Twitter** (Kaggle; CC BY-NC-SA 4.0): 2.8M real customer/company tweets from 108 brands, with timestamps and real agent replies.
  - Includes **41,855 Uber customer conversations** (Oct–Dec 2017; median 22 words; ~49% rides, ~16% food delivery).
  - Also Lyft, used as a generalisation test.
  - Contains a real incident: an app crash during a free-doughnut promotion (14 Nov 2017).
- **Complaints on Twitter** (Preoțiuc-Pietro et al., ACL 2019) with **severity labels** (Jin & Aletras, NAACL 2021): 3,449 expert-labelled tweets; a published reference point.
- **Our gold sets:** ~1,000 English and 400–600 French messages (native and post-edited translations, kept separate), double-annotated with Cohen's κ, test-only. No licensed French complaint dataset exists on Kaggle or Hugging Face.
- **Fictional company content:** Help Center articles and a synthetic trip database, used only to ground and verify demo replies, and labelled as fictional.

### 4. Candidate methodology
- **Preprocessing (each step justified):**
  - no lower-casing, stop-word removal or accent stripping for transformers;
  - brand names masked, so models learn the complaint and not the brand;
  - multi-tweet messages merged;
  - PII masked (Presidio + GLiNER);
  - near-duplicates removed before splitting.
- **Understanding:** fine-tuned multilingual encoders (mmBERT vs. XLM-R); calibration + conformal gate; GLiNER entities; explainable record linking.
- **Discovery:** benchmark of multilingual embeddings; hybrid BM25 + dense retrieval with reciprocal-rank fusion and reranking; BERTopic; Poisson/CUSUM burst detection; Fisher tests with Benjamini–Hochberg correction for probable causes.
- **Generation:** RAG over the Help Center plus record look-ups; mandatory citations; an NLI claim verifier that blocks unsupported drafts; open-weights LLM with a pinned version.
- **Rationale:** encoders are cheaper and more accurate than LLMs for fixed labels. LLMs only generate text, and only with retrieval and verification, because without them they invent policies and facts.

### 5. Evaluation strategy
- **Baselines:** majority class; TF-IDF + linear models; zero-shot LLM; the published 2019 result; LDA / k-means; count threshold; no-RAG / no-facts / no-verifier variants; recency ordering.
- **Metrics:** macro-F1, ECE, quadratic κ, safety-flag recall, span F1, PII recall, Recall@k / MRR / nDCG, NMI and coherence, detection delay, faithfulness, citation precision, blind human ratings with κ.
- **Protocol:**
  - split by conversation and time; dedup across splits;
  - train-only fitting; test set used once;
  - 5 seeds, bootstrap CIs, paired significance tests;
  - ablations: brand masking, dedup, label source, reranker, facts, verifier, quantization;
  - error analysis of 100 errors per task, grouped into categories.

### 6. Feasibility and scope
- **Compute and hosting:** local RTX 5060 Ti (8 GB), Kaggle GPUs as backup. Free hosting: Vercel, Hugging Face Spaces, Neon Postgres, Cloudflare Email Routing + Resend, Telegram, Groq.
- **Scope tiers:**
  - **Core:** email + form + chat, objectives 1–4, console, deployment.
  - **Extended:** ops assistant, probable causes, replay.
  - **Stretch:** emotion, voice.
- **Fallbacks:** local deployment with cached outputs; Gmail instead of the domain email; honest confidence intervals for the small French set.

### 7. Ethics and licensing
- **No impersonation:** the demo company is fictional and labelled as a student project.
- **Personal data:** masked before storage and before any external API call; demo data deleted afterwards.
- **Licences:** non-commercial and share-alike terms respected.
- **Automation limits:** money is never granted automatically; safety, injury and legal cases always reach a human.
- **Bias:** performance compared across languages and writing styles.
- **Misuse:** suppressing complaints is discussed as a misuse risk.
- **AI-use disclosure:** included in the report.

### 8. Planned task allocation
- **Aziz:** classification and distillation, conformal gate, serving, API and channels, deployment, trend detection.
- **Rimel:** data pipeline and EDA, PII and language ID, embeddings, search and clustering, Help Center, RAG and verifier evaluation, web interface.
- **Both:** annotation, error analysis, report, slides. Each member reviews all code and can defend every component.
