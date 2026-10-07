// Phase 1.8 E2E: real Plane login/shell (web :3000 -> API :8001 -> PostgreSQL) and CoS runtime (:8940).
// Usage: node e2e.mjs <stage>   stages: login | create | review | decide | object-page | permissions | provider
// Credentials are read from the gitignored .secrets files and never printed. State: e2e-state.json.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "/opt/homebrew/lib/node_modules/@playwright/cli/node_modules/playwright/index.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const WEB = "http://localhost:3000";
const API = "http://localhost:8001";
const SLUG = process.env.RADAR_E2E_SLUG ?? "radar-e2e";
const STATE = path.join(HERE, SLUG === "radar-e2e" ? "e2e-state.json" : `e2e-state-${SLUG}.json`);
const AUTH_DIR = process.env.RADAR_E2E_AUTH_DIR ?? path.join(ROOT, ".secrets", "e2e-auth");
const EXECUTABLE =
  process.env.RADAR_E2E_CHROMIUM ??
  `${process.env.HOME}/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell`;

const state = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, "utf8")) : { checks: [] };
state.workspace = SLUG;
const save = () => fs.writeFileSync(STATE, JSON.stringify(state, null, 2) + "\n");
function check(name, ok, detail = "") {
  state.checks = state.checks.filter((item) => item.name !== name);
  state.checks.push({ name, ok: !!ok, detail, at: new Date().toISOString() });
  save();
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) throw new Error(`Check failed: ${name}`);
}

function secret(file, pattern) {
  const match = fs.readFileSync(path.join(ROOT, ".secrets", file), "utf8").match(pattern);
  if (!match) throw new Error(`Missing credential in .secrets/${file}`);
  return match[1].trim();
}
const ACCOUNTS = {
  tester: { email: "radar-tester@plane.local", password: () => secret("radar-dev-login.md", /Password:\s*`?([^`\s]+)`?/) },
  member: { email: "radar-e2e-member@plane.local", password: () => secret("radar-e2e-users.env", /RADAR_E2E_MEMBER_PASSWORD=(.+)/) },
  guest: { email: "radar-e2e-guest@plane.local", password: () => secret("radar-e2e-users.env", /RADAR_E2E_GUEST_PASSWORD=(.+)/) },
  outsider: { email: "radar-e2e-outsider@plane.local", password: () => secret("radar-e2e-users.env", /RADAR_E2E_OUTSIDER_PASSWORD=(.+)/) },
};

const browser = await chromium.launch({ executablePath: EXECUTABLE });
const network = [];
let lastPage = null;

async function session(who) {
  const file = path.join(AUTH_DIR, `${who}.json`);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    storageState: fs.existsSync(file) ? file : undefined,
  });
  const page = await context.newPage();
  lastPage = page;
  page.on("response", (response) => {
    const url = response.url();
    if (url.startsWith(API) && /\/radar\/|\/auth\//.test(url))
      network.push(`${who} ${response.request().method()} ${response.status()} ${url.replace(API, "")}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") network.push(`${who} console.error ${message.text().slice(0, 300)}`);
  });
  return { context, page, file };
}

// Real Plane email/password sign-in; the API sets the Django session cookie.
async function login(who) {
  const { context, page, file } = await session(who);
  await page.goto(`${WEB}/`, { waitUntil: "networkidle" });
  if (await page.locator("#email").count()) {
    await page.fill("#email", ACCOUNTS[who].email);
    await page.getByRole("button", { name: "Continue" }).click();
    const password = page.locator('input[type="password"]').first();
    await password.waitFor({ timeout: 15000 });
    await password.fill(ACCOUNTS[who].password());
    await page.locator('button[type="submit"]').first().click();
    await page.waitForURL((url) => !["/", "/sign-in", "/sign-in/"].includes(url.pathname), { timeout: 20000 });
    await page.waitForLoadState("networkidle");
  }
  fs.mkdirSync(AUTH_DIR, { recursive: true, mode: 0o700 });
  await context.storageState({ path: file });
  fs.chmodSync(file, 0o600);
  return { context, page };
}

const SHOTS = SLUG === "radar-e2e" ? HERE : path.join(HERE, SLUG);
fs.mkdirSync(SHOTS, { recursive: true });
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
const api = (page, url, init = {}) =>
  page.evaluate(
    async ([url, init]) => {
      const csrf = (await (await fetch(`${location.origin.replace(":3000", ":8001")}/auth/get-csrf-token/`, { credentials: "include" })).json()).csrf_token;
      const response = await fetch(url, {
        credentials: "include",
        ...init,
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, ...(init.headers ?? {}) },
      });
      let body = null;
      try {
        body = await response.json();
      } catch {}
      return { status: response.status, body };
    },
    [url, init]
  );

async function stageLogin() {
  const { page } = await login("tester");
  await page.goto(`${WEB}/${SLUG}/radar/today`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: "Today" }).first().waitFor({ timeout: 20000 });
  await shot(page, "01-login-today");
  check("login: real Plane sign-in reaches RADAR Today in the shell", page.url().includes(`/${SLUG}/radar/today`), page.url());
}

async function createObject(page, type, title, description) {
  await page.goto(`${WEB}/${SLUG}/radar/objects`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Create object" }).click();
  await page.fill("#radar-object-title", title);
  await page.getByRole("dialog").getByRole("button", { name: /Select a type|Objective|Project|Risk/ }).click();
  await page.getByRole("option", { name: type, exact: true }).click();
  if (description) await page.fill("#radar-create-description", description);
  await page.getByRole("dialog").getByRole("button", { name: "Create", exact: true }).click();
  await page.waitForURL(/\/radar\/objects\/[0-9a-f-]{36}\/?$/, { timeout: 20000 });
  await page.waitForLoadState("networkidle");
  return page.url().match(/objects\/([0-9a-f-]{36})/)[1];
}

async function stageCreate() {
  const { page } = await session("tester");
  state.objects ??= {};
  state.objects.objective ??= await createObject(page, "Objective", "Implantar Governança de IA");
  state.objects.project ??= await createObject(page, "Project", "Sandbox IA");
  state.objects.risk ??= await createObject(
    page,
    "Risk",
    "Licenciamento pode atrasar",
    "Licenciamento pode atrasar a governança de IA e o Sandbox IA"
  );
  save();
  await page.goto(`${WEB}/${SLUG}/radar/objects/${state.objects.risk}`, { waitUntil: "networkidle" });
  await page.getByText("Licenciamento pode atrasar").first().waitFor();
  await shot(page, "02-risk-created");
  check("create: human created Risk, Objective and Project through the RADAR UI", Object.keys(state.objects).length === 3, JSON.stringify(state.objects));
}

const RUN_URL = `${API}/api/workspaces/${SLUG}/radar/agent-runtime/runs/`;
const REVIEWS_URL = `${API}/api/workspaces/${SLUG}/radar/risk-reviews/`;

// Select agent and context in the real Risk Review screen, start one run and wait for its proposals.
async function runReview(page, label, prefix) {
  await page.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  await page.getByText("Run Risk Review").first().waitFor({ timeout: 20000 });
  await page.locator("#risk-review-agent").click();
  await page.getByRole("option", { name: "RADAR Copilot" }).click();
  for (const name of ["Licenciamento pode atrasar", "Implantar Governança de IA", "Sandbox IA"])
    await page.getByRole("checkbox", { name: new RegExp(`^${name} \\(`) }).click();
  await shot(page, `${prefix}-context-selected`);
  const startRequest = page.waitForRequest((request) => request.url() === RUN_URL && request.method() === "POST");
  const startResponse = page.waitForResponse((response) => response.url() === RUN_URL && response.request().method() === "POST");
  await page.getByRole("button", { name: "Run Risk Review" }).click();
  const request = await startRequest;
  const response = await startResponse;
  const started = await response.json();
  const run = { run_id: started.run_id, status: started.status, http: response.status(), key: request.headers()["idempotency-key"], body: request.postDataJSON() };
  // The UI offers "Check review"; the stage waits on this run's prepared review before asserting the screen.
  for (let attempt = 0; attempt < 60; attempt++) {
    const prepared = await api(page, REVIEWS_URL, { method: "POST", body: JSON.stringify({ run_id: run.run_id }) });
    run.prepare_status = prepared.status;
    if (prepared.status !== 202) break;
    await page.waitForTimeout(2000);
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.locator(`article[aria-label^="Review "]`).first().waitFor({ timeout: 20000 }).catch(() => {});
  await page.waitForLoadState("networkidle");
  await shot(page, `${prefix}-proposals`);
  state.runs ??= {};
  state.runs[label] = run;
  save();
  return run;
}

async function stageReview() {
  const { page } = await session("tester");
  const run = await runReview(page, "scripted", "03");
  check("review: run started from the shell with skill risk_review", run.http === 202 && run.body.skill === "risk_review", `run ${run.run_id}`);
  check(
    "review: context roots are the human-created Risk, Objective and Project",
    [state.objects.risk, state.objects.objective, state.objects.project].every((id) => run.body.root_ids.includes(id)),
    run.body.root_ids.join(",")
  );
  const cards = page.locator('article[aria-label^="Review "]');
  const relation = page.locator('article[aria-label="Review relation"]').first();
  check("review: agent suggested THREATENS and a mitigating action", (await cards.count()) >= 2 && (await relation.getByText("→ threatens →").count()) === 1, `${await cards.count()} proposal cards`);
  for (const name of ["Accept", "Edit", "Reject"])
    check(`review: UI shows ${name}`, (await relation.getByRole("button", { name, exact: true }).count()) === 1);
  // Idempotency: replaying the start with the browser's key returns the same run instead of a new one.
  const replay = await api(page, RUN_URL, { method: "POST", body: JSON.stringify(run.body), headers: { "Idempotency-Key": run.key } });
  check("idempotency: replayed run start returns the same run", replay.body?.run_id === run.run_id, `${replay.status} ${replay.body?.run_id}`);
  const prepared = await api(page, REVIEWS_URL, { method: "POST", body: JSON.stringify({ run_id: run.run_id }) });
  const again = await api(page, REVIEWS_URL, { method: "POST", body: JSON.stringify({ run_id: run.run_id }) });
  const ids = (body) => (body?.proposals ?? []).map((p) => p.id).sort().join(",");
  check("idempotency: preparing the same run twice keeps the same proposals", prepared.status === 200 && ids(prepared.body) === ids(again.body) && ids(again.body).length > 0, `${prepared.status}/${again.status}`);
  state.proposals = (again.body?.proposals ?? []).map((p) => ({ id: p.id, component: p.component, ordinal: p.ordinal, status: p.status, target: p.input.target_id ?? null, title: p.input.title ?? null }));
  save();
}

const card = (page, component, text, revision = 1) =>
  page
    .locator(`article[aria-label="Review ${component}"]`)
    .filter({ hasText: text })
    .filter({ hasText: `revision ${revision}` })
    .first();

async function decide(page, target, decision, rationale) {
  await target.getByLabel("Review feedback / rationale").fill(rationale);
  const response = page.waitForResponse((r) => r.url().includes("/resolve/") && r.request().method() === "POST");
  await target.getByRole("button", { name: decision, exact: true }).click();
  const result = await response;
  await page.waitForLoadState("networkidle");
  return { status: result.status(), body: await result.json().catch(() => null) };
}

async function stageDecide() {
  const { page } = await session("tester");
  await page.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  const objective = "Implantar Governança de IA";
  const relation = card(page, "relation", objective);
  await relation.waitFor({ timeout: 20000 });

  // 6-7. Human accepts the THREATENS relation; the Command Layer applies the saved intent.
  const accepted = await decide(page, relation, "Accept", "O atraso do licenciamento ameaça o objetivo.");
  await relation.getByText("Applied").first().waitFor();
  check("accept: relation applied through the Command Layer", accepted.status === 200 && accepted.body.status === "executed", `${accepted.status} ${accepted.body?.command_name}`);
  state.accepted_relation = { proposal: accepted.body.id, intent_hash: accepted.body.intent_hash };

  // Documented 1.5 behavior: the relation bumped the Risk version, so the sibling action needs Edit -> Accept.
  const action = card(page, "action", "Validar licenciamento de IA");
  const conflict = await decide(page, action, "Accept", "Mitigação adequada para o atraso.");
  await action.getByRole("alert").waitFor();
  const alert = await action.getByRole("alert").innerText();
  await shot(page, "04-action-conflict");
  check("accept: sibling action reports the version conflict and asks for review", conflict.status === 409, `${conflict.status} ${JSON.stringify(conflict.body)} / UI: ${alert}`);
  await action.getByRole("button", { name: "Edit", exact: true }).click();
  const edited = await decide(page, action, "Save edited proposal", "Revisado após aceitar a relação; mesma mitigação.");
  check("edit: saved a new intent (revision 2) without executing", edited.status === 200 && edited.body.revision === 2 && edited.body.status === "pending_approval", `${edited.status} rev ${edited.body?.revision}`);
  const revised = card(page, "action", "Validar licenciamento de IA", 2);
  const applied = await decide(page, revised, "Accept", "Mitigação adequada para o atraso.");
  await revised.getByText("Open Action").waitFor();
  check("accept: revised action applied", applied.status === 200 && applied.body.status === "executed", applied.body?.result?.data?.object?.id ?? "");
  state.action = applied.body.result.data.object.id;
  state.accepted_action = { proposal: applied.body.id, intent_hash: applied.body.intent_hash };

  // Rejection: the second suggestion (Sandbox IA) is rejected with feedback and must not change the domain.
  const rejectedRelation = await decide(page, page.locator('article[aria-label="Review relation"]').filter({ hasText: "'Sandbox IA'" }).first(), "Reject", "O Sandbox IA tem licença temporária; não é ameaça.");
  const rejectedAction = await decide(page, card(page, "action", "Preparar plano B do Sandbox IA"), "Reject", "Plano B desnecessário com licença temporária.");
  check("reject: both components of the second suggestion rejected with rationale", rejectedRelation.status === 200 && rejectedRelation.body.status === "rejected" && rejectedAction.body?.status === "rejected", `${rejectedRelation.body?.approval?.rationale}`);
  state.rejected = { relation: { proposal: rejectedRelation.body.id, intent_hash: rejectedRelation.body.intent_hash }, action: { proposal: rejectedAction.body.id, intent_hash: rejectedAction.body.intent_hash } };
  save();
  await shot(page, "05-decisions");

  // Idempotency of decisions: retries return the saved result without a second write.
  const resolve = (item, decision, rationale) =>
    api(page, `${REVIEWS_URL}${item.proposal}/resolve/`, { method: "POST", body: JSON.stringify({ decision, rationale, intent_hash: item.intent_hash }) });
  const retryAccept = await resolve(state.accepted_relation, "accept", "retry");
  check("idempotency: retried Accept returns the executed proposal", retryAccept.status === 200 && retryAccept.body.status === "executed" && retryAccept.body.id === state.accepted_relation.proposal, `${retryAccept.status}`);
  const retryReject = await resolve(state.rejected.relation, "reject", "retry");
  check("idempotency: retried Reject returns the rejected proposal", retryReject.status === 200 && retryReject.body.status === "rejected", `${retryReject.status}`);
  const lateAccept = await resolve(state.rejected.relation, "accept", "mudei de ideia");
  check("rejection: a rejected proposal cannot be accepted later", lateAccept.status === 409, `${lateAccept.status} ${JSON.stringify(lateAccept.body)}`);
  save();
}

async function sectionText(page, id) {
  const section = page.locator(`section[aria-labelledby="${id}"]`);
  await section.waitFor({ timeout: 20000 });
  return (await section.innerText()).replace(/\s+/g, " ");
}

// 9. The real Object Pages show the accepted relation and the Action (forward links and backlinks).
async function stageObjectPage() {
  const { page } = await session("tester");
  await page.goto(`${WEB}/${SLUG}/radar/objects/${state.objects.risk}`, { waitUntil: "networkidle" });
  const relations = await sectionText(page, "radar-relations-heading");
  const backlinks = await sectionText(page, "radar-backlinks-heading");
  await page.locator('section[aria-labelledby="radar-relations-heading"]').scrollIntoViewIfNeeded();
  await shot(page, "06-risk-object-page");
  check("object page: Risk shows threatens -> Implantar Governança de IA", /threatens/i.test(relations) && relations.includes("Implantar Governança de IA"), relations.slice(0, 200));
  check("object page: Risk shows the mitigating Action as backlink", backlinks.includes("Validar licenciamento de IA"), backlinks.slice(0, 200));
  check("rejection: rejected Sandbox IA threat is absent from the Risk", !relations.includes("Sandbox IA") && !backlinks.includes("Preparar plano B"));
  await page.goto(`${WEB}/${SLUG}/radar/objects/${state.action}`, { waitUntil: "networkidle" });
  const actionRelations = await sectionText(page, "radar-relations-heading");
  await shot(page, "07-action-object-page");
  check("object page: Action shows mitigates -> Licenciamento pode atrasar", /mitigates/i.test(actionRelations) && actionRelations.includes("Licenciamento pode atrasar"), actionRelations.slice(0, 200));
  await page.goto(`${WEB}/${SLUG}/radar/objects/${state.objects.objective}`, { waitUntil: "networkidle" });
  const objectiveBacklinks = await sectionText(page, "radar-backlinks-heading");
  check("object page: Objective shows the Risk as backlink", objectiveBacklinks.includes("Licenciamento pode atrasar"), objectiveBacklinks.slice(0, 200));
  await page.reload({ waitUntil: "networkidle" });
  check("object page: state survives a full reload", (await sectionText(page, "radar-backlinks-heading")).includes("Licenciamento pode atrasar"));
}

// Administrative grant change through the existing audited control (never from the browser).
async function setAgentCommands(commands) {
  const { execFileSync } = await import("node:child_process");
  const code = `
from plane.db.models import Workspace, User
from plane.radar.commands import register_actor_grant
from plane.radar.commands.actor import Actor
from plane.radar.models import ActorGrant, RuntimeCredential
from uuid import uuid4
w = Workspace.objects.get(slug="${SLUG}"); admin = User.objects.get(email="radar-tester@plane.local")
b = RuntimeCredential.objects.get(workspace=w, reviewer=admin, channel="plane", is_active=True)
g = ActorGrant.objects.get(workspace=w, actor_type="agent", actor_id=b.actor_id)
register_actor_grant(actor=Actor(actor_type="human", actor_id=admin.pk, reason="E2E permission change", source="radar.runtime-cli", correlation_id=uuid4()),
  workspace=w, actor_type="agent", actor_id=b.actor_id, delegator_id=admin.pk, commands=${JSON.stringify(commands)}, object_types=g.object_types, fields=g.fields)
g.refresh_from_db(); print("GRANT", g.commands, g.policy_version)`;
  return execFileSync("docker", ["exec", "-i", "plane-radar-api-1", "python", "manage.py", "shell", "--settings=plane.settings.local"], { input: code })
    .toString()
    .split("\n")
    .find((line) => line.startsWith("GRANT"));
}

async function stagePermissions() {
  const target = state.accepted_relation;
  const riskUrl = `${API}/api/workspaces/${SLUG}/radar/objects/${state.objects.risk}/`;
  const runBody = { binding_id: state.runs.scripted.body.binding_id, root_ids: state.runs.scripted.body.root_ids, prompt: "Risk Review", skill: "risk_review" };

  // Member (role 15) without an agent binding: reads the domain, cannot use or resolve the tester's agent work.
  const member = (await login("member")).page;
  await member.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  await member.getByText("No agent is linked to your account").waitFor({ timeout: 20000 });
  await shot(member, "08-member-risk-review");
  check("permission: member without binding sees no agent and no foreign reviews", (await member.locator('article[aria-label^="Review "]').count()) === 0);
  check("permission: member can read the Risk", (await api(member, riskUrl)).status === 200);
  const memberRun = await api(member, RUN_URL, { method: "POST", body: JSON.stringify(runBody), headers: { "Idempotency-Key": "member-steal" } });
  check("permission: member cannot start a run with another user's agent binding", [403, 404].includes(memberRun.status), `${memberRun.status}`);
  const memberResolve = await api(member, `${REVIEWS_URL}${state.rejected.action.proposal}/resolve/`, { method: "POST", body: JSON.stringify({ decision: "accept", rationale: "x", intent_hash: state.rejected.action.intent_hash }) });
  check("permission: member cannot resolve another user's proposal", [403, 404].includes(memberResolve.status), `${memberResolve.status}`);

  // Guest (role 5): read-only, no runtime use.
  const guest = (await login("guest")).page;
  await guest.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  await guest.waitForTimeout(1500);
  await shot(guest, "09-guest-risk-review");
  check("permission: guest has no Run Risk Review control", (await guest.getByRole("button", { name: "Run Risk Review" }).count()) === 0);
  const guestRun = await api(guest, RUN_URL, { method: "POST", body: JSON.stringify(runBody), headers: { "Idempotency-Key": "guest-run" } });
  check("permission: guest cannot start runs", [403, 404].includes(guestRun.status), `${guestRun.status}`);

  // Outsider (not a member) and anonymous requests are blocked.
  const outsider = (await login("outsider")).page;
  await outsider.goto(`${WEB}/${SLUG}/radar/objects/${state.objects.risk}`, { waitUntil: "networkidle" });
  await outsider.waitForTimeout(1500);
  await shot(outsider, "10-outsider-object");
  check("permission: outsider cannot see the workspace Risk", !(await outsider.getByText("Licenciamento pode atrasar").count()));
  const outsiderApi = await api(outsider, riskUrl);
  check("permission: outsider API read is denied", [403, 404].includes(outsiderApi.status), `${outsiderApi.status}`);
  const anonymous = await (await fetch(`${REVIEWS_URL}${target.proposal}/resolve/`, { method: "POST" })).status;
  check("permission: anonymous resolve is rejected", [401, 403].includes(anonymous), `${anonymous}`);

  // Agent authority: a second run is prepared, then the administrator narrows the grant before acceptance.
  const { page } = await session("tester");
  const second = await runReview(page, "authority", "11");
  const prepared = await api(page, REVIEWS_URL, { method: "POST", body: JSON.stringify({ run_id: second.run_id }) });
  const pendingAction = prepared.body.proposals.find((p) => p.component === "action" && p.status === "pending_approval");
  state.authority = { run_id: second.run_id, proposal: pendingAction.id, grant_after: await setAgentCommands(["CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement", "LinkObjects"]) };
  save();
  const blocked = await api(page, `${REVIEWS_URL}${pendingAction.id}/resolve/`, { method: "POST", body: JSON.stringify({ decision: "accept", rationale: "aceitar", intent_hash: pendingAction.intent_hash }) });
  await page.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  await page.locator("#risk-review-agent").click();
  await page.getByRole("option", { name: "RADAR Copilot" }).click();
  await page.getByText("This agent needs permission").waitFor({ timeout: 20000 });
  await shot(page, "12-authority-revoked");
  check("permission: narrowed agent grant blocks the pending suggestion", [403, 409].includes(blocked.status), `${blocked.status} ${JSON.stringify(blocked.body)}`);
  check("permission: UI disables Run Risk Review without CreateAction", await page.getByRole("button", { name: "Run Risk Review" }).isDisabled());
  state.authority.grant_restored = await setAgentCommands(["CaptureIssue", "DelegateAction", "ReviewObject", "RecordMeasurement", "LinkObjects", "CreateAction"]);
  const stale = await api(page, `${REVIEWS_URL}${pendingAction.id}/resolve/`, { method: "POST", body: JSON.stringify({ decision: "accept", rationale: "aceitar", intent_hash: pendingAction.intent_hash }) });
  check("permission: restoring the grant does not revive a run authorized under the old policy", stale.status === 409, `${stale.status} ${JSON.stringify(stale.body)}`);
  save();
}

// Real provider: same shell/backend/adapter; the model output is not scripted, so content is recorded, not assumed.
async function stageProvider() {
  const { page } = await session("tester");
  const run = await runReview(page, "provider", "13");
  const prepared = await api(page, REVIEWS_URL, { method: "POST", body: JSON.stringify({ run_id: run.run_id }) });
  state.provider = {
    run_id: run.run_id,
    prepare_status: prepared.status,
    body: prepared.status === 200 ? { result: prepared.body.result, proposals: prepared.body.proposals.map((p) => ({ id: p.id, component: p.component, status: p.status, command: p.command_name, input: p.input, intent_hash: p.intent_hash })) } : prepared.body,
  };
  save();
  check("provider: real-model Risk Review completed from the shell", run.http === 202 && prepared.status !== 202, `prepare ${prepared.status}`);
  check("provider: output passed CoS and Plane validation and was saved for review", prepared.status === 200, JSON.stringify(prepared.body).slice(0, 300));
  const suggestions = prepared.body.result.suggestions;
  check(
    "provider: every suggestion cites both Risk and target with evidence from the snapshot",
    suggestions.every((s) => s.evidence.some((e) => e.object_id === state.objects.risk) && s.evidence.some((e) => e.object_id === s.suggested_relation.target_id)),
    `${suggestions.length} suggestion(s): ${suggestions.map((s) => `${s.suggested_relation.relation}->${s.suggested_relation.target_id === state.objects.project ? "project" : "objective"} ${s.confidence}`).join("; ")}`
  );
}

// Human decisions on the real-provider proposals, through the same cards.
async function stageProviderDecide() {
  const { page } = await session("tester");
  await page.goto(`${WEB}/${SLUG}/radar/risk-review`, { waitUntil: "networkidle" });
  const run = page.locator('section[aria-label="Risk Review run"]').filter({ hasText: state.provider.body.result.summary.slice(0, 60) });
  await run.waitFor({ timeout: 20000 });
  const proposals = state.provider.body.proposals;
  const byTarget = (id) => proposals.find((p) => p.component === "relation" && p.input.target_id === id);
  const cardFor = (proposal) => page.locator(`#risk-proposal-${proposal.id}`);
  // Resumable: a proposal resolved by an earlier attempt is replayed idempotently through the API.
  const resolveOnce = async (proposal, decision, rationale) =>
    (await cardFor(proposal).getByLabel("Review feedback / rationale").count())
      ? decide(page, cardFor(proposal), decision, rationale)
      : api(page, `${REVIEWS_URL}${proposal.id}/resolve/`, { method: "POST", body: JSON.stringify({ decision: decision.toLowerCase(), rationale, intent_hash: proposal.intent_hash }) });
  const duplicate = await resolveOnce(byTarget(state.objects.objective), "Accept", "Relação já registrada; aceitar para confirmar.");
  // The approval is consumed (execution "executed"), but the domain must not change: no new relation, no version bump.
  const version = async (id) => (await api(page, `${API}/api/workspaces/${SLUG}/radar/objects/${id}/`)).body.version;
  const [riskVersion, objectiveVersion] = [await version(state.objects.risk), await version(state.objects.objective)];
  check(
    "provider: accepting an already-recorded relation leaves the domain unchanged",
    duplicate.status === 200 && riskVersion === 3 && objectiveVersion === 2,
    `execution ${duplicate.body?.status} (approval consumed); Risk v${riskVersion}, Objective v${objectiveVersion}`
  );
  const project = await resolveOnce(byTarget(state.objects.project), "Accept", "A descrição do risco cita o Sandbox IA explicitamente.");
  check("provider: human accepted the real-model THREATENS -> Sandbox IA", project.status === 200 && project.body.status === "executed", `${project.status} ${project.body?.status}`);
  for (const action of proposals.filter((p) => p.component === "action")) {
    const rejected = await resolveOnce(action, "Reject", "Duplica a ação existente ou a própria relação; sem nova mitigação.");
    check(`provider: rejected action "${action.input.title.slice(0, 40)}"`, rejected.status === 200 && rejected.body.status === "rejected", `${rejected.status}`);
  }
  await shot(page, "14-provider-decisions");
  await page.goto(`${WEB}/${SLUG}/radar/objects/${state.objects.risk}`, { waitUntil: "networkidle" });
  const relations = await sectionText(page, "radar-relations-heading");
  await page.locator('section[aria-labelledby="radar-relations-heading"]').scrollIntoViewIfNeeded();
  await shot(page, "15-risk-after-provider");
  check("provider: Object Page shows both threats, each once", (relations.match(/Implantar Governança de IA/g) ?? []).length === 1 && (relations.match(/Sandbox IA/g) ?? []).length === 1, relations.slice(0, 220));
  state.provider.decisions = { duplicate: duplicate.body.status, project: project.body.status };
  save();
}

const docker = async (args, input) => (await import("node:child_process")).execFileSync("docker", args, { input }).toString();

// Documented administrative step: existing human-created Objects enter the agent context only via the CLI.
async function stageBind() {
  const admin = (await docker(["exec", "-i", "plane-radar-api-1", "python", "manage.py", "shell", "--settings=plane.settings.local"], 'from plane.db.models import User; print("ADMIN", User.objects.get(email="radar-tester@plane.local").pk)')).match(/ADMIN (\S+)/)[1];
  const codes = { objective: "OBJ", project: "PRJ", risk: "RSK" };
  const suffix = (await import("node:crypto")).createHash("sha256").update(SLUG).digest("hex").slice(0, 6).toUpperCase();
  for (const [key, prefix] of Object.entries(codes)) {
    const out = await docker(["exec", "plane-radar-api-1", "python", "manage.py", "radar_runtime_provision", "--settings=plane.settings.local",
      "--workspace", SLUG, "--admin-id", admin, "--context", `company:${SLUG}`, "--bind-object", state.objects[key], "--external-id", `${prefix}-20261005-${suffix}`]);
    check(`bind: admin CLI bound the ${key} to the agent context`, out.trim() === `${prefix}-20261005-${suffix}`, out.trim());
  }
}

async function stageVerifyDb() {
  const raw = await docker(["exec", "-i", "-e", `RADAR_E2E_STATE=${JSON.stringify(state)}`, "plane-radar-api-1", "python", "manage.py", "shell", "--settings=plane.settings.local"], fs.readFileSync(path.join(HERE, "verify_db.py")));
  const result = JSON.parse(raw.split("\n").find((line) => line.startsWith("VERIFY ")).slice(7));
  fs.writeFileSync(path.join(SHOTS, "db-evidence.json"), JSON.stringify(result, null, 2) + "\n");
  for (const item of result.checks) check(`db: ${item.name}`, item.ok, item.detail ?? "");
}

const SEQUENCE = ["login", "create", "bind", "review", "decide", "object-page", "verify-db", "permissions"];

const stages = {
  bind: stageBind,
  "verify-db": stageVerifyDb,
  "provider-decide": stageProviderDecide,
  provider: stageProvider,
  login: stageLogin,
  create: stageCreate,
  review: stageReview,
  decide: stageDecide,
  "object-page": stageObjectPage,
  permissions: stagePermissions,
};
try {
  const requested = process.argv.slice(2).flatMap((name) => (name === "all" ? SEQUENCE : [name]));
  for (const name of requested) {
    if (!stages[name]) throw new Error(`Unknown stage ${name}`);
    console.log(`== ${name}`);
    await stages[name]();
  }
} catch (error) {
  if (lastPage) await lastPage.screenshot({ path: path.join(HERE, "failure.png"), fullPage: true }).catch(() => {});
  throw error;
} finally {
  fs.appendFileSync(path.join(HERE, "browser-network.log"), network.map((line) => `${new Date().toISOString()} ${line}`).join("\n") + (network.length ? "\n" : ""));
  await browser.close();
}
