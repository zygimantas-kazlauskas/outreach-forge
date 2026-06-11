"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createRun } from "@/lib/api";
import { DEFAULT_SERVICE_ID, SERVICES } from "@/lib/config";
import type { TargetIn } from "@/lib/types";
import {
  ErrorBanner,
  buttonClass,
  cardClass,
  inputClass,
  labelClass,
  subtleButtonClass,
} from "@/components/ui";

interface TargetRow extends TargetIn {
  key: number;
}

let nextKey = 1;

function emptyRow(): TargetRow {
  return { key: nextKey++, company_name: "", url: "", contact_name: "", contact_role: "", notes: "" };
}

export default function NewRunPage() {
  const router = useRouter();
  const [serviceId, setServiceId] = useState<string>(DEFAULT_SERVICE_ID);
  const [concurrency, setConcurrency] = useState(3);
  const [rows, setRows] = useState<TargetRow[]>([emptyRow()]);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [showValidation, setShowValidation] = useState(false);

  const updateRow = (key: number, patch: Partial<TargetIn>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  // Mirrors the backend's 422 rules so users rarely hit raw API errors:
  // >= 1 target, company_name non-empty, concurrency an integer in 1-10.
  const rowInvalid = (row: TargetRow) => row.company_name.trim().length === 0;
  const concurrencyInvalid =
    !Number.isInteger(concurrency) || concurrency < 1 || concurrency > 10;
  const formInvalid = rows.length === 0 || rows.some(rowInvalid) || concurrencyInvalid;

  async function submit() {
    setShowValidation(true);
    setApiError(null);
    if (formInvalid) return;

    const targets: TargetIn[] = rows.map(({ key, ...t }) => ({
      ...t,
      company_name: t.company_name.trim(),
      url: t.url || null,
      contact_name: t.contact_name || null,
      contact_role: t.contact_role || null,
      notes: t.notes ?? "",
    }));

    setSubmitting(true);
    try {
      const created = await createRun({ service_id: serviceId, targets, concurrency });
      router.push(`/runs/${created.run_id}`);
    } catch (e) {
      setApiError(e instanceof ApiError ? e.message : String(e));
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Outreach Forge</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Compose a run: pick a service, add targets, launch the pipeline.
        </p>
      </header>

      <section className={`${cardClass} space-y-3`}>
        <div className="flex flex-wrap items-end gap-4">
          <div className="grow">
            <label htmlFor="service" className={labelClass}>
              Service
            </label>
            <select
              id="service"
              className={`${inputClass} mt-1`}
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
            >
              {SERVICES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="concurrency" className={labelClass}>
              Concurrency (1–10)
            </label>
            <input
              id="concurrency"
              type="number"
              min={1}
              max={10}
              className={`${inputClass} mt-1 w-24`}
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
            />
            {showValidation && concurrencyInvalid && (
              <p className="mt-1 text-xs text-red-600">Whole number, 1 to 10.</p>
            )}
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Targets ({rows.length})</h2>
          <button
            type="button"
            className={subtleButtonClass}
            onClick={() => setRows((rs) => [...rs, emptyRow()])}
          >
            Add target
          </button>
        </div>

        {rows.map((row, index) => (
          <div key={row.key} className={`${cardClass} space-y-2`}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-neutral-500">
                Target {index + 1}
              </span>
              <button
                type="button"
                className="text-xs text-neutral-500 hover:text-red-600"
                onClick={() => setRows((rs) => rs.filter((r) => r.key !== row.key))}
                disabled={rows.length === 1}
                title={rows.length === 1 ? "A run needs at least one target" : "Remove"}
              >
                Remove
              </button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <label className={labelClass}>Company name *</label>
                <input
                  className={`${inputClass} mt-1`}
                  value={row.company_name}
                  onChange={(e) => updateRow(row.key, { company_name: e.target.value })}
                  placeholder="Westshore Family Dental"
                />
                {showValidation && rowInvalid(row) && (
                  <p className="mt-1 text-xs text-red-600">Company name is required.</p>
                )}
              </div>
              <div>
                <label className={labelClass}>URL</label>
                <input
                  className={`${inputClass} mt-1`}
                  value={row.url ?? ""}
                  onChange={(e) => updateRow(row.key, { url: e.target.value })}
                  placeholder="example.com"
                />
              </div>
              <div>
                <label className={labelClass}>Contact name</label>
                <input
                  className={`${inputClass} mt-1`}
                  value={row.contact_name ?? ""}
                  onChange={(e) => updateRow(row.key, { contact_name: e.target.value })}
                />
              </div>
              <div>
                <label className={labelClass}>Contact role</label>
                <input
                  className={`${inputClass} mt-1`}
                  value={row.contact_role ?? ""}
                  onChange={(e) => updateRow(row.key, { contact_role: e.target.value })}
                />
              </div>
            </div>
            <div>
              <label className={labelClass}>Notes (what the researcher works from)</label>
              <textarea
                className={`${inputClass} mt-1 min-h-20`}
                value={row.notes ?? ""}
                onChange={(e) => updateRow(row.key, { notes: e.target.value })}
                placeholder="Observable details: size, hours, positioning, anything from their site…"
              />
            </div>
          </div>
        ))}
      </section>

      {apiError && <ErrorBanner message={apiError} />}

      <div className="flex justify-end">
        <button
          type="button"
          className={buttonClass}
          onClick={submit}
          disabled={submitting}
        >
          {submitting ? "Starting run…" : "Start run"}
        </button>
      </div>
    </main>
  );
}
