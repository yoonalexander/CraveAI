import { CloudIcon, PinIcon, SunIcon } from "./Icons";

/** Decorative indicators; the surrounding status supplies the accessible label. */
export function LocationLoader({ large = false }: { large?: boolean }): JSX.Element {
  return (
    <span aria-hidden="true" className={`location-loader${large ? " location-loader-large" : ""}`}>
      <span className="location-loader-ring" />
      <span className="location-loader-ring" />
      <PinIcon className="location-loader-pin" />
    </span>
  );
}

export function WeatherLoader(): JSX.Element {
  return (
    <span aria-hidden="true" className="weather-loader">
      <SunIcon className="weather-loader-sun" />
      <CloudIcon className="weather-loader-cloud" />
    </span>
  );
}
