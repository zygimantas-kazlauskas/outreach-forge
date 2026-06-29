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
 * Where every "Book a call" button points. Single swap point for the CTA.
 *
 * While this is the placeholder below, every CTA on the landing page renders
 * in a non-functional "Booking — coming soon" state and links nowhere. To go
 * live, replace this with a real booking URL (Calendly / Cal.com / etc.) that
 * starts with "https://" — the CTAs turn into working links automatically.
 * Keep it https; do not point it at a personal email or phone number.
 */
export const BOOKING_URL = "https://REPLACE-WITH-BOOKING-LINK.example";
