import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const restaurants = [
  { place_id: "cheap-open", name: "Cheap Open", price_level: 1, open_now: true, tags: ["Japanese"] },
  { place_id: "cheap-closed", name: "Cheap Closed", price_level: 1, open_now: false, tags: ["Italian"] },
  { place_id: "costly-open", name: "Costly Open", price_level: 3, open_now: true, tags: ["Italian"] },
  { place_id: "unknown", name: "Unknown Data", tags: ["Japanese"] },
].map((place) => ({ ...place, rating: 4.2, address: "Test Street", reason: "Nearby", lat: 43.65, lng: -79.38 }));

test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: restaurants }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 3, used: 0, remaining: 3 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
});

const activate = (button, hasTouch) => hasTouch ? button.tap() : button.click();
const appearance = (button) => button.evaluate((node) => {
  const style = getComputedStyle(node);
  return { background: style.backgroundColor, color: style.color, border: style.borderColor };
});

for (const theme of ["light", "dark"]) {
  test(`details coverage and menu labels keep shared filters predictable (${theme})`, async ({ page, hasTouch }, testInfo) => {
    let detailsCalls = 0;
    await page.route("**/api/places/filter-data", async (route) => {
      detailsCalls++;
      expect(route.request().postDataJSON().place_ids).toHaveLength(4);
      await route.fulfill({ json: { places: restaurants.map((place, index) => ({
        place_id: place.place_id, enrichment_status: "checked", takeout: index === 0 ? true : index === 1 ? false : null,
        cuisine_labels: index === 0 ? [{ value: "Japanese", source: "google", evidence: [] }] : [],
        menu_status: index === 0 ? "assessed" : "no_evidence",
        dietary_labels: index === 0 ? [{ value: "vegan", source: "inferred_menu", evidence: [{ id: "dish", label: "Vegan ramen", source_url: "https://restaurant.example/menu" }] }] : [],
      })) } });
    });
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    await expect(toolbar).toContainText("4 restaurants in this area");
    await activate(toolbar.getByRole("button", { name: "Filters", exact: true }), hasTouch);
    const dialog = page.getByRole("dialog", { name: "Find the right restaurant" });
    await dialog.getByLabel(/^Takeout/).check();
    await dialog.getByLabel("vegan", { exact: true }).check();
    await dialog.getByRole("button", { name: "Show results" }).click();
    await expect(toolbar).toContainText("0 of 4 loaded restaurants shown");
    expect(detailsCalls).toBe(0);
    await activate(toolbar.getByRole("button", { name: "Check next 4 restaurants" }), hasTouch);
    await expect(toolbar).toContainText("1 of 4 loaded restaurants shown");
    await expect(toolbar).toContainText("4 of 4 details checked");
    await expect(toolbar).toContainText("1 official menus assessed");
    await activate(toolbar.getByRole("button", { name: /^Filters/ }), hasTouch);
    await expect(dialog.getByLabel(/^Takeout/)).toBeChecked();
    await expect(dialog.getByLabel(/^Takeout/)).toHaveCount(1);
    await dialog.getByLabel("Include labels inferred from official menus").uncheck();
    await dialog.getByRole("button", { name: "Show results" }).click();
    await expect(toolbar).toContainText("0 of 4 loaded restaurants shown");
    await activate(toolbar.getByRole("button", { name: "Remove Google labels only filter" }), hasTouch);
    await expect(toolbar).toContainText("1 of 4 loaded restaurants shown");
    if (hasTouch) await page.getByRole("button", { name: "Open navigation", exact: true }).tap();
    await page.getByRole("link", { name: "Discovery", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Cheap Open", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Unknown Data", exact: true })).toHaveCount(0);
    await page.getByText("Label sources", { exact: true }).click();
    await expect(page.getByRole("link", { name: "Vegan ramen", exact: true })).toHaveAttribute("href", "https://restaurant.example/menu");
    await expect(page.getByText("1 of 1 filtered restaurants in this collection")).toBeVisible();
    expect(detailsCalls).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const directory = resolve("../.test-issue22-browser-tmp");
    await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}.png`), fullPage: true });
  });

  test(`deselecting a hovered/tapped filter removes its selected appearance (${theme})`, async ({ page, hasTouch }) => {
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    await expect(toolbar).toContainText("4 restaurants in this area");
    const open = toolbar.getByRole("button", { name: "Open Now", exact: true });
    await activate(open, hasTouch);
    await expect(open).toHaveAttribute("aria-pressed", "true");
    const selected = await appearance(open);
    await activate(open, hasTouch);
    await expect(open).toHaveAttribute("aria-pressed", "false");
    await expect(toolbar.getByRole("button", { name: "All", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(toolbar).toContainText("4 restaurants in this area");
    expect(await appearance(open)).not.toEqual(selected);
  });

  test(`rapid toggles stay consistent during loading and after results arrive (${theme})`, async ({ page, hasTouch }) => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    await page.route("**/api/places/suggestions?**", async (route) => {
      await pending;
      await route.fulfill({ json: restaurants });
    });
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    const open = toolbar.getByRole("button", { name: "Open Now", exact: true });
    const budget = toolbar.getByRole("button", { name: "Budget-friendly", exact: true });
    await expect(toolbar).toContainText("Finding restaurants…");
    for (let i = 0; i < 7; i++) await activate(open, hasTouch);
    await activate(budget, hasTouch);
    await activate(budget, hasTouch);
    await expect(open).toHaveAttribute("aria-pressed", "true");
    await expect(budget).toHaveAttribute("aria-pressed", "false");
    release();
    await expect(toolbar).toContainText("2 of 4 loaded restaurants shown");
    const selected = await appearance(open);
    // A burst in one event turn also exercises React's queued state updates.
    await page.evaluate(() => {
      const buttons = [...document.querySelectorAll('.search-filter-scroll button')];
      const open = buttons.find((button) => button.textContent.trim() === "Open Now");
      const budget = buttons.find((button) => button.textContent.trim() === "Budget-friendly");
      for (let i = 0; i < 20; i++) { budget.click(); open.click(); budget.click(); open.click(); }
      open.click();
    });
    await expect(open).toHaveAttribute("aria-pressed", "false");
    await expect(budget).toHaveAttribute("aria-pressed", "false");
    await expect(toolbar).toContainText("4 restaurants in this area");
    expect(await appearance(open)).not.toEqual(selected);
    expect(await appearance(budget)).not.toEqual(selected);

    await activate(budget, hasTouch);
    await activate(open, hasTouch);
    await expect(toolbar).toContainText("1 of 4 loaded restaurants shown");
    await activate(toolbar.getByRole("button", { name: "All", exact: true }), hasTouch);
    await expect(toolbar).toContainText("4 restaurants in this area");
    await expect(open).toHaveAttribute("aria-pressed", "false");
    await expect(budget).toHaveAttribute("aria-pressed", "false");
  });

  test(`advanced apply/cancel/clear and Discovery agree with quick filters (${theme})`, async ({ page, hasTouch }) => {
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    const toolbar = page.getByRole("region", { name: "Restaurant search controls" });
    await expect(toolbar).toContainText("4 restaurants in this area");
    const more = toolbar.getByRole("button", { name: "Filters", exact: true });
    await activate(more, hasTouch);
    const dialog = page.getByRole("dialog", { name: "Find the right restaurant" });
    await dialog.getByLabel("Minimum rating").selectOption("4.5");
    await dialog.getByRole("button", { name: "Close filters" }).click();
    await expect(toolbar).toContainText("4 restaurants in this area");
    await expect(more).toHaveAttribute("aria-expanded", "false");
    await activate(more, hasTouch);
    await expect(dialog.getByLabel("Minimum rating")).toHaveValue("0");
    await dialog.getByLabel("Minimum rating").selectOption("4.5");
    await dialog.getByRole("button", { name: "Show results" }).click();
    await expect(toolbar).toContainText("0 of 4 loaded restaurants shown");
    await activate(toolbar.getByRole("button", { name: "Budget-friendly", exact: true }), hasTouch);
    await activate(toolbar.getByRole("button", { name: "Clear filters", exact: true }), hasTouch);
    await expect(toolbar).toContainText("4 restaurants in this area");
    await expect(toolbar.getByRole("button", { name: "Budget-friendly", exact: true })).toHaveAttribute("aria-pressed", "false");
    await activate(more, hasTouch);
    await expect(dialog.getByLabel("Minimum rating")).toHaveValue("0");
    await dialog.getByLabel("Cuisine").selectOption("Japanese");
    await dialog.getByRole("button", { name: "Reset advanced filters", exact: true }).click();
    await expect(dialog.getByLabel("Cuisine")).toHaveValue("");
    await dialog.getByRole("button", { name: "Show results" }).click();
    await expect(toolbar).toContainText("4 restaurants in this area");

    if (hasTouch) await page.getByRole("button", { name: "Open navigation", exact: true }).tap();
    await page.getByRole("link", { name: "Discovery", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Unknown Data", exact: true })).toBeVisible();
    await activate(toolbar.getByRole("button", { name: "Budget-friendly", exact: true }), hasTouch);
    await expect(page.getByRole("heading", { name: "Cheap Open", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Cheap Closed", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Costly Open", exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Unknown Data", exact: true })).toHaveCount(0);
    await activate(toolbar.getByRole("button", { name: "All", exact: true }), hasTouch);
    await expect(page.getByRole("heading", { name: "Costly Open", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Unknown Data", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
