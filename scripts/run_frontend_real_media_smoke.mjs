import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../web/node_modules/playwright/index.mjs";

const SCRIPT_FILE = fileURLToPath(import.meta.url);
const PROJECT_ROOT = path.resolve(path.dirname(SCRIPT_FILE), "..");
const WORKHOME_ROOT = path.resolve(PROJECT_ROOT, "..", "..");
const VERIFICATION_ROOT = path.join(WORKHOME_ROOT, "management", "ai-manga-factory", "verification");
const APP_URL = process.env.AMF_APP_URL ?? "http://127.0.0.1:8000";
const PACK_NAME = process.env.AMF_PACK_NAME ?? "dgyx_ch1_20";
const PROJECT_NAME = process.env.AMF_PROJECT_NAME ?? `real-media-smoke-${Date.now()}`;
const SCENE_COUNT = process.env.AMF_SCENE_COUNT ?? "2";
const CHAPTER_START = process.env.AMF_CHAPTER_START ?? "1";
const CHAPTER_END = process.env.AMF_CHAPTER_END ?? "1";
const TARGET_DURATION_SECONDS = process.env.AMF_TARGET_DURATION_SECONDS ?? "60";
const OUTPUT_DIR = process.env.AMF_OUTPUT_DIR
  ?? path.join(VERIFICATION_ROOT, "frontend-smoke");
const TIMEOUT_MS = Number(process.env.AMF_TIMEOUT_MS ?? 720000);

async function ensureDir(target) {
  await fs.mkdir(target, { recursive: true });
}

async function readJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${url} -> ${response.status}`);
  }
  return response.json();
}

async function runPreflight() {
  const health = await readJson(`${APP_URL}/health`);
  const openapi = await readJson(`${APP_URL}/openapi.json`);
  await readJson(`${APP_URL}/artifacts-index`);
  await readJson(`${APP_URL}/jobs/summary`);
  const availablePaths = Object.keys(openapi.paths ?? {});
  for (const requiredPath of ["/artifacts-index", "/jobs/summary"]) {
    if (!availablePaths.includes(requiredPath)) {
      throw new Error(`OpenAPI missing route: ${requiredPath}`);
    }
  }
  return { health, checked_paths: ["/health", "/openapi.json", "/artifacts-index", "/jobs/summary"] };
}

function summarizeJob(job) {
  return {
    id: job.id,
    project_name: job.project_name,
    capability_id: job.capability_id,
    status: job.status,
    summary: job.summary,
    error: job.error,
    input: job.input,
    artifacts: job.artifacts,
    workflow: job.workflow,
    updated_at: job.updated_at,
  };
}

async function waitForJob(jobId, timeoutMs) {
  const startedAt = Date.now();
  let lastJob = null;
  while (Date.now() - startedAt < timeoutMs) {
    const jobs = await readJson(`${APP_URL}/jobs`);
    const job = jobs.items.find((item) => item.id === jobId);
    if (job) {
      lastJob = summarizeJob(job);
    }
    if (job && (job.status === "completed" || job.status === "failed")) {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  const error = new Error(`Timed out waiting for job ${jobId}`);
  error.jobSnapshot = lastJob;
  throw error;
}

async function main() {
  await ensureDir(OUTPUT_DIR);
  const beforeJobs = await readJson(`${APP_URL}/jobs`);
  const maxJobIdBefore = beforeJobs.items.reduce((max, job) => Math.max(max, job.id), 0);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  const consoleMessages = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on("console", (message) => {
    consoleMessages.push({ type: message.type(), text: message.text() });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: error.message, stack: error.stack ?? null });
  });
  page.on("requestfailed", (request) => {
    failedRequests.push({
      url: request.url(),
      method: request.method(),
      failure: request.failure()?.errorText ?? "unknown",
    });
  });

  const debugReport = {
    app_url: APP_URL,
    project_name: PROJECT_NAME,
    pack_name: PACK_NAME,
    chapter_start: CHAPTER_START,
    chapter_end: CHAPTER_END,
    scene_count: SCENE_COUNT,
    max_job_id_before: maxJobIdBefore,
    console_messages: consoleMessages,
    page_errors: pageErrors,
    failed_requests: failedRequests,
  };

  try {
    debugReport.preflight = await runPreflight();
    await page.goto(`${APP_URL}/?page=actions`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "运行适配包" }).click();
    await page.waitForFunction(() => {
      const labels = Array.from(document.querySelectorAll("label"));
      const packLabel = labels.find((node) => node.textContent?.includes("适配包"));
      const select = packLabel?.querySelector("select");
      return Boolean(select && select.options.length > 0);
    }, null, { timeout: 30000 });
    await page.getByLabel("适配包").selectOption(PACK_NAME);
    await page.getByLabel("项目名").fill(PROJECT_NAME);
    await page.getByLabel("分镜图数量").fill(SCENE_COUNT);
    await page.getByLabel("目标时长（秒）").fill(TARGET_DURATION_SECONDS);
    await page.getByLabel("开始章节").fill(CHAPTER_START);
    await page.getByLabel("结束章节").fill(CHAPTER_END);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "before-submit.png"), fullPage: true });

    await Promise.all([
      page.waitForURL(/page=jobs/, { timeout: 30000 }),
      page.getByRole("button", { name: "整包真图" }).click(),
    ]);
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(OUTPUT_DIR, "after-submit.png"), fullPage: true });

    const afterJobs = await readJson(`${APP_URL}/jobs`);
    const newJob = afterJobs.items.find((job) => job.id > maxJobIdBefore && job.project_name === PROJECT_NAME);
    if (!newJob) {
      throw new Error(`No new job found for project ${PROJECT_NAME}`);
    }

    const finalJob = await waitForJob(newJob.id, TIMEOUT_MS);
    const artifactSummary = finalJob.artifacts.find((artifact) => String(artifact.path_hint ?? "").endsWith("result_summary.md"));
    const artifactValidation = finalJob.artifacts.find((artifact) => String(artifact.path_hint ?? "").endsWith("validation_report.md"));

    if (artifactSummary?.path_hint) {
      const artifactPath = String(artifactSummary.path_hint).replace(/^\/+/, "");
      await page.goto(`${APP_URL}/artifacts/${artifactPath}`, { waitUntil: "domcontentloaded" }).catch(() => {});
      await page.screenshot({ path: path.join(OUTPUT_DIR, "artifact-view.png"), fullPage: true });
    }

    const report = {
      ...debugReport,
      new_job_id: newJob.id,
      final_job: summarizeJob(finalJob),
      artifact_summary: artifactSummary ?? null,
      artifact_validation: artifactValidation ?? null,
      console_messages: consoleMessages,
      page_errors: pageErrors,
      failed_requests: failedRequests,
    };
    await fs.writeFile(
      path.join(OUTPUT_DIR, `smoke-report-job-${newJob.id}.json`),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );

    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    debugReport.error = {
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack ?? null : null,
    };
    if (error && typeof error === "object" && "jobSnapshot" in error) {
      debugReport.job_snapshot = error.jobSnapshot ?? null;
    }
    debugReport.current_url = page.url();
    debugReport.page_title = await page.title().catch(() => null);
    debugReport.pack_select_html = await page.locator("label").filter({ hasText: "适配包" }).first().innerHTML().catch(() => null);
    await page.screenshot({ path: path.join(OUTPUT_DIR, "failure.png"), fullPage: true }).catch(() => {});
    await fs.writeFile(
      path.join(OUTPUT_DIR, "smoke-failure.json"),
      `${JSON.stringify(debugReport, null, 2)}\n`,
      "utf8",
    );
    throw error;
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
