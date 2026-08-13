import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentWeather, weatherCodeToCondition } from "./weather";

afterEach(() => vi.restoreAllMocks());

describe("weather", () => {
  it("maps WMO weather codes to compact sidebar labels", () => {
    expect(weatherCodeToCondition(0)).toBe("Clear");
    expect(weatherCodeToCondition(3)).toBe("Cloudy");
    expect(weatherCodeToCondition(63)).toBe("Rainy");
    expect(weatherCodeToCondition(75)).toBe("Snowy");
    expect(weatherCodeToCondition(96)).toBe("Stormy");
  });

  it("requests current weather for the selected coordinates", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          current: { temperature_2m: 18.4, weather_code: 2, is_day: 1 },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(fetchCurrentWeather(43.6, -79.4)).resolves.toEqual({
      temperature: 18.4,
      condition: "Cloudy",
      isDay: true,
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain("latitude=43.6");
    expect(String(fetchMock.mock.calls[0][0])).toContain("longitude=-79.4");
  });

  it("rejects incomplete provider responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ current: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(fetchCurrentWeather(1, 2)).rejects.toThrow("incomplete");
  });
});
