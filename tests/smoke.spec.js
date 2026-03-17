const { test, expect, devices } = require("@playwright/test");

test.describe("ApertureZen Smoke Tests (Rev 100)", () => {
  async function bypassLogin(page) {
    await page.goto("/login-test");
    await page.waitForURL("/", { timeout: 10000 });
    // Esperar a que el Splash Screen desaparezca
    const splash = page.locator("#splash-screen");
    await splash.waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});
  }

  test("Test 1: Home Load & Pure Silver Aesthetic", async ({ page }) => {
    await page.goto("/");
    const splash = page.locator("#splash-screen");
    await splash.waitFor({ state: "hidden", timeout: 5000 }).catch(() => {});

    await expect(page).toHaveTitle(/Ctrl\+F Físico/);
    const logo = page.locator(".logo-text");
    await expect(logo).toContainText("APERTURE");
  });

  test("Test 2: Login Flow (Bypass Rafael)", async ({ page }) => {
    await bypassLogin(page);
    const galleryLink = page.locator(
      'nav a:has-text("Galería"), .mobile-nav-item:has-text("Buscados")',
    );
    await expect(galleryLink.first()).toBeVisible();
  });

  test("Test 3: Blueprint Generation (Solid Geometry)", async ({ page }) => {
    await bypassLogin(page);

    await page.goto("/plano/nuevo");
    await page.waitForSelector('input[name="nombre"]', {
      state: "visible",
      timeout: 10000,
    });

    await page.fill('input[name="nombre"]', "Galpón de QA");

    // Activar modo Plantilla
    await page.click("#btn-mode-template");

    // Seleccionar Categoría Galpón
    await page.click("#tpl-galpon");

    // Esperar a que carguen las variantes y seleccionar la primera
    await page.waitForSelector(".variant-item", {
      state: "visible",
      timeout: 10000,
    });
    await page.click(".variant-item");

    // Crear
    await page.click('button[type="submit"]');

    // Verificar Redirección al Editor
    await expect(page).toHaveURL(/\/plano\/\d+\/modular_editor/, { timeout: 15000 });

    // Verificar Editor Modular
    const editorContainer = page.locator("#modular-editor-layout");
    await expect(editorContainer).toBeVisible();
  });

  test("Test 4: Search Engine Validation", async ({ page }) => {
    await bypassLogin(page);

    const searchInput = page.locator("#smart-search-input");
    await searchInput.waitFor({ state: "visible" });
    await searchInput.fill("Herramientas");
    await page.keyboard.press("Enter");

    await expect(page.locator("#results-container")).toBeVisible({ timeout: 10000 });
  });
});
