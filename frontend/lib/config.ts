export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Services the intake page offers. Only the public example ships with the
 * repo; private service configs (gitignored on the backend) can be added
 * here locally without code changes elsewhere.
 */
export const SERVICES = [
  {
    id: "ai-voice-agents",
    label: "AI voice agents for small service businesses",
  },
] as const;

export const DEFAULT_SERVICE_ID = SERVICES[0].id;

/**
 * Public marketing site (the /voice-agents landing page that cold-email
 * recipients click through to). Keep these as the single swap points.
 */
export const BRAND_NAME = "Oakline";

/**
 * Where every "Book a call" button points. Drop in the real Calendly (or
 * similar) URL here when it's ready — nothing else needs to change.
 * Until then this falls back to a pre-filled email so the button still works.
 */
export const BOOKING_URL =
  "mailto:zygimantas.kazlauskas28@gmail.com" +
  "?subject=Book%20a%2015-minute%20call%20about%20AI%20call%20answering";
