/**
 * Browser end-to-end test of the client workflow (S4-09a).
 *
 * Against the running stack: the baseline run loads on its own, the map and
 * ranked shortlist appear, a shortlist row opens its site detail, an edited
 * weight re-runs the analysis under a new run id, and the shortlist exports as
 * CSV. A second test checks that an extreme weight is refused before any run
 * (QA F-07). Only visible UI is used — no API calls are made from the test.
 */
import { expect, test, type Page } from "@playwright/test";

function region(page: Page, name: string) {
  return page.getByRole("region", { name });
}

async function waitForBaseline(page: Page): Promise<string> {
  await page.goto("/");
  const rows = region(page, "Ranked results").locator("tbody tr");
  await expect(rows.first()).toBeVisible();
  const runId = region(page, "Analysis controls").locator("code").first();
  await expect(runId).not.toBeEmpty();
  return (await runId.textContent()) ?? "";
}

test("baseline run → map, shortlist, site detail, re-run, CSV export", async ({ page }) => {
  const baselineRunId = await waitForBaseline(page);

  // Map renders (a MapLibre canvas inside the map container).
  await expect(page.getByLabel("Interactive cell map").locator("canvas").first()).toBeVisible();

  // The shortlist is ranked from 1, and row 1 opens its site detail.
  const shortlist = region(page, "Ranked results");
  const firstRow = shortlist.locator("tbody tr").first();
  await expect(firstRow.locator("td").first()).toHaveText("1");
  const cellId = ((await firstRow.locator("code").textContent()) ?? "").trim();
  expect(cellId).toMatch(/^S\d+\.\d+_E\d+\.\d+$/);
  await firstRow.click();
  const detail = region(page, "Site detail and explanation");
  await expect(detail.getByText(cellId)).toBeVisible();
  await expect(detail.getByText("Eligible candidate", { exact: true })).toBeVisible();

  // Edit a weight and re-run: a different weight set gives a different run id.
  const controls = region(page, "Analysis controls");
  await controls.getByLabel("Wind speed weight").fill("0.6");
  await controls.getByRole("button", { name: /run analysis/i }).click();
  await expect(controls.locator("code").first()).not.toHaveText(baselineRunId);
  await expect(shortlist.locator("tbody tr").first()).toBeVisible();

  // Export the shortlist as CSV.
  const downloadPromise = page.waitForEvent("download");
  await shortlist.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.csv$/);
  const path = await download.path();
  const { readFile } = await import("node:fs/promises");
  const header = (await readFile(path, "utf-8")).split(/\r?\n/)[0] ?? "";
  expect(header).toContain("cell_id");
});

test("an extreme weight is refused before any run (QA F-07)", async ({ page }) => {
  await waitForBaseline(page);
  const controls = region(page, "Analysis controls");
  await controls.getByLabel("Wind speed weight").fill("1e308");
  await expect(controls.getByRole("alert")).toContainText(/at most 100/i);
  await expect(controls.getByRole("button", { name: /run analysis/i })).toBeDisabled();
});
