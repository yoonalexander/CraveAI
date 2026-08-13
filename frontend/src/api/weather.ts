export type CurrentWeather = {
  temperature: number;
  condition: string;
  isDay: boolean;
};

type OpenMeteoResponse = {
  current?: {
    temperature_2m?: number;
    weather_code?: number;
    is_day?: number;
  };
};

export async function fetchCurrentWeather(
  lat: number,
  lng: number,
  signal?: AbortSignal,
): Promise<CurrentWeather> {
  const params = new URLSearchParams({
    latitude: String(lat),
    longitude: String(lng),
    current: "temperature_2m,weather_code,is_day",
    temperature_unit: "celsius",
    timezone: "auto",
  });
  const response = await fetch(
    `https://api.open-meteo.com/v1/forecast?${params.toString()}`,
    { signal },
  );
  if (!response.ok) {
    throw new Error(`Weather request failed (${response.status}).`);
  }

  const payload = (await response.json()) as OpenMeteoResponse;
  const temperature = payload.current?.temperature_2m;
  const weatherCode = payload.current?.weather_code;
  if (typeof temperature !== "number" || typeof weatherCode !== "number") {
    throw new Error("Weather response was incomplete.");
  }

  return {
    temperature,
    condition: weatherCodeToCondition(weatherCode),
    isDay: payload.current?.is_day !== 0,
  };
}

export function weatherCodeToCondition(code: number): string {
  if (code === 0) return "Clear";
  if (code <= 3) return "Cloudy";
  if (code === 45 || code === 48) return "Foggy";
  if (code >= 51 && code <= 57) return "Drizzle";
  if (code >= 61 && code <= 67) return "Rainy";
  if (code >= 71 && code <= 77) return "Snowy";
  if (code >= 80 && code <= 82) return "Showers";
  if (code >= 85 && code <= 86) return "Snow showers";
  if (code >= 95) return "Stormy";
  return "Mixed";
}
