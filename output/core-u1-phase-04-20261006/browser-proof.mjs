// Phase 4 browser proof: production RADAR components against the real API, session and PostgreSQL.
import { writeFileSync } from "node:fs";
import { chromium } from "/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs";

const out = new URL(".", import.meta.url).pathname;
const base = "http://127.0.0.1:3049";
const browser = await chromium.launch({
  executablePath: `${process.env.HOME}/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell`,
});
const info = await (await fetch(`${base}/fixture/info/`)).json();
const slug = info.workspace_slug;
const results = { steps: [] };
const step = (name, data = {}) => {
  results.steps.push({ name, ...data });
  console.log("STEP", name, JSON.stringify(data));
};

async function session(name, to) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 1800 } });
  const page = await context.newPage();
  page.on("response", async (response) => {
    if (response.status() >= 400 && response.url().includes("/api/"))
      console.log(`[${name}] ${response.status()} ${response.url()}`, (await response.text()).slice(0, 400));
  });
  page.on("console", (message) => {
    if (message.type() === "error") console.log(`[${name}] console`, message.text().slice(0, 300));
  });
  // The first visit lets Vite pre-bundle the production component graph.
  await page.goto(`${base}/fixture/login/${name}/?to=${to}`, { waitUntil: "domcontentloaded", timeout: 180000 });
  return { context, page };
}
const field = (page, key) => page.getByTestId(`property-${key}`);
async function choose(page, trigger, option) {
  await page.locator(trigger).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}
async function settled(page) {
  await page.waitForFunction(() => !document.querySelector('[aria-busy="true"]'), null, { timeout: 15000 });
}
// Waits for the write and for the capacity snapshot that follows it, never for a toast.
async function submitted(page, click, method = "PUT") {
  const write = page.waitForResponse((r) => r.request().method() === method && r.url().includes("/radar/"), {
    timeout: 20000,
  });
  const refresh = write.then(() =>
    page.waitForResponse((r) => r.request().method() === "GET" && r.url().includes("/capabilities/"), { timeout: 20000 })
  );
  await click();
  const response = await write;
  await refresh;
  await settled(page);
  return response.status();
}

// 1. C03: create a workspace-only type through metadata; then its lifecycle and presentation.
{
  const { context, page } = await session("author", "create");
  await page.getByRole("button", { name: "Create object" }).click({ timeout: 20000 });
  await page.getByTestId("radar-create-type").click();
  await page.getByRole("option", { name: "Ticket", exact: true }).click();
  await page.locator("#radar-create-summary").waitFor();
  const initial = await page.getByTestId("radar-create-initial-state").innerText();
  const createDisabled = await page.getByRole("button", { name: "Create", exact: true }).isDisabled();
  await page.locator("#radar-object-title").fill("Printer offline");
  await page.locator("#radar-create-summary").fill("Third floor printer is offline");
  await page.screenshot({ path: `${out}browser-create-form.png` });
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.waitForURL(/\/radar\/objects\/[0-9a-f-]{36}/, { timeout: 20000 });
  results.ticket = page.url().match(/objects\/([0-9a-f-]{36})/)[1];
  await page.getByTestId("radar-section-triage").waitFor({ timeout: 20000 });
  await settled(page);
  const narrative = await page.getByTestId("radar-narrative-property").locator("textarea").inputValue();
  const notes = await page.getByTestId("radar-content-notes").locator("h2").innerText();
  const stamp = await page.getByTestId("property-closed_at-reason").innerText();
  step("create_custom_type_from_metadata", { initial, createDisabledBeforeRequired: createDisabled, narrative, notes, stamp });
  await choose(page, "#radar-property-status", "Working");
  const working = await submitted(page, () => page.getByRole("button", { name: "Save status" }).click());
  await choose(page, "#radar-property-status", "Closed");
  const closed = await submitted(page, () => page.getByRole("button", { name: "Save status" }).click());
  step("custom_transitions_saved", { working, closed });
  const closedAt = await page.locator("#radar-property-closed_at").inputValue();
  step("custom_lifecycle_to_terminal", { closedAt, statusEditable: await field(page, "status").getAttribute("data-editable") });
  await page.screenshot({ path: `${out}browser-ticket-terminal.png`, fullPage: true });
  await context.close();
}

// 2. C20/C21: derived score is read-only; risk sections differ from the ticket's.
{
  const { context, page } = await session("author", `objects/${info.objects.risk}`);
  await page.getByTestId("radar-section-assessment").waitFor({ timeout: 20000 });
  await settled(page);
  step("risk_derived_and_sections", {
    scoreEditable: await field(page, "score").getAttribute("data-editable"),
    scoreReason: await page.getByTestId("property-score-reason").innerText(),
    likelihoodEditable: await field(page, "likelihood").getAttribute("data-editable"),
    sections: await page.locator('[data-testid^="radar-section-"]').evaluateAll((nodes) => nodes.map((n) => n.dataset.testid)),
  });
  await page.screenshot({ path: `${out}browser-risk-capacities.png`, fullPage: true });
  await context.close();
}

// 3. C20: a governed action is reviewed then executed with its evidence.
{
  const { context, page } = await session("author", `objects/${info.objects.action}`);
  const card = page.getByTestId("radar-action-action:CompleteAction");
  await card.waitFor({ timeout: 20000 });
  await settled(page);
  await page.locator("#radar-action-CompleteAction-outcome").fill("Enterprise terms signed");
  await choose(page, "#radar-action-CompleteAction-evidence_id", "Document · License assessment");
  await card.getByRole("button", { name: /^Review/ }).click();
  const preview = await page.getByTestId("radar-action-preview").innerText({ timeout: 15000 });
  await page.screenshot({ path: `${out}browser-action-review.png`, fullPage: true });
  const executed = await submitted(page, () => card.getByRole("button", { name: /^Confirm/ }).click(), "POST");
  step("complete_action_with_review", {
    preview,
    executed,
    statusEditable: await field(page, "status").getAttribute("data-editable"),
    completedAt: await page.locator("#radar-property-completed_at").inputValue(),
    completeAvailable: await card.getByRole("button", { name: /^Review/ }).count(),
  });
  await page.screenshot({ path: `${out}browser-action-completed.png`, fullPage: true });
  await context.close();
}

// 4. C20: guarded decision taking and independent approval follow the real guards.
{
  const { context, page } = await session("author", `objects/${info.objects.decision}`);
  const take = page.getByTestId("radar-action-transition:UpdateObject:decided:");
  await take.waitFor({ timeout: 20000 });
  await settled(page);
  step("decision_author_unavailable", {
    take: await take.innerText(),
    approve: await page.getByTestId("radar-action-action:ApproveDecision").innerText(),
  });
  await page.screenshot({ path: `${out}browser-decision-author.png`, fullPage: true });
  await context.close();
}
{
  const { context, page } = await session("reviewer", `objects/${info.objects.decision}`);
  const approve = page.getByTestId("radar-action-action:ApproveDecision");
  await approve.waitFor({ timeout: 20000 });
  await settled(page);
  await page.locator("#radar-action-ApproveDecision-rationale").fill("Independent review of the evidence");
  await approve.getByRole("button", { name: /^Review/ }).click();
  await page.getByTestId("radar-action-preview").waitFor({ timeout: 15000 });
  const approved = await submitted(page, () => approve.getByRole("button", { name: /^Confirm/ }).click(), "POST");
  const take = page.getByTestId("radar-action-transition:UpdateObject:decided:");
  await take.getByRole("button", { name: /^Review/ }).click({ timeout: 20000 });
  await page.getByTestId("radar-action-preview").waitFor({ timeout: 15000 });
  const taken = await submitted(page, () => take.getByRole("button", { name: /^Confirm/ }).click(), "POST");
  await page.getByTestId("property-context-reason").waitFor({ timeout: 20000 });
  step("decision_approved_and_taken_by_reviewer", {
    approved,
    taken,
    contextReason: await page.getByTestId("property-context-reason").innerText(),
    decidedAt: await page.locator("#radar-property-decided_at").inputValue(),
  });
  await page.screenshot({ path: `${out}browser-decision-taken.png`, fullPage: true });
  await context.close();
}

// 5. Readers see the same layout read-only, without governed controls.
{
  const { context, page } = await session("guest", `objects/${info.objects.risk}`);
  await page.getByTestId("radar-section-assessment").waitFor({ timeout: 20000 });
  await settled(page);
  step("guest_read_only", {
    editable: await page.locator("[data-editable]").evaluateAll((nodes) => [...new Set(nodes.map((n) => n.dataset.editable))]),
    saveButtons: await page
      .getByRole("button", { name: /^Save/ })
      .evaluateAll((nodes) => nodes.map((node) => ({ label: node.textContent, disabled: node.disabled }))),
    reviewButtons: await page.getByRole("button", { name: /^Review/ }).count(),
  });
  await page.screenshot({ path: `${out}browser-guest.png`, fullPage: true });
  await context.close();
}

writeFileSync(`${out}browser-steps.json`, `${JSON.stringify(results, null, 2)}\n`);
await browser.close();
