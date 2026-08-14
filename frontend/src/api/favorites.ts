import { apiFetch, readApiError } from "./client";

export type Favorite = {
  id: string;
  restaurant?: string | null;
  place_id?: string | null;
  note?: string | null;
  created_at: string;
};

export async function listFavorites(): Promise<Favorite[]> {
  const response = await apiFetch("/favorites", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { favorites: Favorite[] }).favorites;
}

export async function addFavorite(
  placeId: string,
  note?: string,
  collectionId?: string,
): Promise<Favorite> {
  const response = await apiFetch("/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ place_id: placeId, note, collection_id: collectionId }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export type SavedPlace = {
  id: string;
  place_id?: string | null;
  legacy_name?: string | null;
  collections: Array<{ collection_id: string; note?: string | null }>;
  created_at: string;
};

export type FavoriteCollection = {
  id: string;
  name: string;
  is_default: boolean;
  item_count: number;
};

export async function listSavedPlaces(collectionId?: string): Promise<SavedPlace[]> {
  const query = collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : "";
  const response = await apiFetch(`/favorites/saved${query}`, {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { favorites: SavedPlace[] }).favorites;
}

export async function listCollections(): Promise<FavoriteCollection[]> {
  const response = await apiFetch("/favorites/collections", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { collections: FavoriteCollection[] }).collections;
}

export async function createCollection(name: string): Promise<FavoriteCollection> {
  const response = await apiFetch("/favorites/collections", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function deleteCollection(id: string): Promise<void> {
  const response = await apiFetch(`/favorites/collections/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function updateSavedNote(
  favoriteId: string, collectionId: string, note: string,
): Promise<void> {
  const response = await apiFetch(
    `/favorites/${encodeURIComponent(favoriteId)}/collections/${encodeURIComponent(collectionId)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) },
  );
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function deleteFavorite(id: string): Promise<void> {
  const response = await apiFetch(`/favorites/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await readApiError(response));
}
