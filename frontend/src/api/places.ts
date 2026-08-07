const API_URL =
    import.meta.env.VITE_API_URL?.toString()?.trim() ||
    "https://craveai-d8gh.onrender.com";

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

export async function fetchSuggestions(
    lat: number,
    lng: number,
    radius: number = 5000,
    signal?: AbortSignal,
): Promise<Suggestion[]> {
    const response = await fetch(
        `${API_URL}/places/suggestions?lat=${lat}&lng=${lng}&radius=${radius}`,
        { signal },
    );
    if (!response.ok) {
        throw new Error("Failed to fetch suggestions");
    }
    return response.json();
}
