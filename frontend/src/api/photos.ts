import { apiFetch } from "./client";

export type PlacePhoto = {
  place_id: string;
  index: number;
  total: number;
  photo: {
    uri: string;
    source_uri: string | null;
    report_uri: string | null;
    authors: Array<{ name: string; uri: string | null; avatar_uri: string | null }>;
  } | null;
};

export class PhotoLimitError extends Error {}

export async function fetchPlacePhoto(placeId: string, index: number, signal: AbortSignal): Promise<PlacePhoto> {
  const response = await apiFetch("/places/photo", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ place_id: placeId, index }), signal, cache: "no-store",
  }, { csrf: false });
  if (response.status === 429) throw new PhotoLimitError("Photos are temporarily paused. Try again later.");
  if (!response.ok) throw new Error("Photos could not be loaded.");
  const data = await response.json() as PlacePhoto;
  if (data.place_id !== placeId) throw new Error("Photo venue did not match.");
  return data;
}
