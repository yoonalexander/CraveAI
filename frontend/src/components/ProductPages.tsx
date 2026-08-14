import { FormEvent, useEffect, useState } from "react";

import {
  addFavorite,
  createCollection,
  deleteCollection,
  deleteFavorite,
  FavoriteCollection,
  listCollections,
  listSavedPlaces,
  SavedPlace,
  updateSavedNote,
} from "../api/favorites";
import type { Suggestion } from "../api/places";
import {
  acceptCurrentPolicies,
  clearHistory,
  Conversation,
  ConversationDetail,
  deleteConversation,
  fetchLegalCurrent,
  fetchPlans,
  fetchPreferences,
  LegalCurrent,
  listConversations,
  patchPreferences,
  Plan,
  Preferences,
  readConversation,
  renameConversation,
  resetPersonalization,
  resolvePlaces,
} from "../api/product";
import { deleteAccount, exportAccount } from "../api/auth";
import { LEGAL_CONFIG } from "../config/legal";
import { useAuth } from "../context/AuthContext";
import { SuggestionCard } from "./SuggestionCard";

const helpArticles = [
  { id: "data-use", title: "How CraveAI uses your data", body: "CraveAI separates temporary browsing from information you deliberately save. Your confirmed coordinates and map bounds go to CraveAI and Google to find restaurants, and the active coordinates go directly from your browser to Open-Meteo for weather. OpenAI can receive your prompt, bounded recent chat context, candidate Place IDs and menu evidence, and—only when personalization is enabled—selected preferences, dietary or allergy entries, and saved Place IDs. Voice clips go to OpenAI Whisper for transcription and are cleared from CraveAI memory afterward. Supabase handles identity and the PostgreSQL application database; Vercel and Render host and proxy the service; official restaurant sites may receive bounded server requests for public menu evidence. Temporary chat recovery stays in sessionStorage unless you enable History or explicitly save a conversation. CraveAI does not use an analytics or advertising SDK, does not sell personal information, and stores hashed—not raw—network prefixes for quotas and security. Use Settings to export account data, clear History, reset personalization, or delete the account, and use the Privacy Policy for retention details and provider links." },
  { id: "maps", title: "Maps, location, and Search this area", body: "CraveAI starts near your device or selected fallback. Moving the map does not spend a Places request until you choose Search this area. The confirmed visible area controls markers, Discovery, filters, weather, and later chat requests." },
  { id: "allergies", title: "Allergies and dietary safety", body: "Dietary evidence can be incomplete and CraveAI cannot guarantee allergen safety or kitchen separation. Treat results as discovery assistance, contact the restaurant, and use professional medical advice where appropriate." },
  { id: "history", title: "Temporary chat and History", body: "History is off by default. Temporary recovery is tab-scoped. Signed-in users can enable automatic History in Settings or explicitly save a conversation. Stored conversations remain until deleted." },
  { id: "voice", title: "Voice privacy and limits", body: "Recording starts only after you select the microphone and grant browser permission. Clips are limited to 60 seconds and 10 MB, sent through CraveAI to OpenAI Whisper for transcription, and cleared from CraveAI memory after the request. OpenAI may retain provider abuse-monitoring data under its API data controls; do not record sensitive information." },
  { id: "quotas", title: "Guest and Free quotas", body: "Guest and Free quotas protect reliability and third-party provider costs. Current daily limits appear on the Pricing page and reset daily." },
  { id: "account", title: "Account, export, and deletion", body: "Account Settings lets you export account-owned data, clear History, reset personalization, and delete your account. Place details are re-hydrated from Place IDs and are not included as durable provider content." },
  { id: "limitations", title: "AI limitations and incorrect information", body: "CraveAI can misunderstand prompts or show stale third-party data. Verify hours, prices, menus, accessibility, reservations, and dietary details directly with the restaurant. Use recommendation feedback to report errors." },
] as const;

export function HelpPage(): JSX.Element {
  const initial = window.location.pathname.split("/")[2] || "";
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState<LegalCurrent | null>(null);
  useEffect(() => { void fetchLegalCurrent().then(setCurrent).catch(() => undefined); }, []);
  const filtered = helpArticles.filter((item) => `${item.title} ${item.body}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <section className="product-page help-page">
      <header className="product-page-heading"><p>Support</p><h1>How can we help?</h1><span>Search privacy, maps, chat, saved places, and account guidance.</span></header>
      <label className="help-search"><span>Search Help</span><input onChange={(event) => setQuery(event.target.value)} placeholder="Try “location” or “privacy”" value={query} /></label>
      <div className="help-grid">
        {filtered.map((article) => <details key={article.id} open={article.id === initial}><summary>{article.title}</summary><p>{article.body}</p></details>)}
      </div>
      <footer className="help-contact">
        <h2>Still need help?</h2>
        <p>Contact <a href={`mailto:${current?.support_email || LEGAL_CONFIG.supportEmail}`}>support</a>, or send privacy and data-rights requests to <a href={`mailto:${current?.privacy_email || LEGAL_CONFIG.privacyEmail}`}>the privacy team</a>.</p>
      </footer>
    </section>
  );
}

export function LikesPage(): JSX.Element {
  const { user, loading: authLoading } = useAuth();
  const [collections, setCollections] = useState<FavoriteCollection[]>([]);
  const [selected, setSelected] = useState<string | undefined>();
  const [items, setItems] = useState<SavedPlace[]>([]);
  const [places, setPlaces] = useState<Map<string, Suggestion>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [newCollection, setNewCollection] = useState("");
  const [collectionTargets, setCollectionTargets] = useState<Record<string, string>>({});

  const reload = async () => {
    if (!user) return;
    setBusy(true);
    try {
      const [nextCollections, nextItems] = await Promise.all([listCollections(), listSavedPlaces(selected)]);
      setCollections(nextCollections); setItems(nextItems);
      const hydrated = await resolvePlaces(nextItems.flatMap((item) => item.place_id ? [item.place_id] : []));
      setPlaces(new Map(hydrated.filter((item) => item.place_id && item.name).map((item) => [item.place_id, item])));
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load saved places."); }
    finally { setBusy(false); }
  };
  useEffect(() => { void reload(); }, [user, selected]);
  if (!authLoading && !user) return <SignInRequired title="Sign in to see saved restaurants" />;
  return (
    <section className="product-page likes-page">
      <header className="product-page-heading"><p>Likes</p><h1>Saved restaurants</h1><span>Place details are refreshed from Google when you open this page.</span></header>
      <div className="collection-toolbar">
        <button className={!selected ? "is-active" : ""} onClick={() => setSelected(undefined)}>All saved</button>
        {collections.map((collection) => <button className={selected === collection.id ? "is-active" : ""} key={collection.id} onClick={() => setSelected(collection.id)}>{collection.name} ({collection.item_count})</button>)}
        <form onSubmit={(event) => { event.preventDefault(); void createCollection(newCollection).then(() => { setNewCollection(""); return reload(); }).catch((reason) => setError(String(reason))); }}>
          <input aria-label="New collection name" maxLength={80} onChange={(event) => setNewCollection(event.target.value)} placeholder="New collection" value={newCollection} />
          <button disabled={!newCollection.trim()} type="submit">Create</button>
        </form>
        {selected && !collections.find((collection) => collection.id === selected)?.is_default ? <button className="collection-delete" onClick={() => { if (window.confirm("Delete this collection? The restaurant remains saved in any other collections.")) void deleteCollection(selected).then(() => { setSelected(undefined); return reload(); }); }}>Delete collection</button> : null}
      </div>
      {error ? <p className="product-error" role="alert">{error}</p> : null}
      {busy ? <p className="product-loading">Loading saved places…</p> : null}
      {!busy && !items.length ? <div className="product-empty"><h2>No saved spots yet</h2><p>Save a restaurant from Discovery to add it here.</p><a href="/discovery">Browse Discovery</a></div> : null}
      <div className="saved-grid">
        {items.map((item) => {
          const place = item.place_id ? places.get(item.place_id) : undefined;
          const membership = selected ? item.collections.find((entry) => entry.collection_id === selected) : item.collections[0];
          return <article className="saved-item" key={item.id}>
            {place ? <SuggestionCard description={place.address || place.reason} placeId={place.place_id} rating={place.rating} tags={place.tags} title={place.name} /> : <div className="legacy-save"><strong>{item.legacy_name || "Restaurant details unavailable"}</strong><p>{item.place_id ? "Google details could not be loaded. You can still remove this save." : "Legacy save — CraveAI will not guess its Place ID."}</p>{!item.place_id ? <a href="/discovery">Search in Discovery, save the current place, then remove this legacy entry</a> : null}</div>}
            {membership ? <label>Private note<textarea defaultValue={membership.note || ""} maxLength={1000} onBlur={(event) => void updateSavedNote(item.id, membership.collection_id, event.target.value).catch((reason) => setError(String(reason)))} /></label> : null}
            {item.place_id ? <div className="saved-collection-add"><select aria-label={`Add ${place?.name || "saved restaurant"} to collection`} onChange={(event) => setCollectionTargets((value) => ({ ...value, [item.id]: event.target.value }))} value={collectionTargets[item.id] || ""}><option value="">Add to collection…</option>{collections.filter((collection) => !item.collections.some((entry) => entry.collection_id === collection.id)).map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select><button disabled={!collectionTargets[item.id]} onClick={() => void addFavorite(item.place_id!, undefined, collectionTargets[item.id]).then(() => { window.dispatchEvent(new Event("craveai-favorites-changed")); return reload(); })}>Add</button></div> : null}
            <button className="danger-link" onClick={() => void deleteFavorite(item.id).then(() => { window.dispatchEvent(new Event("craveai-favorites-changed")); return reload(); })}>Remove</button>
          </article>;
        })}
      </div>
    </section>
  );
}

export function HistoryPage(): JSX.Element {
  const { user, loading: authLoading } = useAuth();
  const [items, setItems] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => listConversations().then(setItems).catch((reason) => setError(String(reason)));
  useEffect(() => { if (user) void load(); }, [user]);
  if (!authLoading && !user) return <SignInRequired title="Sign in to use History" />;
  return (
    <section className="product-page history-page">
      <header className="product-page-heading"><p>History</p><h1>Your conversations</h1><span>History is opt-in and stored until you delete it.</span></header>
      {error ? <p className="product-error">{error}</p> : null}
      <div className="history-layout">
        <aside>
          <button className="danger-link" onClick={() => void clearHistory().then(() => { setItems([]); setSelected(null); })}>Clear all</button>
          {items.map((item) => <div className="history-list-item" key={item.id}>
            <button onClick={() => void readConversation(item.id).then(setSelected)}>{item.title}<small>{new Date(item.updated_at).toLocaleDateString()}</small></button>
            <button aria-label={`Rename ${item.title}`} onClick={() => { const title = window.prompt("Conversation title", item.title); if (title) void renameConversation(item.id, title).then(load); }}>Rename</button>
            <button aria-label={`Delete ${item.title}`} onClick={() => void deleteConversation(item.id).then(() => { setSelected(null); return load(); })}>Delete</button>
          </div>)}
        </aside>
        <div className="history-detail">
          {selected ? <><div className="history-detail-heading"><h2>{selected.title}</h2><button onClick={() => reopenConversation(selected)}>Continue on Home</button></div>{selected.messages.map((message) => <article className={`history-message is-${message.role}`} key={message.id}><strong>{message.role === "user" ? "You" : "CraveAI"}</strong><p>{message.content}</p>{message.place_ids.length ? <small>{message.place_ids.length} restaurant reference{message.place_ids.length === 1 ? "" : "s"} will be refreshed when reopened.</small> : null}</article>)}</> : <div className="product-empty"><h2>Select a conversation</h2><p>Stored messages and Place-ID references appear here.</p></div>}
        </div>
      </div>
    </section>
  );
}

function reopenConversation(conversation: ConversationDetail): void {
  const messages = conversation.messages.slice(-24).map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
  }));
  window.sessionStorage.setItem(
    "craveai-temporary-chat",
    JSON.stringify({ messages, draft: "", conversationId: conversation.id }),
  );
  window.history.pushState({}, "", "/");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

const splitList = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);
const joinList = (value: string[]) => value.join(", ");

export function SettingsPage(): JSX.Element {
  const { user, loading: authLoading } = useAuth();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  useEffect(() => { if (user) void fetchPreferences().then((value) => { setPrefs(value); setForm({
    favorite_cuisines: joinList(value.favorite_cuisines),
    disliked_foods: joinList(value.disliked_foods),
    dietary_restrictions: joinList(value.dietary_restrictions),
    allergies: joinList(value.allergies),
    default_location_label: value.default_location?.label || "",
    default_location_lat: value.default_location ? String(value.default_location.lat) : "",
    default_location_lng: value.default_location ? String(value.default_location.lng) : "",
    dining_style: typeof value.recommendation_preferences.dining_style === "string" ? value.recommendation_preferences.dining_style : "",
  }); }); }, [user]);
  if (!authLoading && !user) return <SignInRequired title="Sign in to manage Settings" />;
  const save = async (event: FormEvent) => {
    event.preventDefault(); if (!prefs) return;
    const lat = Number(form.default_location_lat);
    const lng = Number(form.default_location_lng);
    const hasLocation = Boolean(form.default_location_label?.trim()) && Number.isFinite(lat) && Number.isFinite(lng);
    const next = await patchPreferences({
      ...prefs,
      favorite_cuisines: splitList(form.favorite_cuisines || ""),
      disliked_foods: splitList(form.disliked_foods || ""),
      dietary_restrictions: splitList(form.dietary_restrictions || ""),
      allergies: splitList(form.allergies || ""),
      default_location: hasLocation ? { label: form.default_location_label.trim(), lat, lng } : null,
      recommendation_preferences: { dining_style: form.dining_style?.trim() || "" },
    });
    setPrefs(next); setStatus("Settings saved.");
  };
  return (
    <section className="product-page settings-page">
      <header className="product-page-heading"><p>Settings</p><h1>Your CraveAI controls</h1><span>Optional sensitive preferences can be removed at any time.</span></header>
      {!prefs ? <p className="product-loading">Loading settings…</p> : <form onSubmit={(event) => void save(event)}>
        <section><h2>Recommendation preferences</h2>{[
          ["favorite_cuisines", "Favourite cuisines"], ["disliked_foods", "Disliked foods"], ["dietary_restrictions", "Dietary restrictions"], ["allergies", "Allergies"],
        ].map(([key, label]) => <label key={key}>{label}<input onChange={(event) => setForm((value) => ({ ...value, [key]: event.target.value }))} placeholder="Comma-separated" value={form[key] || ""} /></label>)}
          <p className="settings-warning">CraveAI cannot guarantee allergen safety. Always verify directly with the restaurant.</p>
          <label>Dining style or occasion<input onChange={(event) => setForm((value) => ({ ...value, dining_style: event.target.value }))} placeholder="Casual, date night, quiet…" value={form.dining_style || ""} /></label>
          <label className="toggle-row"><input checked={prefs.personalization_enabled} onChange={(event) => setPrefs({ ...prefs, personalization_enabled: event.target.checked })} type="checkbox" />Use saved preferences for recommendations</label>
        </section>
        <section><h2>History and accessibility</h2>
          <label className="toggle-row"><input checked={prefs.history_enabled} onChange={(event) => setPrefs({ ...prefs, history_enabled: event.target.checked })} type="checkbox" />Automatically save signed-in conversations</label>
          <label>Reduced motion<select onChange={(event) => setPrefs({ ...prefs, reduced_motion: event.target.value as Preferences["reduced_motion"] })} value={prefs.reduced_motion}><option value="system">Use system setting</option><option value="on">On</option><option value="off">Off</option></select></label>
          <label>Default radius<select onChange={(event) => setPrefs({ ...prefs, default_radius_meters: Number(event.target.value) })} value={prefs.default_radius_meters}><option value="2000">2 km</option><option value="5000">5 km</option><option value="10000">10 km</option><option value="20000">20 km</option></select></label>
          <fieldset className="default-location-fields"><legend>Optional default location</legend><label>Label<input onChange={(event) => setForm((value) => ({ ...value, default_location_label: event.target.value }))} placeholder="Downtown Toronto" value={form.default_location_label || ""} /></label><label>Latitude<input inputMode="decimal" onChange={(event) => setForm((value) => ({ ...value, default_location_lat: event.target.value }))} placeholder="43.6532" value={form.default_location_lat || ""} /></label><label>Longitude<input inputMode="decimal" onChange={(event) => setForm((value) => ({ ...value, default_location_lng: event.target.value }))} placeholder="-79.3832" value={form.default_location_lng || ""} /></label></fieldset>
        </section>
        <section><h2>Notifications</h2><label className="toggle-row"><input checked={Boolean(prefs.notification_preferences.product_updates)} onChange={(event) => setPrefs({ ...prefs, notification_preferences: { ...prefs.notification_preferences, product_updates: event.target.checked } })} type="checkbox" />Allow future product-update messages (none are sent yet)</label></section>
        <button className="primary-action" type="submit">Save settings</button>{status ? <span className="save-status">{status}</span> : null}
      </form>}
      <section className="privacy-actions"><h2>Privacy and data</h2>
        <button onClick={() => void exportAccount().then((data) => downloadJson("craveai-account-export.json", data))}>Export my data</button>
        <button onClick={() => void clearHistory().then(() => setStatus("History permanently deleted."))}>Clear History</button>
        <button onClick={() => void resetPersonalization().then(() => setStatus("Personalization reset."))}>Reset personalization</button>
        <button className="danger-button" onClick={() => { if (window.confirm("Permanently delete your CraveAI account and account-owned data?")) void deleteAccount().then(() => window.location.assign("/")); }}>Delete account</button>
      </section>
    </section>
  );
}

export function PricingPage(): JSX.Element {
  const [plans, setPlans] = useState<Plan[]>([]);
  useEffect(() => { void fetchPlans().then(setPlans).catch(() => undefined); }, []);
  return <section className="product-page pricing-page"><header className="product-page-heading"><p>Plans</p><h1>Simple access, clear limits</h1><span>Plus is disabled until cost validation is complete.</span></header><div className="plan-grid">{plans.map((plan) => <article className={plan.id === "free" ? "is-featured" : ""} key={plan.id}><p>{plan.name}</p><h2>{plan.coming_later ? "Coming later" : plan.price === 0 ? "$0" : "Included"}</h2>{plan.limits ? <dl>{Object.entries(plan.limits).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{key.includes("seconds") ? `${Math.round(value / 60)} min` : value}</dd></div>)}</dl> : null}<ul>{plan.features.map((feature) => <li key={feature}>{feature}</li>)}</ul><button disabled={!plan.available}>{plan.id === "guest" ? "Current guest access" : plan.id === "free" ? "Create a free account" : "Not available"}</button></article>)}</div></section>;
}

export function PolicyGate(): JSX.Element {
  const { refresh } = useAuth();
  const [current, setCurrent] = useState<LegalCurrent | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    void fetchLegalCurrent().then(setCurrent).catch(() => setError("Unable to load the current policies."));
  }, []);
  return (
    <div className="policy-gate-backdrop">
      <section aria-labelledby="policy-gate-title" aria-modal="true" className="policy-gate" role="dialog">
        <img alt="" src="/craveai-pin.svg" />
        <p>Policy update</p><h1 id="policy-gate-title">Review before continuing</h1>
        <span>CraveAI is an 18+ service. Material policy changes require a new acknowledgment before account features and AI chat can continue.</span>
        <label><input checked={accepted} onChange={(event) => setAccepted(event.target.checked)} type="checkbox" />I am 18 or older, agree to the current <a href="/terms" target="_blank">Terms</a>, and acknowledge the <a href="/privacy" target="_blank">Privacy Policy</a>.</label>
        {error ? <p className="product-error">{error}</p> : null}
        <button disabled={!accepted || !current} onClick={() => { if (current) void acceptCurrentPolicies(current).then(refresh).catch((reason) => setError(reason instanceof Error ? reason.message : "Acceptance failed.")); }}>Accept and continue</button>
      </section>
    </div>
  );
}

function SignInRequired({ title }: { title: string }): JSX.Element {
  return <section className="product-page"><div className="product-empty"><img alt="" src="/craveai-pin.svg" /><h1>{title}</h1><p>Account-owned data is available only after authentication.</p><a href="/login">Log in</a></div></section>;
}

function downloadJson(filename: string, data: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}
