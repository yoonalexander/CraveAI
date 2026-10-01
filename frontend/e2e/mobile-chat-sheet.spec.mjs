import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

test.beforeEach(async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 43.65, longitude: -79.38 });
  await page.addInitScript(() => sessionStorage.setItem("craveai-age-18", "true"));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user: null } }));
  await page.route("**/api/places/suggestions?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/chat/status", (route) => route.fulfill({ json: { usage: { limit: 9, used: 0, remaining: 9 } } }));
  await page.route("**/api/telemetry/startup", (route) => route.fulfill({ status: 204 }));
  await page.route("https://api.open-meteo.com/**", (route) => route.fulfill({ json: { current: { temperature_2m: 20, weather_code: 0, is_day: 1 } } }));
  await page.route("**/api/chat/stream", (route) => route.fulfill({ contentType: "text/event-stream", body: 'event: reply\ndata: {"reply":"Try a nearby noodle restaurant."}\n\n' }));
});

async function expectFooterSeparated(page, noticeSelector) {
  await expect(page.getByText(/^[89] messages left today$/)).toBeVisible();
  const meta = await page.locator(".chat-composer-meta").boundingBox();
  const notice = await page.locator(noticeSelector).boundingBox();
  expect(meta.y + meta.height).toBeLessThanOrEqual(notice.y);
  const sheet = await page.locator(".mobile-chat-sheet").boundingBox();
  expect(notice.y + notice.height).toBeLessThanOrEqual(sheet.y + sheet.height);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test("mobile quota and notices occupy separate rows in collapsed, expanded and active chat", async ({ page, hasTouch }, testInfo) => {
  test.skip(!hasTouch, "Mobile sheet layout");
  await page.goto("/");
  await expectFooterSeparated(page, ".chat-legal-notice");
  const directory = resolve("../.test-mobile-chat-tmp");
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-collapsed.png`) });
  await page.getByRole("button", { name: "Expand chat" }).tap();
  await expectFooterSeparated(page, ".chat-legal-notice");
  const composer = page.getByRole("textbox", { name: "Ask CraveAI" });
  await composer.fill("Noodles");
  await composer.press("Enter");
  await expect(page.getByText("Try a nearby noodle restaurant.")).toBeVisible();
  await expectFooterSeparated(page, ".chat-disclaimer");
  await page.getByRole("button", { name: "Collapse chat" }).tap();
  await expect(page.locator(".chat-disclaimer")).not.toBeVisible();
  await page.getByRole("button", { name: "Expand chat" }).tap();
  await expectFooterSeparated(page, ".chat-disclaimer");
});

test("touch dragging resizes the sheet while its bottom stays anchored", async ({ page, hasTouch }, testInfo) => {
  test.skip(!hasTouch, "Mobile touch gestures");
  await page.goto("/");
  await expect(page.getByText("9 messages left today", { exact: true })).toBeVisible();
  const sheet = page.locator(".mobile-chat-sheet");
  const before = await sheet.boundingBox();
  const handle = await page.locator(".mobile-sheet-grabber").boundingBox();
  const session = await page.context().newCDPSession(page);
  const x = Math.round(handle.x + handle.width / 2);
  const y = Math.round(handle.y + handle.height / 2);
  await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  await session.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y - 110 }] });
  await expect(sheet).toHaveClass(/is-dragging/);
  const during = await sheet.boundingBox();
  expect(during.y).toBeLessThan(before.y - 90);
  expect(Math.abs(during.y + during.height - before.y - before.height)).toBeLessThan(1);
  await expectFooterSeparated(page, ".chat-legal-notice");
  const directory = resolve("../.test-mobile-chat-tmp");
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, `${testInfo.project.name}-dragging.png`) });
  await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(page.getByRole("button", { name: "Collapse chat" })).toBeVisible();
  await expect(sheet).not.toHaveClass(/is-dragging/);
  const split = await page.locator(".home-split").boundingBox();
  await expect.poll(async () => Math.abs((await sheet.boundingBox()).y - split.y - 8)).toBeLessThan(1);
  const expanded = await sheet.boundingBox();
  await session.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: Math.round(expanded.y + 18) }] });
  await session.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: Math.round(expanded.y + 118) }] });
  await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await expect(page.getByRole("button", { name: "Expand chat" })).toBeVisible();
  await expectFooterSeparated(page, ".chat-legal-notice");
});
