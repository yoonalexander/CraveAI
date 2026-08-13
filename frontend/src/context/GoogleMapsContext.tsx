import { createContext, ReactNode, useContext, useMemo } from "react";
import { Libraries, useJsApiLoader } from "@react-google-maps/api";

type GoogleMapsContextValue = {
  isLoaded: boolean;
  loadError: Error | undefined;
  hasApiKey: boolean;
};

const GoogleMapsContext = createContext<GoogleMapsContextValue>({
  isLoaded: false,
  loadError: undefined,
  hasApiKey: false,
});

const libraries: Libraries = ["places"];

export function GoogleMapsProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY?.toString().trim();
  if (!apiKey) {
    return (
      <GoogleMapsContext.Provider
        value={{ isLoaded: false, loadError: undefined, hasApiKey: false }}
      >
        {children}
      </GoogleMapsContext.Provider>
    );
  }

  return <GoogleMapsLoader apiKey={apiKey}>{children}</GoogleMapsLoader>;
}

function GoogleMapsLoader({
  apiKey,
  children,
}: {
  apiKey: string;
  children: ReactNode;
}): JSX.Element {
  const { isLoaded, loadError } = useJsApiLoader({
    id: "craveai-google-maps",
    googleMapsApiKey: apiKey,
    libraries,
  });
  const value = useMemo(
    () => ({ isLoaded, loadError, hasApiKey: true }),
    [isLoaded, loadError],
  );

  return (
    <GoogleMapsContext.Provider value={value}>
      {children}
    </GoogleMapsContext.Provider>
  );
}

export function useGoogleMaps(): GoogleMapsContextValue {
  return useContext(GoogleMapsContext);
}
