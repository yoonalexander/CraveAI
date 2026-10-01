import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const restaurants = [
  { place_id: "sushi", name: "Sushi Spot", cuisine_labels: [{ value: "Japanese", source: "google", evidence: [] }] },
  { place_id: "pasta", name: "Pasta Spot", cuisine_labels: [{ value: "Italian", source: "inferred_menu", evidence: [{ id: "pasta", label: "Pasta menu", source_url: "https://restaurant.example/menu" }] }] },
  { place_id: "other", name: "New Spot", tags: ["Ethiopian"] },
].map((place) => ({ tags: ["Restaurant"], ...place, open_now: true, rating: 4.2, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));

test.beforeEach(async ({ page, context }) => {
  await page.route("**/api/discovery/signals?**", (route) => route.fulfill({ json: { status: "pending", items: [], region: "Toronto & GTA", coverage: ["Toronto & GTA"], expires_at: null } }));
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: restaurants }));
  await page.route("**/api/places/photo", (route) => route.fulfill({ json: { place_id: route.request().postDataJSON().place_id, index: 0, total: 0, photo: null } }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 3, used: 0, remaining: 3 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
});

const activate = (button, hasTouch) => hasTouch ? button.tap() : button.click();
const appearance = (button) => button.evaluate((node) => {
  const style = getComputedStyle(node);
  return { background: style.backgroundColor, color: style.color, border: style.borderColor };
});
async function capture(page, testInfo, theme, surface) {
  const directory = resolve("../.test-issue25-browser-tmp");
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-${surface}.png`), fullPage: true });
}

for (const theme of ["light", "dark"]) {
  test(`cuisine art preserves loading, touch, hover, keyboard and advanced filter states (${theme})`, async ({ page, hasTouch }, testInfo) => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    await page.route("**/api/places/suggestions?**", async (route) => { await pending; await route.fulfill({ json: restaurants }); });
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    const choices = page.getByRole("group", { name: "Cuisine filters" });
    const japanese = choices.getByRole("button", { name: "Japanese", exact: true });
    await expect(japanese).toBeDisabled();
    await expect(japanese).toHaveCSS("opacity", "0.5");
    await expect(choices.getByRole("button")).toHaveCount(19);
    expect(await choices.locator("svg:not([aria-hidden='true'])").count()).toBe(0);
    expect(await choices.locator("svg:not([focusable='false'])").count()).toBe(0);
    release();
    await expect(toolbar).toContainText("3 restaurants in this area");
    await expect(japanese).toBeEnabled();
    await capture(page, testInfo, theme, "home");
    await japanese.scrollIntoViewIfNeeded();
    const plain = await appearance(japanese);
    if (!hasTouch) { await japanese.hover(); expect(await appearance(japanese)).not.toEqual(plain); }
    await activate(japanese, hasTouch);
    await expect(japanese).toHaveAttribute("aria-pressed", "true");
    const selected = await appearance(japanese);
    await expect(toolbar).toContainText("1 of 3 loaded restaurants shown");
    await activate(japanese, hasTouch);
    await expect(japanese).toHaveAttribute("aria-pressed", "false");
    expect(await appearance(japanese)).not.toEqual(selected);
    await japanese.focus();
    await page.keyboard.press("Space");
    await expect(japanese).toHaveAttribute("aria-pressed", "true");
    await expect(japanese).toHaveCSS("outline-style", "solid");
    await expect(japanese).toHaveCSS("outline-width", "2px");
    const icon = await japanese.locator("svg").boundingBox();
    expect(icon.width).toBe(28); expect(icon.height).toBe(28);
    await capture(page, testInfo, theme, "selected");
    await activate(toolbar.getByRole("button", { name: /^Filters/ }), hasTouch);
    const dialog = page.getByRole("dialog", { name: "Find the right restaurant" });
    await expect(dialog.getByLabel("Cuisine", { exact: true })).toHaveValue("Japanese");
    await expect(dialog.locator(".cuisine-select svg")).toHaveAttribute("data-food-icon", "sushi");
    await dialog.getByLabel("Cuisine", { exact: true }).selectOption("Italian");
    await expect(dialog.locator(".cuisine-select svg")).toHaveAttribute("data-food-icon", "pasta");
    await dialog.getByRole("button", { name: "Show results" }).click();
    await expect(choices.getByRole("button", { name: "Italian", exact: true })).toHaveAttribute("aria-pressed", "true");
    await activate(choices.getByRole("button", { name: "Any cuisine", exact: true }), hasTouch);
    await expect(toolbar).toContainText("3 restaurants in this area");
    const vietnamese = choices.getByRole("button", { name: "Vietnamese", exact: true });
    await activate(vietnamese, hasTouch);
    await expect(vietnamese).toHaveAttribute("aria-pressed", "true");
    await expect(toolbar).toContainText("0 of 3 loaded restaurants shown");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });

  test(`Discovery food tags preserve photos, source labels and unknown cuisine fallback (${theme})`, async ({ page, hasTouch }, testInfo) => {
    await page.goto("/discovery");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const sushi = page.locator("article").filter({ has: page.getByRole("heading", { name: "Sushi Spot", exact: true }) });
    await expect(sushi.locator(".restaurant-food-tag")).toHaveText("Japanese");
    await expect(sushi.locator(".restaurant-food-tag svg")).toHaveAttribute("data-food-icon", "sushi");
    await expect(sushi.getByRole("link", { name: "View on Google Maps" })).toBeVisible();
    const other = page.locator("article").filter({ has: page.getByRole("heading", { name: "New Spot", exact: true }) });
    await expect(other.locator(".restaurant-food-tag")).toHaveText("Ethiopian");
    await expect(other.locator(".restaurant-food-tag svg")).toHaveAttribute("data-food-icon", "plate");
    const pasta = page.locator("article").filter({ has: page.getByRole("heading", { name: "Pasta Spot", exact: true }) });
    await pasta.getByText("Label sources", { exact: true }).click();
    await expect(pasta.getByRole("link", { name: "Pasta menu", exact: true })).toHaveAttribute("href", "https://restaurant.example/menu");
    const tagBox = await sushi.locator(".restaurant-food-tag").boundingBox();
    const cardBox = await sushi.boundingBox();
    expect(tagBox.x).toBeGreaterThanOrEqual(cardBox.x);
    expect(tagBox.x + tagBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
    expect(tagBox.y + tagBox.height).toBeLessThanOrEqual(cardBox.y + cardBox.height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await capture(page, testInfo, theme, "discovery");
    await sushi.screenshot({ path: resolve("../.test-issue25-browser-tmp", `${testInfo.project.name}-${theme}-card.png`) });
    await activate(page.getByRole("group", { name: "Cuisine filters" }).getByRole("button", { name: "Mexican", exact: true }), hasTouch);
    await expect(page.getByRole("heading", { name: "No spots to show yet" })).toBeVisible();
    await expect(page.locator(".discovery-empty > svg")).toHaveAttribute("data-food-icon", "plate");
  });
}
