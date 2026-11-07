# ComplaintLens: Annotation Guidelines (v1)

These rules are used by **both human annotators** (gold sets D4/D5) **and** the LLM that produces silver labels, so the two can be compared fairly.

**Unit of annotation:** one *first contact*: everything the customer wrote before the company's first reply (consecutive tweets, or one email or chat message). Earlier context is shown when available, but you label the customer's message.

Pilot: 50 items, both annotators independently. Then compute Cohen's κ per field, discuss disagreements, and update this file (v2) before the full set. Every rule added after the pilot is marked *(v2)*.

---

## Field 1: `message_type` (exactly one)

| Label | Definition | Examples |
|---|---|---|
| `complaint` | The customer expresses that **reality breached their expectations**, and the company or its service is responsible. Includes reports of problems, even when written calmly. | "I was charged twice for one ride." · "Driver cancelled 3 times, still waiting." |
| `request` | Asks for information or an action **without** expressing a breach of expectations. | "How do I add a second card?" · "Can I book a ride for my mom?" |
| `feedback` | A suggestion or opinion about improving the service, with no specific failed experience. | "You should let us tip in cash." |
| `praise` | Thanks or compliments. | "Driver was super kind, thanks!" |
| `spam_or_irrelevant` | Not addressed to customer service, an advertisement, gibberish, or a conversation with someone else. | "Follow me for crypto tips" · "lol same" |

**Decision rules:**
1. **Complaint beats request.** "I was charged twice, can you refund me?" is a `complaint`: the request exists *because of* the breach. (This is the definition of Preoțiuc-Pietro et al., 2019, so D2 labels stay compatible.)
2. **Sarcasm counts as what is meant.** "Great, 40 minutes waiting, love it 🙃" is a `complaint`.
3. **Praise with a complaint is a complaint.** "Driver was nice but the app charged me twice" → `complaint`.
4. A **question that implies a failure** is a complaint. "Why did my fare double?" → `complaint` (the customer reports an unexpected charge).

## Field 2: `response_required` (yes / no) + `urgency`

**yes** if a competent agent would need to answer or act: a question, a problem to solve, a request for refund or contact, a safety issue. **no** for pure venting with nothing to act on, praise that needs no answer, and spam.

- "worst app ever" alone → **no** (nothing actionable; an agent *may* reply, but nothing is required).
- "worst app ever, it charged me twice" → **yes**.

`urgency` (only if yes):
- `immediate`: safety, injury, harassment, a person stranded (e.g. a child or elderly person alone), an account being hijacked right now.
- `24h`: money lost, a lost item, or a service blocked (cannot ride or log in).
- `standard`: everything else.

## Field 3: `category` (one or more; the first one listed is the main one)

| Category | Covers |
|---|---|
| `fare_billing` | surge, double charge, wrong amount, route-based overcharge, cancellation fee, refund delay, receipts |
| `driver_behaviour` | rudeness, wrong route on purpose, refused trip, unprofessional conduct (not safety-critical) |
| `safety_incident` | dangerous driving, assault, harassment, threats, impaired driver, accident, feeling unsafe |
| `lost_item` | items left in a vehicle |
| `cancellation_no_show` | driver or rider cancellations, no-shows, long waits, no cars available |
| `delivery_order` | food-delivery orders: late, missing or wrong items, cold food, order given to someone else, courier behaviour, restaurant problems |
| `app_technical` | crashes, bugs, GPS/map errors, payment-screen failures, updates |
| `account_access` | login, verification, hacked or locked accounts, deactivation |
| `promotions_credits` | promo codes, referral credits, gift cards, subscriptions |
| `accessibility` | wheelchair, service animals, assistance needs, discrimination tied to a disability |
| `other` | none of the above (e.g. brand-level opinions, news, company politics) |

**Rules:**
- When safety is involved, `safety_incident` is **always** first, even if fare is also mentioned.
- Discrimination or refusal because of a service animal or disability → `accessibility` **and** the `harassment_discrimination` risk flag.

## Field 4: `severity` (complaints only; 1–4, following Jin & Aletras 2021, Trosborg 1995)

| Level | Name | The customer… | Example |
|---|---|---|---|
| 1 | No explicit reproach | reports the problem without blaming anyone | "My receipt shows two charges." |
| 2 | Disapproval | expresses negative feelings or dissatisfaction, without accusing | "Really disappointed, waited 30 min." |
| 3 | Accusation | states or implies the company did something wrong | "You charged me twice on purpose." |
| 4 | Blame | holds the company responsible, often with insults, threats or demands | "You are thieves. I'm reporting you and deleting the app." |

Severity measures **how the complaint is expressed**, not how dangerous the situation is (that is Field 5). A calm report of an assault can be severity 1 with the `safety` risk flag.

## Field 5: `risk_flags` (zero or more)
`safety` · `injury` · `harassment_discrimination` · `legal_threat` (lawyer, court, regulator, police report about the company) · `fraud_account_takeover` · `media_threat` (going to the press or "going viral") · `vulnerable_person` (child, elderly, disabled person or someone in distress involved).

**Rule:** if unsure whether `safety` applies, **flag it**. A false alarm costs an agent a minute; a miss can cost much more.

## Field 6: entities (span annotation)
Mark exact character spans: `DATE_TIME`, `MONEY`, `LOCATION`, `TRIP_REF` (trip ID or a unique trip description), `DRIVER_REF` (driver name or plate), `PAYMENT_REF` (card digits, payment method). Do not mark the company itself.

---

## Borderline cases log
Disagreements found during the pilot are added here, each with the final decision and the reason, so that both annotators and the silver-labelling prompt converge.

| # | Message (short) | Disagreement | Decision and reason |
|---|---|---|---|
| | | | |
