import { apiFetch, readApiError } from "./client";

export type Favorite = {
  id: string;
  restaurant: string;
  note?: string | null;
  created_at: string;
};

export async function listFavorites(): Promise<Favorite[]> {
  const response = await apiFetch("/favorites", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { favorites: Favorite[] }).favorites;
}

export async function addFavorite(
  restaurant: string,
  note?: string,
): Promise<Favorite> {
  const response = await apiFetch("/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ restaurant, note }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function deleteFavorite(id: string): Promise<void> {
  const response = await apiFetch(`/favorites/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(await readApiError(response));
}
