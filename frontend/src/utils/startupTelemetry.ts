export type StartupEventName =
  | "first_api_response"
  | "auth_me"
  | "preferences"
  | "geolocation"
  | "maps_ready"
  | "first_map_render";

export type StartupOutcome = "success" | "timeout" | "error" | "denied" | "fallback";

type StartupEvent = {
  name: StartupEventName;
  duration_ms: number;
  outcome: StartupOutcome;
};

const REPORT_DELAY_MS = 5_000;
const navigationStartedAt = performance.now();
const timings = new Map<StartupEventName, StartupEvent>();
let reportTimer: number | null = null;

export function recordStartupTiming(
  name: StartupEventName,
  outcome: StartupOutcome,
  durationMs = performance.now() - navigationStartedAt,
): void {
  if (timings.has(name)) return;
  timings.set(name, {
    name,
    duration_ms: Math.max(0, Math.round(durationMs)),
    outcome,
  });
  if (reportTimer === null) {
    reportTimer = window.setTimeout(() => {
      reportTimer = null;
      void flushStartupTimings();
    }, REPORT_DELAY_MS);
  }
}

export async function flushStartupTimings(): Promise<void> {
  if (!timings.size) return;
  const events = Array.from(timings.values());
  timings.clear();
  try {
    await fetch("/api/telemetry/startup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
      credentials: "omit",
      keepalive: true,
    });
  } catch {
    // Startup reporting must never affect the user-facing startup path.
  }
}

export function resetStartupTelemetryForTests(): void {
  timings.clear();
  if (reportTimer !== null) window.clearTimeout(reportTimer);
  reportTimer = null;
}
