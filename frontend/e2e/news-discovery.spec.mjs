import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

function snapshot() {
  const now = Date.now(); const future = new Date(now + 86400000).toISOString();
  return { status: "ready", region: "Toronto & GTA", coverage: ["Toronto & GTA"], checked_at: new Date(now).toISOString(), expires_at: future, refresh_due_at: future,
    items: ["newly_opened", "trending", "recently_spotted"].map((label, i) => ({
      place_id: `news-${i}`, name: ["Hearth Table", "Nori Room", "Market Kitchen"][i], city: "Toronto", address: null, label,
      opening_date: new Date(now - 10 * 86400000).toISOString().slice(0, 10), publisher_count: label === "trending" ? 2 : 1, expires_at: future,
      sources: (label === "trending" ? ["cbc.ca", "thestar.com"] : ["cbc.ca"]).map((publisher) => ({ url: `https://${publisher}/food/news-${i}`, publisher,
        published_at: null, observed_at: new Date(now - 86400000).toISOString(), evidence: `${["Hearth Table", "Nori Room", "Market Kitchen"][i]} brings something new to Toronto` })),
    })) };
}
test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]); await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/discovery/signals?**", (route) => route.fulfill({ json: snapshot() }));
  await page.route("**/api/places/photo", (route) => {
    const { place_id } = route.request().postDataJSON();
    return route.fulfill({ json: { place_id, index: 0, total: 1, photo: { uri: `https://lh3.googleusercontent.com/${place_id}`, source_uri: "https://maps.google.com/photo", report_uri: null,
      authors: [{ name: "Photo contributor", uri: "https://maps.google.com/contributor", avatar_uri: null }] } } });
  });
  await page.route("https://lh3.googleusercontent.com/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"><rect width="800" height="400" fill="#d8ccb8"/><circle cx="400" cy="200" r="150" fill="#fff"/><circle cx="400" cy="200" r="110" fill="#608052"/><text x="325" y="205" font-size="20">Test fixture</text></svg>` }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 3, used: 0, remaining: 3 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
});

for (const theme of ["light", "dark"]) {
  test(`news sources, dates, photos and map navigation fit ${theme} layouts`, async ({ page }, testInfo) => {
    const lookups = []; let chats = 0;
    await page.route("**/api/chat/stream", (route) => { chats++; return route.abort(); });
    await page.route("**/api/places/resolve", (route) => {
      lookups.push(route.request().postDataJSON());
      return route.fulfill({ json: { places: [{ place_id: "news-0", name: "Hearth Table", rating: null, address: "10 Main Street", reason: "News", lat: 43.66, lng: -79.4 }] } });
    });
    await page.goto("/discovery"); await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const section = page.getByRole("region", { name: "New places. New reasons to go." });
    await expect(section.locator("article")).toHaveCount(3);
    await expect(section.getByText("Newly opened", { exact: true })).toBeVisible();
    const hearth = section.locator("article").first();
    await expect(hearth.getByAltText("Google Maps photo of Hearth Table")).toBeVisible();
    await expect(hearth.getByRole("link", { name: "Photo: Photo contributor" })).toBeVisible();
    await expect(hearth.getByRole("link", { name: "cbc.ca" })).toHaveAttribute("href", "https://cbc.ca/food/news-0");
    await expect(hearth.getByText(/First indexed/)).toBeVisible();
    await expect(section.getByText("2 independent publisher groups in the past 14 days")).toBeVisible();
    await section.getByText("How these picks qualify", { exact: true }).click();
    await expect(section.getByText(/Newly opened requires/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    for (const card of await section.locator("article").all()) {
      const box = await card.boundingBox();
      const button = await card.getByRole("button", { name: /^Show on map/ }).boundingBox();
      expect(button.height).toBeGreaterThanOrEqual(44); expect(button.x + button.width).toBeLessThanOrEqual(box.x + box.width);
    }
    const directory = resolve("../.test-issue26-browser-tmp"); await mkdir(directory, { recursive: true });
    await section.evaluate((node) => { for (let parent = node.parentElement; parent; parent = parent.parentElement) parent.scrollTop = 0; });
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-news.png`), fullPage: true });
    await hearth.getByRole("button", { name: "Show on map Hearth Table" }).click();
    await expect(page).toHaveURL(/\/$/); expect(lookups).toEqual([{ place_ids: ["news-0"] }]); expect(chats).toBe(0);
  });
}

test("unavailable and expired source snapshots hide badges while nearby discovery remains usable", async ({ page }) => {
  const data = snapshot(); data.status = "unavailable";
  await page.route("**/api/discovery/signals?**", (route) => route.fulfill({ json: data }));
  await page.goto("/discovery");
  const section = page.getByRole("region", { name: "New places. New reasons to go." });
  await expect(section.getByRole("status")).toContainText("Older picks are hidden");
  await expect(section.locator("article")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Cuisine filters" })).toBeVisible();
  data.status = "ready"; data.expires_at = new Date(Date.now() - 1000).toISOString();
  await page.reload(); await expect(section.getByRole("status")).toContainText("Older picks are hidden");
  await expect(section.locator("article")).toHaveCount(0);
});
