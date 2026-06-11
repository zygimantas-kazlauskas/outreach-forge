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
