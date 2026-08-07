import { apiFetch } from "./client";

export interface Suggestion {
    name: string;
    rating: number;
    address: string;
    reason: string;
    place_id: string;
    lat: number;
    lng: number;
    tags?: string[];
    user_ratings_total?: number;
}

export class PlacesQuotaError extends Error {
    resetAt: string | null;

    constructor(resetAt: string | null) {
        super("Today's nearby discovery limit has been reached.");
        this.name = "PlacesQuotaError";
        this.resetAt = resetAt;
    }
}

export async function fetchSuggestions(
    lat: number,
    lng: number,
    radius: number = 5000,
    signal?: AbortSignal,
): Promise<Suggestion[]> {
    const response = await apiFetch(
        `/places/suggestions?lat=${lat}&lng=${lng}&radius=${radius}`,
        { signal },
        { csrf: false },
    );
    if (!response.ok) {
        if (response.status === 429) {
            throw new PlacesQuotaError(response.headers.get("x-ratelimit-reset"));
        }
        throw new Error(`Failed to fetch suggestions (${response.status})`);
    }
    return response.json();
}
