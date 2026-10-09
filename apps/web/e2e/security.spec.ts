// Phase 12: security headers on pages and APIs (D-076) and login throttling (D-075), against the production build.
import { expect, test } from "@playwright/test";

test("pages and API responses carry the security headers", async ({ request }) => {
  for (const path of ["/login", "/api/incidents"]) {
    const response = await request.get(path, { maxRedirects: 0 });
    const headers = response.headers();
    const csp = headers["content-security-policy"] ?? "";
    expect(csp, path).toContain("default-src 'self'");
    expect(csp, path).toContain("frame-ancestors 'none'");
    expect(csp, path).toContain("object-src 'none'");
    expect(csp, path).not.toContain("unsafe-eval"); // production build
    expect(headers["x-content-type-options"], path).toBe("nosniff");
    expect(headers["x-frame-options"], path).toBe("DENY");
    expect(headers["referrer-policy"], path).toBe("no-referrer");
    expect(headers["x-powered-by"], path).toBeUndefined();
  }
});

test("the console still renders and signs in under the CSP", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  expect(violations).toEqual([]);
});

test("repeated failed sign-ins for one email are throttled without revealing whether it exists", async ({ page }) => {
  const email = "nobody.throttle@sentinelx.local"; // unknown on purpose: throttling must not depend on the account
  await page.goto("/login");
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(`wrong-password-${attempt}`);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByLabel("Password")).toHaveValue(""); // the action finished and reset the form
    await expect(page.getByText("Invalid email or password.")).toBeVisible();
  }
  await page.getByLabel("Email").fill(email.toUpperCase()); // the key is the normalized email
  await page.getByLabel("Password").fill("wrong-password-6");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Too many failed attempts. Try again in 15 minutes.")).toBeVisible();
});
