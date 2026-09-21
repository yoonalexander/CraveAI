import { beforeEach, describe, expect, it, vi } from "vitest";

import { recordStartupTiming, resetStartupTelemetryForTests } from "./startupTelemetry";

describe("startup telemetry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetStartupTelemetryForTests();
  });

  it("batches bounded first-occurrence timings without sending account cookies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    recordStartupTiming("first_api_response", "success", 120);
    recordStartupTiming("auth_me", "timeout", 4_000);
    recordStartupTiming("auth_me", "success", 4_500);

    await vi.advanceTimersByTimeAsync(5_000);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/telemetry/startup");
    expect(init.credentials).toBe("omit");
    expect(JSON.parse(init.body as string)).toEqual({
      events: [
        { name: "first_api_response", duration_ms: 120, outcome: "success" },
        { name: "auth_me", duration_ms: 4_000, outcome: "timeout" },
      ],
    });
  });
});
