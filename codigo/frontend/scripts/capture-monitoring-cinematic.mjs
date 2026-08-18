#!/usr/bin/env node

/** Captura post-hoc de la cinematica publicada; nunca gobierna el replay. */

import { chromium } from "@playwright/test";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { homedir, platform, release, tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const EXPECTED = {
  beats: 726,
  fps: 12,
  height: 1080,
  videoFrames: 1121,
  width: 1920,
};

const args = parseArgs(process.argv.slice(2));
const captureDir = resolve(args.captureDir);
const projectRoot = fileURLToPath(new URL("../../../", import.meta.url));
const planPath = join(captureDir, "capture_plan.json");
const preregistrationPath = join(captureDir, "preregistration.json");
const timelinePath = join(captureDir, "cinematic_timeline.jsonl");
const manifestPath = join(captureDir, "manifest.json");
const plan = readJson(planPath);
const preregistration = readJson(preregistrationPath);
const sourceManifest = readJson(manifestPath);
const timeline = readTimeline(timelinePath);
const beats = timeline.beats;
validateInputs(
  plan,
  preregistration,
  sourceManifest,
  beats,
  timeline.lines,
);
const rendererSourceBinding = validateRendererSources(plan, projectRoot);

const framesDir = join(captureDir, "frames");
if (existsSync(framesDir) && readdirSync(framesDir).length > 0) {
  throw new Error(`frames directory is not empty: ${framesDir}`);
}
mkdirSync(framesDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
let browserVersion = "unknown";
let sessionBinding = null;
let servedRendererBinding = [];
const mutationAttempts = [];
const frameRecords = [];
try {
  browserVersion = browser.version();
  const context = await browser.newContext({
    colorScheme: "light",
    deviceScaleFactor: 1,
    locale: "es-ES",
    reducedMotion: "reduce",
    viewport: { width: EXPECTED.width, height: EXPECTED.height },
  });
  const page = await context.newPage();
  const rendererOrigin = new URL(args.baseUrl).origin;
  const servedResources = new Map();
  const servedResourceTasks = [];
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (
      url.origin !== rendererOrigin ||
      url.pathname.startsWith("/api/") ||
      !response.ok()
    ) return;
    const task = response.body().then((body) => {
      servedResources.set(`${url.pathname}${url.search}`, {
        content_type: response.headers()["content-type"] ?? null,
        path: `${url.pathname}${url.search}`,
        sha256: sha256Bytes(body),
        size_bytes: body.byteLength,
      });
    }).catch(() => undefined);
    servedResourceTasks.push(task);
  });
  await page.route("**/*", async (route) => {
    const method = route.request().method().toUpperCase();
    if (["GET", "HEAD", "OPTIONS"].includes(method)) {
      await route.continue();
      return;
    }
    mutationAttempts.push(`${method} ${route.request().url()}`);
    await route.abort("blockedbyclient");
  });
  await page.addInitScript((timeline) => {
    Object.defineProperty(window, "__TFM_MONITORING_CINEMATIC_TIMELINE__", {
      configurable: false,
      enumerable: false,
      value: timeline,
      writable: false,
    });
  }, beats);

  const campaignResponse = await context.request.get(
    new URL("/api/monitoring/evidence-campaigns/current", args.baseUrl).toString(),
  );
  if (!campaignResponse.ok()) {
    throw new Error(`campaign endpoint failed: ${campaignResponse.status()}`);
  }
  const campaign = await campaignResponse.json();
  if (
    campaign.campaign_id !== plan.campaign_id ||
    campaign.session_id !== plan.campaign_session_id ||
    campaign.plan_sha256 !== plan.campaign_plan_sha256 ||
    sourceManifest.registration_sha256 !== preregistration.registration_sha256 ||
    campaign.publication_sha256 !== sourceManifest.campaign_publication_sha256 ||
    !["completed", "failed"].includes(campaign.status) ||
    !campaign.result_sha256 ||
    campaign.result_sha256 !== sourceManifest.campaign_result_sha256 ||
    !Number.isFinite(Date.parse(campaign.registered_at)) ||
    !campaign.started_at ||
    Date.parse(preregistration.registered_at) > Date.parse(campaign.started_at)
  ) {
    throw new Error("browser capture requires the exact completed campaign result");
  }
  const sessionResponse = await context.request.get(
    new URL(
      `/api/monitoring/sessions/${encodeURIComponent(plan.campaign_session_id)}`,
      args.baseUrl,
    ).toString(),
  );
  if (!sessionResponse.ok()) {
    throw new Error(`campaign session endpoint failed: ${sessionResponse.status()}`);
  }
  sessionBinding = validateSessionAgainstTimeline(
    await sessionResponse.json(),
    plan,
    beats,
  );

  await page.goto(args.baseUrl, { waitUntil: "networkidle" });
  await page
    .getByRole("navigation", { name: "Vistas principales" })
    .getByRole("button", { name: "Monitorización" })
    .click();
  await page.getByRole("button", { name: "Abrir sesión" }).click();
  await page.getByRole("tab", { name: "Cinemática" }).click();

  const stage = page.getByTestId("monitoring-cinematic-stage");
  await stage.waitFor({ state: "visible" });
  await Promise.all(servedResourceTasks);
  servedRendererBinding = [...servedResources.values()].sort((left, right) =>
    left.path.localeCompare(right.path),
  );
  if (servedRendererBinding.length === 0) {
    throw new Error("browser did not expose renderer response bytes");
  }
  for (const testId of [
    "monitoring-bearing-rig",
    "monitoring-health-trend",
    "monitoring-score-ratio-trend",
    "monitoring-agent-act",
    "monitoring-evidence-heatmap",
    "monitoring-act-rail",
  ]) {
    const panel = page.getByTestId(testId);
    if ((await panel.count()) !== 1) {
      throw new Error(`cinematic panel is missing or duplicated: ${testId}`);
    }
    await panel.waitFor({ state: "visible" });
  }
  const range = page.getByRole("slider", {
    name: "Seleccionar acto de la cinemática",
  });
  if ((await range.count()) !== 1) {
    throw new Error("cinematic stage must expose exactly one act range");
  }
  const rangeContract = await range.evaluate((element) => ({
    max: element.max,
    min: element.min,
  }));
  if (rangeContract.min !== "0" || rangeContract.max !== "725") {
    throw new Error("cinematic act range must use exact domain 0..725");
  }
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        caret-color: transparent !important;
        scroll-behavior: auto !important;
        transition: none !important;
      }
      html, body { margin: 0 !important; overflow: hidden !important; }
      [data-testid="monitoring-cinematic-stage"] {
        background: #f7f8fb !important;
        box-sizing: border-box !important;
        height: 1080px !important;
        inset: 0 !important;
        margin: 0 !important;
        max-height: none !important;
        max-width: none !important;
        overflow: hidden !important;
        padding: 24px !important;
        position: fixed !important;
        width: 1920px !important;
        z-index: 2147483647 !important;
      }
    `,
  });
  await page.evaluate(() => document.fonts.ready);

  for (const beat of beats) {
    await range.evaluate((element, value) => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set;
      if (!setter) throw new Error("native range setter is unavailable");
      setter.call(element, String(value));
      element.dispatchEvent(new Event("input", { bubbles: true }));
      element.dispatchEvent(new Event("change", { bubbles: true }));
    }, beat.beat_index);
    await page.waitForFunction(
      (expected) =>
        document
          .querySelector('[data-testid="monitoring-cinematic-stage"]')
          ?.getAttribute("data-beat-index") === String(expected),
      beat.beat_index,
    );
    await stage.evaluate(
      () =>
        new Promise((resolveFrame) =>
          requestAnimationFrame(() => requestAnimationFrame(resolveFrame)),
        ),
    );
    const filename = `beat-${String(beat.beat_index).padStart(6, "0")}.png`;
    const path = join(framesDir, filename);
    await page.screenshot({
      animations: "disabled",
      caret: "hide",
      fullPage: false,
      path,
      scale: "css",
      type: "png",
    });
    assertPngDimensions(path, EXPECTED.width, EXPECTED.height);
    frameRecords.push({
      beat_index: beat.beat_index,
      beat_sha256: beat.beat_sha256,
      duration_frames: beat.duration_frames,
      height: EXPECTED.height,
      path: relative(captureDir, path).replaceAll("\\", "/"),
      sha256: sha256File(path),
      size_bytes: statSync(path).size,
      width: EXPECTED.width,
    });
  }
  await context.close();
} finally {
  await browser.close();
}

if (mutationAttempts.length > 0) {
  throw new Error(`browser attempted mutations:\n${mutationAttempts.join("\n")}`);
}

const frameManifestPath = join(captureDir, "frames.jsonl");
writeExclusive(
  frameManifestPath,
  `${frameRecords.map((item) => stableStringify(item)).join("\n")}\n`,
);

let videoPath = null;
let ffmpegPath = null;
if (!args.skipVideo) {
  ffmpegPath = resolveFfmpeg(args.ffmpegPath);
  videoPath = join(captureDir, "campaign.webm");
  renderWebm({ beats, ffmpegPath, framesDir, outputPath: videoPath });
}

const packageJson = readJson(new URL("../package.json", import.meta.url));
const renderManifestCore = {
  schema_version: "monitoring_cinematic_render_manifest_v1",
  campaign_id: plan.campaign_id,
  capture_id: plan.capture_id,
  capture_plan_sha256: plan.capture_plan_sha256,
  registration_sha256: preregistration.registration_sha256,
  source_manifest_sha256: sourceManifest.manifest_sha256,
  timeline_sha256: sourceManifest.timeline_sha256,
  beat_count: frameRecords.length,
  video_frame_count: beats.reduce((total, item) => total + item.duration_frames, 0),
  fps: EXPECTED.fps,
  viewport: { width: EXPECTED.width, height: EXPECTED.height, device_scale_factor: 1 },
  browser: { engine: "chromium", version: browserVersion },
  browser_session_binding: sessionBinding,
  renderer_source_binding: rendererSourceBinding,
  served_renderer_binding: servedRendererBinding,
  environment: {
    node: process.version,
    platform: platform(),
    release: release(),
    playwright: packageJson.devDependencies?.["@playwright/test"] ?? "unknown",
  },
  frames_manifest: {
    path: relative(captureDir, frameManifestPath).replaceAll("\\", "/"),
    sha256: sha256File(frameManifestPath),
  },
  video: videoPath
    ? {
        codec: "VP8",
        format: "WebM",
        path: relative(captureDir, videoPath).replaceAll("\\", "/"),
        sha256: sha256File(videoPath),
        size_bytes: statSync(videoPath).size,
      }
    : null,
  ffmpeg: ffmpegPath
    ? { path: ffmpegPath, sha256: sha256File(ffmpegPath) }
    : null,
  trace_scope: "post_hoc_read_only_ui_capture",
};
const renderManifest = {
  ...renderManifestCore,
  render_manifest_sha256: sha256Text(stableStringify(renderManifestCore)),
};
const renderManifestPath = join(captureDir, "render_manifest.json");
writeExclusive(renderManifestPath, `${JSON.stringify(renderManifest, null, 2)}\n`);

const renderChecksumsPath = join(captureDir, "render-checksums.sha256");
const renderedPaths = [
  ...frameRecords.map((item) => join(captureDir, item.path)),
  frameManifestPath,
  renderManifestPath,
  ...(videoPath ? [videoPath] : []),
];
writeExclusive(
  renderChecksumsPath,
  `${renderedPaths
    .sort()
    .map((path) => `${sha256File(path)}  ${relative(captureDir, path).replaceAll("\\", "/")}`)
    .join("\n")}\n`,
);

process.stdout.write(
  `${JSON.stringify(
    {
      beat_count: frameRecords.length,
      campaign_id: plan.campaign_id,
      capture_id: plan.capture_id,
      frames_dir: framesDir,
      mode: "post_hoc_capture",
      mutation_attempt_count: mutationAttempts.length,
      render_manifest_sha256: renderManifest.render_manifest_sha256,
      video_frame_count: renderManifest.video_frame_count,
      video_path: videoPath,
    },
    null,
    2,
  )}\n`,
);

function parseArgs(argv) {
  const parsed = {
    baseUrl: "http://127.0.0.1:5173",
    captureDir:
      "../reports/validation/monitoring_cinematic/" +
      "nasa-p3-agentic-window-56h-v1-cinematic-2d-v1",
    ffmpegPath: null,
    skipVideo: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--skip-video") {
      parsed.skipVideo = true;
    } else if (arg === "--base-url") {
      parsed.baseUrl = requiredValue(argv, ++index, arg);
    } else if (arg === "--capture-dir") {
      parsed.captureDir = requiredValue(argv, ++index, arg);
    } else if (arg === "--ffmpeg-path") {
      parsed.ffmpegPath = requiredValue(argv, ++index, arg);
    } else {
      throw new Error(`unknown argument: ${arg}`);
    }
  }
  return parsed;
}

function requiredValue(argv, index, flag) {
  const value = argv[index];
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function readTimeline(path) {
  const lines = readFileSync(path, "utf8")
    .split(/\r?\n/u)
    .filter(Boolean);
  return { beats: lines.map((line) => JSON.parse(line)), lines };
}

function validateInputs(plan, preregistration, sourceManifest, beats, lines) {
  const expectedKeyframes = [
    "tick:000",
    "tick:352",
    "trigger:353",
    "tick:496",
    "trigger:498",
    "trigger:499",
    "trigger:688",
    "final_verdict",
  ];
  if (
    plan.schema_version !== "monitoring_cinematic_capture_plan_v1" ||
    plan.viewport_width !== EXPECTED.width ||
    plan.viewport_height !== EXPECTED.height ||
    plan.device_scale_factor !== 1 ||
    plan.reduced_motion !== true ||
    plan.fps !== EXPECTED.fps ||
    plan.expected_beat_count !== EXPECTED.beats ||
    plan.expected_video_frame_count !== EXPECTED.videoFrames ||
    JSON.stringify(plan.keyframes) !== JSON.stringify(expectedKeyframes)
  ) {
    throw new Error("capture plan does not match the closed browser contract");
  }
  if (
    canonicalHashWithout(plan, "capture_plan_sha256") !==
    plan.capture_plan_sha256
  ) {
    throw new Error("capture plan SHA-256 does not match canonical payload");
  }
  if (
    preregistration.schema_version !== "monitoring_cinematic_preregistration_v1" ||
    canonicalHashWithout(preregistration, "registration_sha256") !==
      preregistration.registration_sha256 ||
    preregistration.capture_id !== plan.capture_id ||
    preregistration.campaign_id !== plan.campaign_id ||
    preregistration.campaign_plan_sha256 !== plan.campaign_plan_sha256 ||
    preregistration.capture_plan_sha256 !== plan.capture_plan_sha256 ||
    resolve(preregistration.capture_plan_ref) !== resolve(planPath) ||
    !Number.isFinite(Date.parse(preregistration.registered_at))
  ) {
    throw new Error("cinematic preregistration does not bind the capture plan");
  }
  if (
    canonicalHashWithout(sourceManifest, "manifest_sha256") !==
    sourceManifest.manifest_sha256
  ) {
    throw new Error("source manifest SHA-256 does not match canonical payload");
  }
  if (
    sourceManifest.capture_plan_sha256 !== plan.capture_plan_sha256 ||
    sourceManifest.timeline_sha256 !== sha256File(timelinePath) ||
    beats.length !== EXPECTED.beats
  ) {
    throw new Error("timeline does not bind capture/source manifest");
  }
  let previous = "0".repeat(64);
  const expectedDurations = {
    agent_decision: 9,
    final_verdict: 36,
    policy_proposal: 24,
    tick: 1,
    trigger: 12,
  };
  const kindCounts = Object.fromEntries(
    Object.keys(expectedDurations).map((kind) => [kind, 0]),
  );
  for (const [index, beat] of beats.entries()) {
    if (
      beat.schema_version !== "monitoring_cinematic_beat_v1" ||
      beat.beat_index !== index ||
      beat.previous_beat_sha256 !== previous ||
      !/^[0-9a-f]{64}$/u.test(beat.beat_sha256) ||
      !(beat.kind in expectedDurations) ||
      beat.duration_frames !== expectedDurations[beat.kind]
    ) {
      throw new Error(`cinematic beat chain breaks at ${index}`);
    }
    const canonicalCore = lines[index].replace(
      /"beat_sha256":"[0-9a-f]{64}",/u,
      "",
    );
    if (
      canonicalCore === lines[index] ||
      sha256Text(canonicalCore) !== beat.beat_sha256
    ) {
      throw new Error(`cinematic beat hash mismatch at ${index}`);
    }
    kindCounts[beat.kind] += 1;
    previous = beat.beat_sha256;
  }
  if (
    kindCounts.tick !== 689 ||
    kindCounts.trigger !== 4 ||
    kindCounts.agent_decision !== 28 ||
    kindCounts.policy_proposal !== 4 ||
    kindCounts.final_verdict !== 1 ||
    beats.at(-1)?.kind !== "final_verdict"
  ) {
    throw new Error("cinematic timeline does not match the 689/4/28/4/1 matrix");
  }
  const videoFrames = beats.reduce((total, item) => total + item.duration_frames, 0);
  if (videoFrames !== EXPECTED.videoFrames) {
    throw new Error("cinematic duration budget is not exact");
  }
}

function validateRendererSources(plan, root) {
  const entries = Object.entries(plan.source_sha256s ?? {}).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  if (entries.length === 0) {
    throw new Error("capture plan does not seal renderer sources");
  }
  return entries.map(([reference, expectedSha256]) => {
    const path = resolve(root, reference);
    const fromRoot = relative(root, path);
    if (
      fromRoot.startsWith("..") ||
      resolve(root, fromRoot) !== path ||
      !existsSync(path) ||
      lstatSync(path).isSymbolicLink() ||
      !statSync(path).isFile() ||
      sha256File(path) !== expectedSha256
    ) {
      throw new Error(`sealed renderer source changed: ${reference}`);
    }
    return {
      path: reference.replaceAll("\\", "/"),
      sha256: expectedSha256,
      size_bytes: statSync(path).size,
    };
  });
}

function validateSessionAgainstTimeline(session, plan, beats) {
  if (
    session?.config?.session_id !== plan.campaign_session_id ||
    session?.state?.session_id !== plan.campaign_session_id ||
    session?.state?.status !== "completed" ||
    session?.state?.revision !== 689 ||
    session?.state?.execution_cursor !== 688 ||
    session?.total_monitoring_ticks !== 689 ||
    !Array.isArray(session?.ticks) ||
    session.ticks.length !== 689 ||
    !Array.isArray(session?.triggers)
  ) {
    throw new Error("browser session is not the complete campaign replay");
  }
  const tickBeats = beats.filter((beat) => beat.kind === "tick");
  if (tickBeats.length !== 689) {
    throw new Error("injected timeline does not expose 689 tick beats");
  }
  for (let cursor = 0; cursor < 689; cursor += 1) {
    const tick = session.ticks[cursor];
    const beat = tickBeats[cursor];
    const display = beat.display_projection;
    if (
      tick.cursor !== cursor ||
      beat.cursor !== cursor ||
      beat.session_id !== plan.campaign_session_id ||
      tick.session_id !== plan.campaign_session_id ||
      tick.tick_id !== beat.tick_id ||
      tick.source_time !== beat.source_time ||
      display.cursor !== cursor ||
      display.source_time !== tick.source_time ||
      !Array.isArray(tick.frames) ||
      tick.frames.length !== 4 ||
      !Array.isArray(display.assets) ||
      display.assets.length !== 4
    ) {
      throw new Error(`browser tick identity diverges at cursor ${cursor}`);
    }
    for (const asset of display.assets) {
      const frame = tick.frames.find(
        (candidate) =>
          candidate.asset_id === asset.asset_id &&
          candidate.channel_id === asset.channel_id,
      );
      if (!frame || !cinematicFrameEquals(frame, asset)) {
        throw new Error(
          `browser frame diverges at cursor ${cursor}: ${asset.asset_id}/${asset.channel_id}`,
        );
      }
    }
  }
  const primaryEvents = session.triggers.filter(
    (trigger) => trigger.lifecycle_revision === 1,
  );
  if (
    primaryEvents.length !== 14 ||
    primaryEvents.filter((trigger) => trigger.lifecycle_status === "emitted").length !== 4
  ) {
    throw new Error("browser trigger ledger does not contain the frozen 14/4 primary matrix");
  }
  const triggerBeats = beats.filter((beat) => beat.kind === "trigger");
  if (triggerBeats.length !== 4) {
    throw new Error("injected timeline does not expose four trigger beats");
  }
  for (const beat of triggerBeats) {
    const event = primaryEvents.find((candidate) => candidate.event_id === beat.event_id);
    const projected = beat.display_projection.trigger;
    if (
      !event ||
      !projected ||
      event.trigger_id !== beat.trigger_id ||
      event.cutoff_cursor !== beat.cursor ||
      event.trigger_type !== projected.trigger_type ||
      event.reason_code !== projected.reason_code ||
      projected.cutoff_cursor !== beat.cursor
    ) {
      throw new Error(`browser trigger diverges at cursor ${beat.cursor}`);
    }
  }
  return {
    emitted_primary_trigger_count: 4,
    execution_cursor: session.state.execution_cursor,
    primary_trigger_count: primaryEvents.length,
    revision: session.state.revision,
    session_id: session.state.session_id,
    terminal_source_time: session.ticks[688].source_time,
    terminal_tick_id: session.ticks[688].tick_id,
    tick_count: session.ticks.length,
  };
}

function cinematicFrameEquals(frame, asset) {
  const telemetry = frame.telemetry ?? null;
  return (
    frame.analysis_status === asset.analysis_status &&
    frame.gap_detected === asset.gap_detected &&
    (telemetry?.signal_rms ?? null) === asset.signal_rms &&
    (telemetry?.signal_peak_abs ?? null) === asset.signal_peak_abs &&
    (frame.health_index ?? null) === asset.health_index &&
    (frame.risk_index ?? null) === asset.risk_index &&
    (frame.health_state ?? null) === asset.health_state &&
    (frame.score ?? null) === asset.score &&
    (frame.threshold ?? null) === asset.threshold &&
    (frame.score_ratio ?? null) === asset.score_ratio
  );
}

function assertPngDimensions(path, expectedWidth, expectedHeight) {
  const header = readFileSync(path).subarray(0, 24);
  if (header.toString("ascii", 1, 4) !== "PNG") throw new Error(`not a PNG: ${path}`);
  const width = header.readUInt32BE(16);
  const height = header.readUInt32BE(20);
  if (width !== expectedWidth || height !== expectedHeight) {
    throw new Error(`unexpected PNG dimensions ${width}x${height}: ${path}`);
  }
}

function resolveFfmpeg(explicitPath) {
  if (explicitPath) {
    const candidate = resolve(explicitPath);
    if (!existsSync(candidate)) throw new Error(`ffmpeg not found: ${candidate}`);
    return candidate;
  }
  const browserRoot = process.env.PLAYWRIGHT_BROWSERS_PATH
    ? resolve(process.env.PLAYWRIGHT_BROWSERS_PATH)
    : join(homedir(), ".cache", "ms-playwright");
  const candidates = existsSync(browserRoot)
    ? readdirSync(browserRoot)
        .filter((name) => name.startsWith("ffmpeg-"))
        .sort()
        .reverse()
        .map((name) => join(browserRoot, name, "ffmpeg-linux"))
    : [];
  const selected = candidates.find((path) => existsSync(path));
  if (!selected) {
    throw new Error("Playwright ffmpeg not found; pass --ffmpeg-path or --skip-video");
  }
  return selected;
}

function renderWebm({ beats, ffmpegPath, framesDir, outputPath }) {
  if (existsSync(outputPath)) throw new Error(`video already exists: ${outputPath}`);
  const staging = mkdtempSync(join(tmpdir(), "tfm-cinematic-video-"));
  try {
    let outputIndex = 0;
    for (const beat of beats) {
      const source = join(
        framesDir,
        `beat-${String(beat.beat_index).padStart(6, "0")}.png`,
      );
      for (let repeat = 0; repeat < beat.duration_frames; repeat += 1) {
        const destination = join(staging, `frame-${String(outputIndex).padStart(6, "0")}.png`);
        try {
          linkSync(source, destination);
        } catch {
          copyFileSync(source, destination);
        }
        outputIndex += 1;
      }
    }
    if (outputIndex !== EXPECTED.videoFrames) {
      throw new Error(`unexpected staged frame count: ${outputIndex}`);
    }
    const execution = spawnSync(
      ffmpegPath,
      [
        "-y",
        "-framerate",
        String(EXPECTED.fps),
        "-start_number",
        "0",
        "-i",
        join(staging, "frame-%06d.png"),
        "-frames:v",
        String(EXPECTED.videoFrames),
        "-an",
        "-c:v",
        "libvpx",
        "-b:v",
        "4M",
        "-pix_fmt",
        "yuv420p",
        "-map_metadata",
        "-1",
        outputPath,
      ],
      { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 },
    );
    if (execution.status !== 0) {
      throw new Error(`ffmpeg failed (${execution.status}): ${execution.stderr}`);
    }
  } finally {
    rmSync(staging, { force: true, recursive: true });
  }
}

function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sha256Text(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${pythonJsonString(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return typeof value === "string" ? pythonJsonString(value) : JSON.stringify(value);
}

function pythonJsonString(value) {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/gu, (character) =>
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

function canonicalHashWithout(value, excludedField) {
  const core = { ...value };
  delete core[excludedField];
  return sha256Text(stableStringify(core));
}

function writeExclusive(path, content) {
  writeFileSync(path, content, { encoding: "utf8", flag: "wx" });
}
