import { expect, test } from "@playwright/test";

test.describe("AI Manga Factory sample control tower", () => {
  test("loads in sample mode and supports primary navigation", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByTestId("workspace-mode")).toHaveText("sample");
    await expect(page.getByTestId("hero-project-name")).toContainText("斗气");

    await page.getByTestId("nav-monitoring").click();
    await expect(page.getByTestId("page-monitoring")).toBeVisible();
    await expect(page.getByTestId("monitoring-alert-count")).toContainText("1");

    await page.getByTestId("nav-settings").click();
    await expect(page.getByTestId("page-settings")).toBeVisible();
    await expect(page.getByTestId("auth-state")).toContainText("enabled");
  });
});
