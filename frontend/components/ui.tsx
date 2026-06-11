/**
 * Minimal shared UI primitives. Deliberately plain Tailwind (no component
 * library): this is an operator tool — clarity over beauty.
 */

export const inputClass =
  "w-full rounded border border-neutral-300 bg-background px-2 py-1.5 text-sm " +
  "text-foreground placeholder:text-neutral-400 focus:outline-none " +
  "focus:ring-2 focus:ring-neutral-400 dark:border-neutral-700";

export const buttonClass =
  "rounded bg-foreground px-3 py-1.5 text-sm font-medium text-background " +
  "hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40";

export const subtleButtonClass =
  "rounded border border-neutral-300 px-3 py-1.5 text-sm text-foreground " +
  "hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-40 " +
  "dark:border-neutral-700 dark:hover:bg-neutral-900";

export const cardClass =
  "rounded-lg border border-neutral-200 bg-background p-4 dark:border-neutral-800";

export const labelClass = "block text-xs font-medium text-neutral-500";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
    >
      {message}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <p className="animate-pulse text-sm text-neutral-500">{label}</p>
  );
}
