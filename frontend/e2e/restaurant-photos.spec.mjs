import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const restaurants = Array.from({ length: 30 }, (_, i) => ({ place_id: `venue-${i}`, name: `Restaurant ${i}`, rating: 4.3, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));
test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: { user_id: "test-user", email: "test@example.com", email_verified: true, username: "food_explorer" } } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: restaurants }));
  await page.route("**/api/account/preferences", (route) => route.fulfill({ json: { preferences: { default_radius_meters: 5000, personalization_enabled: false, history_enabled: false } } }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 10, used: 0, remaining: 10 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/favorites/collections", (route) => route.fulfill({ json: { collections: [] } }));
  await page.route("**/api/favorites/saved*", (route) => route.fulfill({ json: { favorites: [{ id: "save", place_id: "venue-0", collections: [], created_at: "today" }] } }));
  await page.route("**/api/places/resolve", (route) => route.fulfill({ json: { places: [restaurants[0]] } }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
  await page.route("https://lh3.googleusercontent.com/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#567e40"/><circle cx="400" cy="300" r="150" fill="#ece1c6"/><text x="150" y="520" fill="#fff" font-size="28">Photo test fixture</text></svg>` }));
});

async function navigate(page, hasTouch, name) {
  if (hasTouch) await page.getByRole("button", { name: "Open navigation", exact: true }).tap();
  await page.getByRole("link", { name, exact: true }).click();
}

for (const theme of ["light", "dark"]) {
  test(`lazy previews, gallery, attribution and saved photos fit ${theme} layouts`, async ({ page, hasTouch }, testInfo) => {
    const calls = [];
    await page.route("**/api/places/photo", (route) => {
      const { place_id, index } = route.request().postDataJSON(); calls.push({ place_id, index });
      return route.fulfill({ json: { place_id, index, total: 3, photo: {
        uri: `https://lh3.googleusercontent.com/${place_id}-${index}`, source_uri: `https://maps.google.com/photo/${place_id}/${index}`, report_uri: "https://maps.google.com/report",
        authors: [{ name: `Contributor ${index}`, uri: "https://maps.google.com/contributor", avatar_uri: "https://lh3.googleusercontent.com/avatar" }, { name: "Second contributor", uri: null, avatar_uri: null }],
      } } });
    });
    await page.goto("/discovery");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const first = page.locator(".discovery-grid .suggestion-card").first();
    await expect(first.getByAltText("Google Maps photo of Restaurant 0")).toBeVisible();
    await expect(first.getByRole("link", { name: "Photo: Contributor 0" })).toBeVisible();
    await expect(first.getByText("Photo: Second contributor", { exact: true })).toBeVisible();
    await expect(first.getByRole("link", { name: "Google Maps", exact: true })).toHaveAttribute("href", "https://maps.google.com/photo/venue-0/0");
    expect(calls.length).toBeLessThan(restaurants.length);
    const open = first.getByRole("button", { name: "View photos of Restaurant 0" });
    await open.click();
    const gallery = page.getByRole("dialog", { name: "Photos of Restaurant 0" });
    await expect(gallery.getByRole("button", { name: "Previous photo" })).toBeDisabled();
    await expect(gallery.getByRole("button", { name: "Close photos" })).toBeFocused();
    await gallery.getByRole("button", { name: "Next photo" }).click();
    await expect(gallery.getByRole("status")).toHaveText("2 / 3");
    await expect(gallery.getByRole("img", { name: "Google Maps photo of Restaurant 0" })).toHaveAttribute("src", "https://lh3.googleusercontent.com/venue-0-1");
    await expect(gallery.getByRole("link", { name: "Photo: Contributor 1" })).toBeVisible();
    await expect(gallery.getByRole("link", { name: "Google Maps", exact: true })).toHaveAttribute("href", "https://maps.google.com/photo/venue-0/1");
    const next = gallery.getByRole("button", { name: "Next photo" });
    await next.focus(); await page.keyboard.press("Tab");
    await expect(gallery.getByRole("button", { name: "Close photos" })).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const box = await gallery.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(testInfo.project.use.viewport.width);
    const directory = resolve("../.test-issue23-browser-tmp"); await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-gallery.png`) });
    await page.keyboard.press("Escape");
    await expect(gallery).toHaveCount(0); await expect(open).toBeFocused();
    await navigate(page, hasTouch, "Likes");
    await expect(page.getByAltText("Google Maps photo of Restaurant 0")).toBeVisible();
    await page.getByRole("button", { name: "View photos of Restaurant 0" }).click();
    await expect(page.getByRole("dialog", { name: "Photos of Restaurant 0" })).toBeVisible();
    await page.getByRole("button", { name: "Close photos" }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-likes.png`) });
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain("googleusercontent.com");
  });
}

test("missing, broken and quota-limited photos stay usable without automatic retries", async ({ page }) => {
  const calls = [];
  await page.route("**/api/places/photo", (route) => {
    const { place_id } = route.request().postDataJSON(); calls.push(place_id);
    if (place_id === "venue-0") return route.fulfill({ json: { place_id, index: 0, total: 0, photo: null } });
    if (place_id === "venue-1") return route.fulfill({ json: { place_id, index: 0, total: 1, photo: { uri: "https://lh3.googleusercontent.com/broken", source_uri: null, report_uri: null, authors: [] } } });
    return route.fulfill({ status: 429, json: { detail: { code: "daily_places_request_quota_exceeded" } } });
  });
  await page.route("https://lh3.googleusercontent.com/broken", (route) => route.fulfill({ status: 404, body: "missing" }));
  await page.goto("/discovery");
  const cards = page.locator(".discovery-grid .suggestion-card");
  await expect(cards.nth(0).getByText("No photos available yet")).toBeVisible();
  await cards.nth(1).scrollIntoViewIfNeeded();
  await expect(cards.nth(1).getByText("This photo could not be loaded.")).toBeVisible();
  await expect(cards.nth(1).getByRole("button", { name: "Retry photos" })).toBeVisible();
  await cards.nth(2).scrollIntoViewIfNeeded();
  await expect(cards.nth(2).getByText("Photos are temporarily paused. Try again later.")).toBeVisible();
  await expect(cards.nth(2).getByRole("button", { name: "Retry photos" })).toHaveCount(0);
  expect(calls.filter((id) => id === "venue-0")).toHaveLength(1);
  expect(calls.filter((id) => id === "venue-1")).toHaveLength(1);
  expect(calls.filter((id) => id === "venue-2")).toHaveLength(1);
});
