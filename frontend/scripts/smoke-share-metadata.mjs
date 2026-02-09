#!/usr/bin/env node

const SITE_BASE = String(
  process.env.SMOKE_SITE_BASE || process.env.NEXT_PUBLIC_SITE_URL || "https://emergence.quest"
).replace(/\/+$/, "");
const RUN_ID = String(process.env.SMOKE_RUN_ID || "ci-smoke-run").trim();
const TIMEOUT_MS = Number(process.env.SMOKE_TIMEOUT_MS || 15000);

function fail(message) {
  throw new Error(message);
}

function ensure(condition, message) {
  if (!condition) fail(message);
}

function decodeMetaUrl(value) {
  return String(value || "").replace(/&amp;/g, "&").replace(/\\u0026/g, "&");
}

function parseMetaTags(html) {
  const metaTags = [];
  const tagMatches = String(html || "").match(/<meta\s+[^>]*>/gi) || [];
  for (const tag of tagMatches) {
    const attrs = {};
    const attrMatches = tag.matchAll(/([A-Za-z:_-]+)\s*=\s*"([^"]*)"/g);
    for (const match of attrMatches) {
      attrs[String(match[1] || "").toLowerCase()] = match[2] || "";
    }
    metaTags.push(attrs);
  }
  return metaTags;
}

function findMetaContent(html, key, value) {
  const metaTags = parseMetaTags(html);
  const loweredValue = String(value || "").toLowerCase();
  for (const attrs of metaTags) {
    if (String(attrs[key] || "").toLowerCase() === loweredValue) {
      return decodeMetaUrl(attrs.content || "");
    }
  }
  return "";
}

async function fetchText(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, { redirect: "follow", signal: controller.signal });
    ensure(response.ok, `Expected 2xx for ${url}, got ${response.status}`);
    return await response.text();
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      redirect: "follow",
      signal: controller.signal,
    });
    ensure(response.ok, `Expected 2xx JSON for ${url}, got ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function assertPngUrl(url, label) {
  ensure(url, `${label}: missing URL`);
  ensure(url.includes("/social-card.png"), `${label}: expected social-card.png URL, got ${url}`);
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    fail(`${label}: invalid URL ${url}`);
  }
  ensure(parsed.searchParams.has("v"), `${label}: missing cache-busting v= query param in ${url}`);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(parsed.toString(), { method: "GET", redirect: "follow", signal: controller.signal });
    ensure(response.status === 200, `${label}: expected image 200, got ${response.status} for ${parsed}`);
    const contentType = String(response.headers.get("content-type") || "").toLowerCase();
    ensure(contentType.startsWith("image/png"), `${label}: expected image/png, got ${contentType || "n/a"}`);
  } finally {
    clearTimeout(timer);
  }
}

async function assertSharePage(path, label) {
  const pageUrl = `${SITE_BASE}${path}`;
  const html = await fetchText(pageUrl);
  const ogImage = findMetaContent(html, "property", "og:image");
  const twitterImage = findMetaContent(html, "name", "twitter:image");

  ensure(ogImage, `${label}: missing og:image on ${pageUrl}`);
  ensure(twitterImage, `${label}: missing twitter:image on ${pageUrl}`);

  await assertPngUrl(ogImage, `${label} og:image`);
  await assertPngUrl(twitterImage, `${label} twitter:image`);
  console.log(`[ok] ${label} -> ${path}`);
  console.log(`     og: ${ogImage}`);
  console.log(`     tw: ${twitterImage}`);
  return { ogImage, twitterImage };
}

async function main() {
  ensure(RUN_ID.length > 0, "SMOKE_RUN_ID cannot be empty");

  const runPath = `/share/run/${encodeURIComponent(RUN_ID)}`;
  const runResult = await assertSharePage(runPath, "share-run");

  let apiBase;
  try {
    apiBase = new URL(runResult.ogImage).origin;
  } catch {
    fail(`Unable to resolve API base from ${runResult.ogImage}`);
  }

  const events = await fetchJson(`${apiBase}/api/events?limit=1`);
  ensure(Array.isArray(events) && events.length > 0, `No events returned from ${apiBase}/api/events?limit=1`);
  const eventId = Number(events[0]?.id || 0);
  ensure(Number.isInteger(eventId) && eventId > 0, "Could not resolve a valid event id for smoke check");

  await assertSharePage(`/share/moment/${eventId}`, "share-moment");
  await assertSharePage(`/share/run/${encodeURIComponent(RUN_ID)}/moment/${eventId}`, "share-run-moment");

  console.log("");
  console.log(`[done] Share metadata smoke passed for site=${SITE_BASE}, run=${RUN_ID}, event=${eventId}`);
}

main().catch((error) => {
  console.error(`[fail] ${error?.message || error}`);
  process.exitCode = 1;
});
