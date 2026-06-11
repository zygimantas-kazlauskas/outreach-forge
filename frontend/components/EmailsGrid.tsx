"use client";

/**
 * Final drafts for a finished run: one card per email with copy-to-clipboard.
 * Send stays disabled until Resend lands in Block 6 (the API answers 501).
 */

import { useEffect, useState } from "react";

import { ApiError, getRunEmails } from "@/lib/api";
import type { RunEmail } from "@/lib/types";
import { ErrorBanner, Spinner, buttonClass, cardClass, subtleButtonClass } from "@/components/ui";

function CopyButton({ email }: { email: RunEmail }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={subtleButtonClass}
      onClick={async () => {
        await navigator.clipboard.writeText(`${email.subject}\n\n${email.body}`);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? "Copied" : "Copy subject + body"}
    </button>
  );
}

function EmailCard({ email }: { email: RunEmail }) {
  return (
    <div className={`${cardClass} space-y-3`}>
      <div className="space-y-1">
        <p className="text-xs font-medium text-neutral-500">
          {email.target_name ?? `target ${email.target_id}`} · {email.send_status}
        </p>
        <h3 className="text-sm font-semibold">{email.subject}</h3>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{email.body}</p>
      {email.chosen_hook && (
        <p className="border-t border-neutral-200 pt-2 text-xs text-neutral-500 dark:border-neutral-800">
          Hook: {email.chosen_hook}
        </p>
      )}
      <div className="flex gap-2">
        <CopyButton email={email} />
        <button
          type="button"
          className={buttonClass}
          disabled
          title="Email sending arrives in Block 6 (Resend) — the API currently returns 501."
        >
          Send
        </button>
      </div>
    </div>
  );
}

export function EmailsGrid({ runId }: { runId: number }) {
  const [emails, setEmails] = useState<RunEmail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRunEmails(runId)
      .then((list) => !cancelled && setEmails(list))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) return <ErrorBanner message={error} />;
  if (emails === null) return <Spinner label="Loading drafts…" />;
  if (emails.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        No drafts were produced (every target failed).
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {emails.map((email) => (
        <EmailCard key={email.email_id} email={email} />
      ))}
    </div>
  );
}
