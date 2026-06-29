import type { Metadata } from "next";

import { BOOKING_URL, BRAND_NAME } from "@/lib/config";

export const metadata: Metadata = {
  title: `${BRAND_NAME} — Never miss another customer call`,
  description:
    "An AI receptionist that answers every call 24/7, books the appointment, and only interrupts you for real emergencies. Stop losing jobs to voicemail.",
};

/**
 * Public marketing landing page for the AI voice-agents service. Fully static
 * server component: no client JS, no data fetching. One job — turn a skeptical
 * service-business owner into a booked 15-minute call. Every CTA points at
 * BOOKING_URL (see lib/config.ts). The FAQ uses native <details> so it stays
 * interactive without shipping a byte of JavaScript.
 */

// --- shared pieces -------------------------------------------------------

function BookCta({
  children = "Book a 15-minute call",
  variant = "solid",
}: {
  children?: React.ReactNode;
  variant?: "solid" | "ghost";
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3.5 " +
    "text-base font-semibold transition focus:outline-none focus-visible:ring-2 " +
    "focus-visible:ring-offset-2 focus-visible:ring-blue-500";
  const styles =
    variant === "solid"
      ? "bg-blue-600 text-white shadow-sm hover:bg-blue-500 focus-visible:ring-offset-slate-950"
      : "border border-slate-300 bg-white text-slate-900 hover:bg-slate-50 focus-visible:ring-offset-white";
  return (
    <a href={BOOKING_URL} className={`${base} ${styles}`}>
      {children}
      <ArrowIcon />
    </a>
  );
}

function ArrowIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

// --- page ----------------------------------------------------------------

export default function VoiceAgentsPage() {
  return (
    <div className="min-h-screen bg-white font-[family-name:var(--font-geist-sans)] text-slate-900 antialiased">
      {/* Nav */}
      <header className="absolute inset-x-0 top-0 z-10">
        <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <span className="text-lg font-bold tracking-tight text-white">
            {BRAND_NAME}
          </span>
          <a
            href={BOOKING_URL}
            className="rounded-lg bg-white/10 px-4 py-2 text-sm font-semibold text-white ring-1 ring-inset ring-white/20 transition hover:bg-white/20"
          >
            Book a call
          </a>
        </nav>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden bg-slate-950 text-white">
        {/* soft accent glow, kept subtle so it reads premium not flashy */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-32 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-blue-600/20 blur-3xl"
        />
        <div className="relative mx-auto max-w-3xl px-6 pb-20 pt-32 text-center sm:pb-28 sm:pt-40">
          <p className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/5 px-4 py-1.5 text-sm font-medium text-blue-200 ring-1 ring-inset ring-white/10">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            AI receptionist for service businesses
          </p>
          <h1 className="text-balance text-4xl font-extrabold leading-[1.1] tracking-tight sm:text-6xl">
            Every missed call is a customer calling your competitor next.
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-balance text-lg leading-relaxed text-slate-300 sm:text-xl">
            Our AI receptionist answers every call 24/7, books the appointment,
            and only interrupts you for real emergencies — so you stop losing
            jobs to voicemail.
          </p>
          <div className="mt-9 flex flex-col items-center gap-3">
            <BookCta />
            <p className="text-sm text-slate-400">
              15 minutes. Nothing to install. See exactly how it would answer
              your phone.
            </p>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="bg-slate-950 text-white">
        <div className="mx-auto max-w-3xl px-6 py-20 text-center sm:py-24">
          <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
            See it answer your phone before you decide.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-balance text-lg text-slate-300">
            Book a 15-minute call. We&rsquo;ll show you exactly how it would
            handle your calls — then you choose. No pressure, no contracts to
            sign on the spot.
          </p>
          <div className="mt-8 flex justify-center">
            <BookCta />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-6 py-8 text-sm text-slate-500 sm:flex-row">
          <span className="font-semibold text-slate-700">{BRAND_NAME}</span>
          <span>AI call answering for small service businesses.</span>
        </div>
      </footer>
    </div>
  );
}
