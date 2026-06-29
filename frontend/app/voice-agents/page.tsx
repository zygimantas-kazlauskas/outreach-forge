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

/**
 * The CTA only becomes a live link once BOOKING_URL is a real https URL.
 * Until then (placeholder value) it stays in a "coming soon" state and links
 * nowhere — so no real or personal address is ever exposed. Flipping it live
 * is a one-line change to BOOKING_URL in lib/config.ts.
 */
const BOOKING_LIVE =
  BOOKING_URL.startsWith("https://") &&
  !BOOKING_URL.includes("REPLACE-WITH-BOOKING-LINK");

function BookCta({
  children = "Book a 15-minute call",
}: {
  children?: React.ReactNode;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3.5 " +
    "text-base font-semibold transition focus:outline-none focus-visible:ring-2 " +
    "focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 focus-visible:ring-blue-500";

  if (!BOOKING_LIVE) {
    return (
      <span
        aria-disabled="true"
        className={`${base} cursor-not-allowed bg-white/10 text-slate-300 ring-1 ring-inset ring-white/15`}
      >
        Booking — coming soon
      </span>
    );
  }

  return (
    <a
      href={BOOKING_URL}
      className={`${base} bg-blue-600 text-white shadow-sm hover:bg-blue-500`}
    >
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

function PhoneIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
      <path d="m9 16 2 2 4-4" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
      <path d="M12 8v4M12 16h.01" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
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
          {BOOKING_LIVE ? (
            <a
              href={BOOKING_URL}
              className="rounded-lg bg-white/10 px-4 py-2 text-sm font-semibold text-white ring-1 ring-inset ring-white/20 transition hover:bg-white/20"
            >
              Book a call
            </a>
          ) : (
            <span
              aria-disabled="true"
              className="cursor-not-allowed rounded-lg bg-white/5 px-4 py-2 text-sm font-medium text-slate-400 ring-1 ring-inset ring-white/10"
            >
              Booking soon
            </span>
          )}
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

      {/* Problem, made concrete */}
      <section className="bg-white">
        <div className="mx-auto max-w-3xl px-6 py-20 sm:py-24">
          <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
            You don&rsquo;t lose customers because you&rsquo;re bad. You lose
            them because no one picked up.
          </h2>
          <div className="mt-8 space-y-5 text-lg leading-relaxed text-slate-600">
            <p>
              It&rsquo;s 7pm. Someone with a cracked tooth, a flooded kitchen, a
              wedding next week calls your number. You&rsquo;re closed. So they
              scroll down to the next name on Google and call them instead. That
              job is gone, and you never even knew it rang.
            </p>
            <p>
              It happens during the day too — you&rsquo;re with a patient, under
              a sink, mid-haircut. The phone rings out. Most people who hit a
              voicemail just hang up and call the next business on the list.
              They don&rsquo;t leave a message, and they don&rsquo;t call back.
            </p>
            <p className="font-medium text-slate-900">
              Every one of those calls was a paying customer you&rsquo;d already
              spent money on marketing to reach. Miss a few a week and it adds
              up to thousands of dollars walking straight to your competitors.
            </p>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-slate-50">
        <div className="mx-auto max-w-5xl px-6 py-20 sm:py-24">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
              An AI receptionist that never goes home
            </h2>
            <p className="mt-4 text-lg text-slate-600">
              It picks up on the first ring, day or night, and handles the call
              like your best front-desk person would. Three steps to set up.
            </p>
          </div>
          <ol className="mt-12 grid gap-6 sm:grid-cols-3">
            {[
              {
                icon: <PhoneIcon />,
                step: "1",
                title: "We learn your business",
                body: "Your hours, services, prices, and what counts as a real emergency. One short call and it knows your front desk cold.",
              },
              {
                icon: <CalendarIcon />,
                step: "2",
                title: "It answers every call",
                body: "A natural-sounding receptionist picks up 24/7 — after hours, on weekends, and while you're already on the phone — and books straight into your calendar.",
              },
              {
                icon: <ShieldIcon />,
                step: "3",
                title: "You get the booking, not the busywork",
                body: "Genuine emergencies ring through to you. Everything else is answered, booked, and logged so nothing slips.",
              },
            ].map((s) => (
              <li
                key={s.step}
                className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  {s.icon}
                </div>
                <p className="mt-5 text-sm font-semibold text-blue-600">
                  Step {s.step}
                </p>
                <h3 className="mt-1 text-lg font-bold tracking-tight">
                  {s.title}
                </h3>
                <p className="mt-2 text-slate-600">{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Why it matters / outcomes */}
      <section className="bg-white">
        <div className="mx-auto max-w-4xl px-6 py-20 sm:py-24">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
              Stop paying to be reached, then missing the call
            </h2>
            <p className="mt-4 text-lg text-slate-600">
              This isn&rsquo;t about answering more calls. It&rsquo;s about
              keeping the customers you&rsquo;re already winning.
            </p>
          </div>
          <ul className="mt-12 grid gap-6 sm:grid-cols-3">
            {[
              {
                title: "No missed calls",
                body: "Every ring answered — 2am, Sunday, or your busiest hour. The booking lands with you instead of your competitor.",
              },
              {
                title: "No extra payroll",
                body: "A full-time receptionist runs thousands a month. This costs a fraction of that and never calls in sick.",
              },
              {
                title: "No voicemail dead-ends",
                body: "Callers reach a real answer and a booked time, not a beep. The moment they're ready to buy, you're there.",
              },
            ].map((o) => (
              <li key={o.title} className="rounded-2xl bg-slate-50 p-6">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                  <CheckIcon />
                </div>
                <h3 className="mt-4 text-lg font-bold tracking-tight">
                  {o.title}
                </h3>
                <p className="mt-2 text-slate-600">{o.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Objection handling / FAQ */}
      <section className="bg-slate-50">
        <div className="mx-auto max-w-2xl px-6 py-20 sm:py-24">
          <h2 className="text-balance text-center text-3xl font-bold tracking-tight sm:text-4xl">
            The questions everyone asks
          </h2>
          <div className="mt-10 space-y-3">
            {[
              {
                q: "Will it sound like a robot?",
                a: "No. It speaks naturally, knows your business, and most callers won't realize they're not talking to a person. You hear exactly how it sounds and sign off before it ever answers a real call.",
              },
              {
                q: "Is this complicated to set up?",
                a: "No. We do the setup for you. There's no app to install and nothing changes about how you work — your phone just stops going unanswered.",
              },
              {
                q: "Will it work with my current phone number?",
                a: "Yes. It works with the number and provider you already have. Keep the same number on your cards, your van, and your website — nothing to reprint.",
              },
              {
                q: "What happens with real emergencies?",
                a: "You decide what counts as urgent. Genuine emergencies get routed straight to you or your on-call line; routine calls get booked and logged so they're waiting for you.",
              },
              {
                q: "What does it cost?",
                a: "Less than the jobs you lose to voicemail in a typical month. We'll give you a straight, no-games number on the call — once we know your business, not before.",
              },
            ].map((item) => (
              <details
                key={item.q}
                className="group rounded-xl border border-slate-200 bg-white px-5 [&_summary]:cursor-pointer"
              >
                <summary className="flex items-center justify-between gap-4 py-4 text-lg font-semibold marker:content-none">
                  {item.q}
                  <span className="text-slate-400 transition group-open:rotate-45">
                    <PlusIcon />
                  </span>
                </summary>
                <p className="pb-5 text-slate-600">{item.a}</p>
              </details>
            ))}
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
