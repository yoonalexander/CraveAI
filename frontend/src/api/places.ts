const API_BASE_URL = "http://localhost:8000";

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
): Promise<Suggestion[]> {
    const response = await fetch(
        `${API_BASE_URL}/places/suggestions?lat=${lat}&lng=${lng}&radius=${radius}`,
    );
    if (!response.ok) {
        throw new Error("Failed to fetch suggestions");
    }
    return response.json();
}
