import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const restaurants = Array.from({ length: 60 }, (_, index) => ({
  place_id: `pin-${index}`, name: `Restaurant ${index}`, rating: index === 59 ? null : 4.3,
  address: `${index} Main Street, Toronto`, reason: "Nearby", lat: 43.65 + index * .0001, lng: -79.38,
  price_level: index % 2 ? 3 : 1, open_now: index % 3 === 0,
}));
test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]); await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: restaurants }));
  await page.route("**/api/places/photo", (route) => route.fulfill({ json: { place_id: route.request().postDataJSON().place_id, total: 1, index: 0, photo: {
    uri: "https://lh3.googleusercontent.com/fixture", source_uri: "https://maps.google.com/photo", report_uri: null,
    authors: [{ name: "Contributor", uri: "https://maps.google.com/contributor", avatar_uri: null }],
  } } }));
  await page.route("https://lh3.googleusercontent.com/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="220"><rect width="600" height="220" fill="#d4dfc8"/><ellipse cx="300" cy="110" rx="130" ry="90" fill="#fff"/><ellipse cx="300" cy="110" rx="90" ry="60" fill="#68834e"/><text x="255" y="115" font-size="16">Test fixture</text></svg>` }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 3, used: 0, remaining: 3 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
});
const activate = (button, hasTouch) => hasTouch ? button.tap() : button.click();
for (const theme of ["light", "dark"]) {
  test(`browse all sixty map results, photos and shared filters without chat (${theme})`, async ({ page, hasTouch }, testInfo) => {
    let chatCalls = 0; let nearbyCalls = 0; const photoCalls = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/chat/stream")) chatCalls++;
      if (request.url().includes("/api/places/suggestions")) nearbyCalls++;
      if (request.url().includes("/api/places/photo")) photoCalls.push(request.postDataJSON().place_id);
    });
    await page.goto("/"); await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const view = page.getByRole("group", { name: "Restaurant view" });
    await expect(view.getByRole("button", { name: "List 60" })).toBeVisible();
    await activate(view.getByRole("button", { name: "List 60" }), hasTouch);
    const list = page.getByRole("region", { name: "Restaurants on this map" });
    await expect(list.getByRole("listitem")).toHaveCount(60);
    await expect(list.getByText(/All loaded pins, not just/)).toBeVisible();
    await expect(list.getByAltText("Google Maps photo of Restaurant 0")).toBeVisible();
    // The browser fixture intentionally has no Maps key; browsing still works.
    await expect(list.getByRole("button", { name: "Show Restaurant 0 on map" })).toBeDisabled();
    const firstLink = list.getByRole("listitem").first().getByRole("link", { name: "Open in Google Maps", exact: true });
    await expect(firstLink).toHaveAttribute("href", /query_place_id=pin-0/);
    const last = list.getByRole("listitem").last();
    await last.scrollIntoViewIfNeeded(); await expect(last.getByRole("heading", { name: "Restaurant 59" })).toBeVisible();
    await expect(last.getByText(/Rating unavailable/)).toBeVisible();
    expect(photoCalls.length).toBeLessThan(60);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const controlBox = await view.boundingBox(); expect(controlBox.height).toBeGreaterThanOrEqual(44);
    if (hasTouch) await expect(page.getByRole("textbox", { name: "Ask CraveAI" })).not.toBeVisible();
    await list.evaluate((element) => { element.scrollTop = 0; });
    const directory = resolve("../.test-issue27-browser-tmp"); await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-list.png`), fullPage: true });
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    await activate(toolbar.getByRole("button", { name: "Budget-friendly", exact: true }), hasTouch);
    await expect(list.getByRole("listitem")).toHaveCount(30); await expect(view.getByRole("button", { name: "List 30" })).toBeVisible();
    await activate(toolbar.getByRole("button", { name: "Open Now", exact: true }), hasTouch);
    await expect(list.getByRole("listitem")).toHaveCount(10); await expect(view.getByRole("button", { name: "List 10" })).toBeVisible();
    await activate(toolbar.getByRole("button", { name: "All", exact: true }), hasTouch);
    await expect(list.getByRole("listitem")).toHaveCount(60);
    await view.getByRole("button", { name: "List 60" }).focus(); await page.keyboard.press("Escape");
    await expect(view.getByRole("button", { name: "Map", exact: true })).toBeFocused();
    await expect(list).not.toBeVisible();
    if (hasTouch) await expect(page.getByRole("textbox", { name: "Ask CraveAI" })).toBeVisible();
    expect(chatCalls).toBe(0); expect(nearbyCalls).toBe(1);
  });
}

test("loading, empty and quota errors keep the list accessible and retry respects limits", async ({ page, hasTouch }) => {
  let release; let calls = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  await page.route("**/api/places/suggestions?**", async (route) => { calls++; if (calls === 1) { await pending; await route.fulfill({ status: 503, json: {} }); }
    else await route.fulfill({ status: 429, headers: { "x-ratelimit-reset": "2026-10-02T00:00:00Z" }, json: {} }); });
  await page.goto("/");
  await activate(page.getByRole("group", { name: "Restaurant view" }).getByRole("button", { name: "List 0" }), hasTouch);
  const list = page.getByRole("region", { name: "Restaurants on this map" });
  await expect(list.getByText(/Updating restaurants/)).toBeVisible();
  release(); await expect(list.getByRole("alert")).toContainText("couldn't search this area");
  await expect(list.getByRole("heading", { name: "Restaurants are unavailable" })).toBeVisible();
  await list.getByRole("button", { name: "Try again" }).click();
  await expect(list.getByRole("alert")).toContainText("limit has been reached");
  await expect(list.getByRole("button", { name: "Try again" })).toHaveCount(0);
  expect(calls).toBe(2);
});
