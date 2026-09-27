import { test, expect, Page } from "@playwright/test";
import path from "node:path";
import fs from "node:fs/promises";
const sample = (name: string) => path.resolve(__dirname, "../../samples", name);

test.beforeEach(async ({ request }) => {
  // This server always owns a freshly migrated disposable schema.
  const list = await (await request.get("/api/v1/cases")).json();
  for (const item of list.items)
    expect(
      (
        await request.delete(`/api/v1/cases/${item.id}`, {
          data: { expected_version: item.version, confirmed: true },
        })
      ).ok(),
    ).toBeTruthy();
});

async function importPair(page: Page) {
  await page.goto("/dossiers/nouveau");
  await page
    .getByLabel("Document bon de commande", { exact: true })
    .setInputFiles(sample("po.pdf"));
  await page
    .getByLabel("Document facture", { exact: true })
    .setInputFiles(sample("invoice.png"));
  await page.getByRole("button", { name: "Analyser les documents" }).click();
  await expect(page).toHaveURL(/\/dossiers\/[a-f0-9-]{36}$/);
  await expect(
    page.getByRole("heading", { name: /point.*à vérifier/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Votre brouillon de demande" }),
  ).toHaveCount(0);
  return page.url().split("/").at(-1)!;
}
async function resolvePair(page: Page) {
  await page.getByRole("link", { name: "Vérifier les données" }).click();
  await page.getByRole("tab", { name: "02 · Facture" }).click();
  await expect(
    page.getByRole("img", { name: "Original invoice.png" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/review-desktop.png",
    fullPage: false,
  });
  await page.getByLabel("Quantité", { exact: true }).fill("22");
  await page
    .getByLabel("Motif de la correction ou de la confirmation")
    .fill("Quantité 22 vérifiée sur la facture synthétique, page 1.");
  await page.getByRole("button", { name: "Enregistrer et relancer" }).click();
  await expect(
    page.getByRole("heading", { name: "Votre brouillon de demande" }),
  ).toBeVisible();
  await expect(page.locator(".result-summary")).toContainText("200,00 MAD");
}

test("empty dashboard and mobile layout", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Votre premier rapprochement commence ici.",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("link", { name: "Comparer mes documents" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
});

test("real upload, blocked review, correction, draft edit, reload, copy, download and delete", async ({
  page,
  context,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const id = await importPair(page);
  await resolvePair(page);
  await page
    .getByLabel("Objet", { exact: true })
    .fill("Demande de vérification — facture INV-8821");
  await page
    .getByLabel("Message", { exact: true })
    .fill(
      "Bonjour, merci de vérifier l’écart potentiel de 200.00 MAD hors taxes.",
    );
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("Brouillon enregistré.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Objet", { exact: true })).toHaveValue(
    "Demande de vérification — facture INV-8821",
  );
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Copier le brouillon" }).click();
  await expect(
    page.getByText("Brouillon copié.", { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "200.00 MAD hors taxes",
  );
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Télécharger", exact: true }).click();
  const download = await downloading;
  expect(await fs.readFile((await download.path())!, "utf8")).toContain(
    "Objet : Demande de vérification",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/result-desktop.png",
    fullPage: true,
  });
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: /Atlas Supplies/ }),
  ).toBeVisible();
  await expect(page.locator(".featured")).toContainText("200,00 MAD");
  await page.goto(`/dossiers/${id}`);
  await page
    .getByRole("button", { name: "Supprimer le dossier", exact: true })
    .click();
  await page.getByRole("button", { name: "Supprimer définitivement" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3001/");
  await expect(
    page.getByRole("heading", {
      name: "Votre premier rapprochement commence ici.",
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("unresolved uncertainty stays blocked after rerun", async ({ page }) => {
  await importPair(page);
  await page.getByRole("link", { name: "Vérifier les données" }).click();
  await page
    .getByLabel("Motif de la correction ou de la confirmation")
    .fill("La quantité reste inconnue.");
  await page.getByRole("button", { name: "Enregistrer et relancer" }).click();
  await expect(page).toHaveURL(/\/dossiers\/[a-f0-9-]{36}$/);
  await expect(
    page.getByRole("heading", { name: /point.*à vérifier/ }),
  ).toBeVisible();
  await expect(page.locator(".result-summary")).toHaveCount(0);
  await expect(page.locator(".draft-panel")).toHaveCount(0);
  await page.goto("/");
  await expect(page.locator(".featured")).not.toContainText("MAD");
});

test("stale draft edits are rejected without overwriting the current version", async ({
  page,
  request,
}) => {
  const id = await importPair(page);
  await resolvePair(page);
  const current = await (await request.get(`/api/v1/cases/${id}`)).json();
  expect(
    (
      await request.patch(`/api/v1/cases/${id}/draft`, {
        data: {
          expected_version: current.version,
          subject: "Version concurrente",
          body: "Version conservée côté serveur.",
        },
      })
    ).ok(),
  ).toBeTruthy();
  await page.getByLabel("Objet", { exact: true }).fill("Modification périmée");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Ce dossier a changé",
  );
  expect(
    (await (await request.get(`/api/v1/cases/${id}`)).json()).draft.subject,
  ).toBe("Version concurrente");
  await page.reload();
  await expect(page.getByLabel("Objet", { exact: true })).toHaveValue(
    "Version concurrente",
  );
});

test("invalid uploads and foreign origins are rejected", async ({
  page,
  request,
}) => {
  await page.goto("/dossiers/nouveau");
  await page.getByLabel("Document facture", { exact: true }).setInputFiles({
    name: "bad.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a document"),
  });
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Formats acceptés",
  );
  await expect(
    page.getByRole("button", { name: "Analyser les documents" }),
  ).toBeDisabled();
  expect(
    (
      await request.post("/api/v1/cases", {
        headers: { Origin: "https://example.com" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.get("/api/v1/cases", { headers: { Host: "example.com" } })
    ).status(),
  ).toBe(403);
});
