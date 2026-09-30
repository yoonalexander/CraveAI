import { expect, test as base } from "@playwright/test";
import { createServer } from "node:http";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

// A real, gated SSE response exercises fetch streaming and abort in the browser.
// route.fulfill would deliver all stages at once and miss the transitions.
const test = base.extend({
  stream: async ({ page }, use) => {
    const responses = [];
    const server = createServer((request, response) => {
      response.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:4175");
      response.setHeader("Access-Control-Allow-Credentials", "true");
      response.setHeader("Access-Control-Allow-Headers", "Content-Type, Accept");
      response.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
      if (request.method === "OPTIONS") { response.writeHead(204); response.end(); return; }
      request.resume();
      response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
      response.flushHeaders();
      responses.push(response);
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const url = `http://127.0.0.1:${server.address().port}/api/chat/stream`;
    await page.route("**/api/chat/stream", (route) => route.continue({ url }));
    await use({
      responses,
      send: (event, data) => responses.at(-1)?.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
      finish: () => responses.at(-1)?.end(),
    });
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  },
});

test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.addInitScript(() => sessionStorage.setItem("craveai-age-18", "true"));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 3, used: 0, remaining: 3 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
});

async function ask(page, stream, text) {
  const composer = page.getByRole("textbox", { name: "Ask CraveAI" });
  await composer.fill(text); await composer.press("Enter");
  await expect.poll(() => stream.responses.length).toBeGreaterThan(0);
  await expect(page.locator(".chat-thinking")).toBeVisible();
}

for (const theme of ["light", "dark"]) for (const reduced of [false, true]) {
  test(`slow stages stay animated, readable and stable (${theme}, ${reduced ? "reduced" : "normal"} motion)`, async ({ page, stream }, testInfo) => {
    await page.emulateMedia({ reducedMotion: reduced ? "reduce" : "no-preference" });
    await page.goto("/");
    await page.evaluate((theme) => document.documentElement.classList.add(theme), theme);
    await ask(page, stream, "Find a cozy noodle spot");
    const progress = page.locator(".chat-thinking");
    const status = progress.getByRole("status");
    await expect(status).toHaveText("Getting your search ready…");
    await expect(status).toHaveAttribute("aria-live", "polite");
    await expect(progress.locator(".chat-thinking-dots")).toHaveAttribute("aria-hidden", "true");
    await expect(progress.locator("i").first()).toHaveCSS("animation-name", reduced ? "none" : "thinking");
    // Let the existing first-message composer/sheet transition finish before
    // measuring stage changes; the staged response itself remains held open.
    await page.waitForTimeout(550);
    const initial = await progress.boundingBox();
    const composer = await page.locator(".chat-composer").boundingBox();
    await progress.evaluate((node) => { node.querySelector(".chat-thinking-dots").dataset.session = "initial"; });
    for (const message of ["Understanding your craving", "Searching restaurants in the confirmed area", "Checking attributable menu evidence", "Comparing evidence with your constraints", "Ranking the verified nearby matches"]) {
      stream.send("stage", { message });
      await expect(status).toHaveText(message);
      await expect(progress.locator(".chat-thinking-dots")).toHaveAttribute("data-session", "initial");
      await expect(progress.locator("i").first()).toHaveCSS("animation-name", reduced ? "none" : "thinking");
      if (!reduced) await expect(progress.locator("i").first()).toHaveCSS("animation-iteration-count", "infinite");
      await expect(progress.locator(".chat-progress-message")).toHaveCSS("animation-name", reduced ? "none" : "chat-stage-enter");
      await page.waitForTimeout(300); // Keep each streamed stage visible through its transition.
      const bounds = await progress.boundingBox();
      expect(Math.abs(bounds.height - initial.height)).toBeLessThan(1);
      expect(Math.abs(bounds.y - initial.y)).toBeLessThan(1);
      const nextComposer = await page.locator(".chat-composer").boundingBox();
      expect(Math.abs(nextComposer.y - composer.y)).toBeLessThan(1);
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(testInfo.project.use.viewport.width);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    const directory = resolve("../.test-issue24-browser-tmp"); await mkdir(directory, { recursive: true });
    await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-${theme}-${reduced ? "reduced" : "normal"}.png`) });
    stream.send("reply", { reply: "Here are your noodle spots." }); stream.finish();
    await expect(page.getByText("Here are your noodle spots.")).toBeVisible();
    await expect(progress).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Ask CraveAI" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Stop response" })).toHaveCount(0);
  });
}

test("stopping a stream and retrying after an error clears and resets progress", async ({ page, stream }) => {
  await page.goto("/");
  await ask(page, stream, "First request");
  stream.send("stage", { message: "Checking menus…" });
  await expect(page.getByText("Checking menus…")).toBeVisible();
  await page.getByRole("button", { name: "Stop response" }).click();
  await expect(page.locator(".chat-thinking")).toHaveCount(0);
  await expect(page.getByText("Response stopped.")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Ask CraveAI" })).toBeFocused();
  await expect.poll(() => stream.responses[0].destroyed).toBe(true);
  await ask(page, stream, "Second request");
  await expect.poll(() => stream.responses.length).toBe(2);
  await expect(page.getByText("Getting your search ready…")).toBeVisible();
  stream.send("stage", { message: "Finding nearby restaurants…" });
  await expect(page.getByText("Finding nearby restaurants…")).toBeVisible();
  stream.send("error", { status: 500, detail: { code: "provider_failed" } }); stream.finish();
  await expect(page.locator(".chat-thinking")).toHaveCount(0);
  await expect(page.getByRole("alert")).toBeVisible();
  await ask(page, stream, "Try again");
  await expect.poll(() => stream.responses.length).toBe(3);
  await expect(page.getByText("Getting your search ready…")).toBeVisible();
  stream.send("reply", { reply: "Fresh recommendations." }); stream.finish();
  await expect(page.getByText("Fresh recommendations.")).toBeVisible();
  await expect(page.locator(".chat-thinking")).toHaveCount(0);
});
