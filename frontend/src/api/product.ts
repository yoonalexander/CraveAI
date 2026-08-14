import { apiFetch, readApiError } from "./client";
import type { Suggestion } from "./places";

export type LegalCurrent = {
  terms: { version: string; effective_date: string; path: string };
  privacy: { version: string; effective_date: string; path: string };
  minimum_age: number;
  operator_legal_name: string;
  operator_address: string;
  governing_law: string;
  support_email: string;
  privacy_email: string;
  revision_history: Array<{ terms_version: string; privacy_version: string; effective_date: string; summary: string }>;
  publication_ready: boolean;
  publication_issues?: string[];
};

export async function fetchLegalCurrent(): Promise<LegalCurrent> {
  const response = await apiFetch("/legal/current", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function acceptCurrentPolicies(current: LegalCurrent): Promise<void> {
  const response = await apiFetch("/legal/accept", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      terms_version: current.terms.version, privacy_version: current.privacy.version,
      accept_terms: true, acknowledge_privacy: true, age_confirmed: true,
    }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
}

export type Preferences = {
  favorite_cuisines: string[];
  disliked_foods: string[];
  dietary_restrictions: string[];
  allergies: string[];
  default_location?: { lat: number; lng: number; label: string } | null;
  default_radius_meters: number;
  recommendation_preferences: Record<string, unknown>;
  personalization_enabled: boolean;
  history_enabled: boolean;
  reduced_motion: "system" | "on" | "off";
  notification_preferences: Record<string, boolean>;
};

export async function fetchPreferences(): Promise<Preferences> {
  const response = await apiFetch("/account/preferences", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function patchPreferences(changes: Partial<Preferences>): Promise<Preferences> {
  const response = await apiFetch("/account/preferences", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes),
  });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function clearHistory(): Promise<void> {
  const response = await apiFetch("/account/history", { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function resetPersonalization(): Promise<void> {
  const response = await apiFetch("/account/personalization", { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export type Conversation = { id: string; title: string; summary: string; created_at: string; updated_at: string };
export type ConversationDetail = Conversation & {
  messages: Array<{ id: string; role: "user" | "assistant"; content: string; place_ids: string[]; created_at: string }>;
};

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiFetch("/conversations", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { conversations: Conversation[] }).conversations;
}

export async function saveConversationMessages(
  messages: Array<{ role: "user" | "assistant"; content: string; place_ids: string[] }>,
): Promise<string> {
  const firstPrompt = messages.find((item) => item.role === "user")?.content || "Saved conversation";
  const create = await apiFetch("/conversations", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ first_prompt: firstPrompt }),
  });
  if (!create.ok) throw new Error(await readApiError(create));
  const conversation = (await create.json()) as Conversation;
  for (const message of messages.slice(-12)) {
    const response = await apiFetch(`/conversations/${encodeURIComponent(conversation.id)}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(message),
    });
    if (!response.ok) throw new Error(await readApiError(response));
  }
  return conversation.id;
}

export async function readConversation(id: string): Promise<ConversationDetail> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(id)}`, {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return response.json();
}

export async function renameConversation(id: string, title: string): Promise<void> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function resolvePlaces(placeIds: string[]): Promise<Suggestion[]> {
  if (!placeIds.length) return [];
  const response = await apiFetch("/places/resolve", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ place_ids: placeIds.slice(0, 20) }),
  }, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { places: Suggestion[] }).places;
}

export type Plan = { id: string; name: string; available: boolean; coming_later?: boolean; price: number | null; limits: Record<string, number> | null; features: string[] };
export async function fetchPlans(): Promise<Plan[]> {
  const response = await apiFetch("/plans", {}, { csrf: false });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { plans: Plan[] }).plans;
}

export async function submitFeedback(
  recommendationToken: string, liked: boolean, notes?: string, reportReason?: string,
): Promise<void> {
  const response = await apiFetch("/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recommendation_token: recommendationToken, liked, notes, report_reason: reportReason }),
  });
  if (!response.ok) throw new Error(await readApiError(response));
}

export async function transcribeAudio(blob: Blob, durationSeconds: number, authenticated: boolean): Promise<string> {
  const body = new FormData();
  body.append("file", blob, "craveai-recording.webm");
  body.append("duration_seconds", String(durationSeconds));
  body.append("age_confirmed", String(sessionStorage.getItem("craveai-age-18") === "true"));
  const response = await apiFetch("/audio/transcriptions", { method: "POST", body }, { csrf: authenticated });
  if (!response.ok) throw new Error(await readApiError(response));
  return ((await response.json()) as { text: string }).text;
}
