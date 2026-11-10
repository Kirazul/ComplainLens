"use client";

import { useCallback, useEffect, useState, type KeyboardEvent } from "react";

import { useSession } from "@/components/console/shell";
import { humanize } from "@/components/console/status";
import { api, type Agreement, type AnnotationItem, type AnnotationProgress, type GoldLabels } from "@/lib/api";

// Field values mirror eval/annotation_guidelines.md (and the backend's Labels model).
const TYPES = ["complaint", "request", "feedback", "praise", "spam_or_irrelevant"];
const URGENCY = ["immediate", "24h", "standard"];
const CATEGORIES = [
  "fare_billing", "driver_behaviour", "safety_incident", "lost_item", "cancellation_no_show",
  "delivery_order", "app_technical", "account_access", "promotions_credits", "accessibility", "other",
];
const RISKS = [
  "safety", "injury", "harassment_discrimination", "legal_threat", "fraud_account_takeover",
  "media_threat", "vulnerable_person",
];
const SETS = [
  ["pilot", "Pilot (both annotators)"],
  ["gold_en", "English gold"],
  ["gold_fr", "French gold"],
] as const;

const EMPTY: GoldLabels = {
  message_type: "", response_required: true, urgency: null, categories: [], severity: null, risk_flags: [],
};

function problems(l: GoldLabels): string[] {
  const out = [];
  if (!l.message_type) out.push("choose a message type");
  if (l.categories.length === 0) out.push("choose at least one category");
  if (l.message_type === "complaint" && l.severity === null) out.push("choose a severity");
  if (l.response_required && !l.urgency) out.push("choose an urgency");
  return out;
}

function Choice({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full px-3 py-1 text-sm ring-1 ${active ? "bg-ink text-white ring-ink" : "bg-white ring-line hover:ring-ink"}`}
    >
      {label}
    </button>
  );
}

export default function AnnotatePage() {
  const annotator = useSession()?.user.username ?? "";
  const [setName, setSetName] = useState("pilot");
  const [item, setItem] = useState<AnnotationItem | null | undefined>(undefined);
  const [progress, setProgress] = useState<AnnotationProgress | null>(null);
  const [labels, setLabels] = useState<GoldLabels>(EMPTY);
  const [agreement, setAgreement] = useState<Agreement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frText, setFrText] = useState("");
  const [version, setVersion] = useState(0);
  const explain = (e: unknown) => (e as Error).message;

  useEffect(() => {
    if (!annotator) return;
    let active = true;
    api
      .annotateNext(setName)
      .then((r) => {
        if (!active) return;
        setItem(r.item);
        setProgress(r.progress);
        setLabels(EMPTY);
        setError(null);
      })
      .catch((e: Error) => active && setError(e.message));
    api.agreement(setName === "gold_fr" ? "gold_fr" : setName).then((a) => active && setAgreement(a)).catch(() => undefined);
    return () => {
      active = false;
    };
  }, [annotator, setName, version]);

  const save = useCallback(async () => {
    if (!item || problems(labels).length) return;
    try {
      await api.annotateSave(item.id, {
        ...labels,
        urgency: labels.response_required ? labels.urgency : null,
        severity: labels.message_type === "complaint" ? labels.severity : null,
      });
      setVersion((v) => v + 1);
    } catch (e) {
      setError(explain(e));
    }
  }, [item, labels]);

  function onKey(e: KeyboardEvent) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save();
  }

  const toggle = (list: string[], value: string, max = 99) =>
    list.includes(value) ? list.filter((v) => v !== value) : list.length < max ? [...list, value] : list;

  const left = problems(labels);
  const done = progress?.labelled[setName]?.[annotator] ?? 0;
  const total = progress?.items[setName] ?? 0;

  return (
    <main className="mx-auto max-w-7xl px-5 py-8" onKeyDown={onKey}>
      <div className="flex flex-wrap items-end gap-4">
        <h1 className="mr-auto text-2xl font-semibold">Annotate</h1>
        <label className="text-sm">
          <span className="block text-muted">Set</span>
          <select value={setName} onChange={(e) => setSetName(e.target.value)} className="mt-1 rounded-lg border border-line px-3 py-1.5">
            {SETS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
      <p className="mt-2 text-sm text-muted">
        Label each message by the guidelines (eval/annotation_guidelines.md).
        {total > 0 && ` You have done ${done} of ${total}.`}
      </p>
      {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 px-4 py-2 text-escalated">{error}</p>}

      <div className="mt-6 grid gap-8 lg:grid-cols-[1fr_22rem]">
        <section aria-label="Message to label">
          {item === null ? (
            <p className="rounded-xl border border-dashed border-line bg-white p-8 text-muted">
              Nothing left for you in this set. Thank you.
            </p>
          ) : item ? (
            <div className="space-y-5">
              <blockquote className="rounded-xl border border-line bg-white p-5 text-lg leading-relaxed">
                {item.text}
                <footer className="mt-2 text-xs text-muted">{item.id} · {item.lang}</footer>
              </blockquote>

              <fieldset>
                <legend className="text-sm font-semibold">Message type</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {TYPES.map((t) => (
                    <Choice key={t} label={humanize(t)} active={labels.message_type === t}
                      onClick={() => setLabels({ ...labels, message_type: t, severity: t === "complaint" ? labels.severity : null })} />
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <legend className="text-sm font-semibold">Response required, and how urgently</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Choice label="No reply needed" active={!labels.response_required}
                    onClick={() => setLabels({ ...labels, response_required: false, urgency: null })} />
                  {URGENCY.map((u) => (
                    <Choice key={u} label={`Reply: ${u}`} active={labels.response_required && labels.urgency === u}
                      onClick={() => setLabels({ ...labels, response_required: true, urgency: u })} />
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <legend className="text-sm font-semibold">Categories (main first, up to 3)</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {CATEGORIES.map((c) => (
                    <Choice key={c} label={`${labels.categories.indexOf(c) >= 0 ? `${labels.categories.indexOf(c) + 1}. ` : ""}${humanize(c)}`}
                      active={labels.categories.includes(c)} onClick={() => setLabels({ ...labels, categories: toggle(labels.categories, c, 3) })} />
                  ))}
                </div>
              </fieldset>

              {labels.message_type === "complaint" && (
                <fieldset>
                  <legend className="text-sm font-semibold">Severity (how the complaint is expressed)</legend>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {["No explicit reproach", "Disapproval", "Accusation", "Blame"].map((s, i) => (
                      <Choice key={s} label={`${i + 1}. ${s}`} active={labels.severity === i + 1}
                        onClick={() => setLabels({ ...labels, severity: i + 1 })} />
                    ))}
                  </div>
                </fieldset>
              )}

              <fieldset>
                <legend className="text-sm font-semibold">Risk flags (if unsure about safety, flag it)</legend>
                <div className="mt-2 flex flex-wrap gap-2">
                  {RISKS.map((r) => (
                    <Choice key={r} label={humanize(r)} active={labels.risk_flags.includes(r)}
                      onClick={() => setLabels({ ...labels, risk_flags: toggle(labels.risk_flags, r) })} />
                  ))}
                </div>
              </fieldset>

              <label className="block text-sm">
                <span className="font-semibold">Note (optional, for borderline cases)</span>
                <input value={labels.note ?? ""} onChange={(e) => setLabels({ ...labels, note: e.target.value })}
                  className="mt-1 w-full rounded-lg border border-line px-3 py-1.5" />
              </label>

              <div className="flex items-center gap-4">
                <button type="button" onClick={save} disabled={left.length > 0}
                  className="rounded-lg bg-ink px-5 py-2 font-semibold text-white disabled:opacity-50">
                  Save and next
                </button>
                {left.length > 0 && <span className="text-sm text-muted">To save: {left.join(", ")}.</span>}
              </div>
            </div>
          ) : (
            <p className="text-muted">Loading…</p>
          )}
        </section>

        <aside className="space-y-6">
          <section className="rounded-xl border border-line bg-white p-4">
            <h2 className="font-semibold">Agreement on this set</h2>
            {agreement && agreement.double_labelled_items > 0 ? (
              <table className="mt-2 w-full text-sm">
                <thead className="text-muted">
                  <tr><th className="text-left font-medium">Field</th><th className="text-right font-medium">κ</th><th className="text-right font-medium">Agree</th></tr>
                </thead>
                <tbody>
                  {Object.entries(agreement.fields).map(([f, v]) => (
                    <tr key={f}>
                      <td>{humanize(f)}</td>
                      <td className="text-right">{(v.kappa ?? v.kappa_quadratic) ?? "n/a"}</td>
                      <td className="text-right">{Math.round(v.agreement * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="mt-1 text-sm text-muted">Appears once two people have labelled the same items.</p>
            )}
            {agreement && agreement.double_labelled_items > 0 && (
              <p className="mt-2 text-xs text-muted">{agreement.double_labelled_items} items labelled by two people. Severity uses quadratic-weighted κ.</p>
            )}
          </section>

          <section className="rounded-xl border border-line bg-white p-4">
            <h2 className="font-semibold">Write a French message</h2>
            <p className="mt-1 text-sm text-muted">
              No licensed French complaint data exists, so the French gold set is written by the team. Use invented details only.
            </p>
            <textarea value={frText} onChange={(e) => setFrText(e.target.value)} rows={4}
              className="mt-2 w-full rounded-lg border border-line px-3 py-2 text-sm"
              placeholder="Ex. : Le chauffeur a pris un détour et j'ai payé 12 $ de plus." />
            <button type="button" disabled={frText.trim().length < 2}
              onClick={async () => {
                try {
                  await api.annotateAddItem(frText, "fr");
                  setFrText("");
                  setVersion((v) => v + 1);
                } catch (e) {
                  setError(explain(e));
                }
              }}
              className="mt-2 rounded-lg border border-line px-3 py-1.5 text-sm font-semibold disabled:opacity-50">
              Add to the French set
            </button>
          </section>
        </aside>
      </div>
    </main>
  );
}
