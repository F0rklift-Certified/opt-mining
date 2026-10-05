import { test, expect } from "@playwright/test";

/** Real Docker API/data → browser; no route mocks or synthetic ranking values. */
test("full NSW screening demo reconciles with the decision service", async ({ page, request }) => {
  const api = process.env.E2E_API_URL ?? "http://localhost:8000";
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByText("Data-quality checks passed", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeEnabled();
  const handleResponse = await request.post(`${api}/runs`, { data: { scenario: "wind_led" } });
  expect(handleResponse.ok()).toBeTruthy();
  const handle = await handleResponse.json();
  const rows = await (await request.get(`${api}/runs/${handle.run_id}/results?top_n=10`)).json();
  const shortlist = page.getByRole("region", { name: "Ranked results" });
  const detail = page.getByRole("region", { name: "Site detail / explanation", exact: true });
  await expect(shortlist.getByRole("button", { name: new RegExp(rows[0].cell_id) })).toBeVisible();
  await expect(detail.getByRole("code").filter({ hasText: rows[0].cell_id })).toBeVisible();
  const canvas = page.getByRole("img", { name: "NSW eligible and excluded screening cells" });
  await expect(canvas).toBeVisible();
  // The real canvas contains drawing, not the old placeholder.
  expect(await canvas.evaluate((node) => {
    const canvas = node as HTMLCanvasElement;
    const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let eligible = 0;
    for (let i = 0; i < pixels.length; i += 4) if (pixels[i] === 36 && pixels[i + 1] === 120) eligible++;
    return eligible;
  })).toBeGreaterThan(100);
  const site = await (await request.get(`${api}/runs/${handle.run_id}/sites/${rows[0].cell_id}`)).json();
  await expect(detail.getByText(site.explanation.headline, { exact: true })).toBeVisible();
  for (const phrase of site.explanation.positive_factors) await expect(detail.getByText(phrase, { exact: true })).toBeVisible();
  await expect(page.getByText("Actual service-resolved criterion weights (relative weights)")).toBeVisible();

  // A display filter must not POST a new run or alter retained values/ranks.
  let newRunRequests = 0;
  page.on("request", (r) => { if (r.method() === "POST" && new URL(r.url()).pathname === "/runs") newRunRequests++; });
  await page.getByLabel("Top N", { exact: true }).fill("5");
  await page.getByRole("button", { name: "Apply display filters" }).click();
  await expect(shortlist.locator("tbody tr")).toHaveCount(5);
  expect(newRunRequests).toBe(0);
  await shortlist.getByRole("button", { name: new RegExp(rows[1].cell_id) }).click();
  await expect(detail.getByRole("code").filter({ hasText: rows[1].cell_id })).toBeVisible();

  // Map selection uses the same service coordinate and opens the same cell.
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  const x = (rows[0].centroid_lon - 140.7) / 13.6 * bounds!.width;
  const y = (-27.8 - rows[0].centroid_lat) / 13.6 * bounds!.width;
  await canvas.click({ position: { x, y } });
  await expect(detail.getByRole("code").filter({ hasText: rows[0].cell_id })).toBeVisible();

  await shortlist.getByText(/^Inspect exclusions/).click();
  await shortlist.getByRole("button", { name: /^Inspect excluded/ }).first().click();
  await expect(detail.getByText("Not scored", { exact: true })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "exclusion reasons" })).toBeVisible();
  await page.getByRole("button", { name: "Compare Wind-led and Grid-led" }).click();
  await expect(page.getByText("Selected cell comparison:", { exact: false })).toBeHidden();
  await expect(page.getByRole("columnheader", { name: "Engine rank delta" })).toBeVisible();
  await page.getByRole("radio", { name: "Grid-led", exact: true }).check();
  await page.getByRole("button", { name: "Run analysis", exact: true }).click();
  const grid = await (await request.post(`${api}/runs`, { data: { scenario: "grid_led" } })).json();
  const gridRows = await (await request.get(`${api}/runs/${grid.run_id}/results?top_n=10`)).json();
  await expect(detail.getByRole("code").filter({ hasText: gridRows[0].cell_id })).toBeVisible();
  expect(gridRows[0].cell_id).not.toBe(rows[0].cell_id);
  await expect(page.getByText(/Selected cell comparison:/)).toBeVisible();
  const bad = await request.get(`${api}/runs/${grid.run_id}/results?top_n=0`);
  expect(bad.status()).toBe(422);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "test-results/final-demo.png", fullPage: true });
});
