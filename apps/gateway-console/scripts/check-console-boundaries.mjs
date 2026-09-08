import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";

const defaultRoot = new URL("../src/", import.meta.url);
const forbiddenPatterns = [
  ["localStorage", /\blocalStorage\b/],
  ["sessionStorage", /\bsessionStorage\b/],
  ["document.cookie", /\bdocument\s*\.\s*cookie\b/],
  ["location.search", /\b(?:window\s*\.\s*)?location\s*\.\s*search\b/],
  ["unreviewed mutation HTTP method", /\bmethod\s*:\s*["'`](?:PUT|PATCH|DELETE)["'`]/],
  ["Authorization header", /["'`]Authorization["'`]\s*:/],
  ["absolute HTTP URL", /https?:\/\//],
];
const postPattern = /\bmethod\s*:\s*["'`]POST["'`]/g;
const reviewedGeneratePost =
  /this\.\#fetch\(\s*["'`]\/v1\/generate["'`]\s*,\s*\{\s*method\s*:\s*["'`]POST["'`]/;
const allowedPaths = new Set(["/v1/ops/overview", "/v1/ops/deployments", "/v1/generate"]);

export async function checkConsoleBoundaries(root = defaultRoot) {
  const files = await collectSourceFiles(root);
  for (const file of files) {
    const content = await readFile(file, "utf8");
    for (const [label, pattern] of forbiddenPatterns) {
      if (pattern.test(content)) {
        throw new Error(`forbidden console boundary ${JSON.stringify(label)} in ${file.pathname}`);
      }
    }

    const postMatches = [...content.matchAll(postPattern)];
    if (postMatches.length > 0) {
      const reviewedFile = file.pathname.endsWith("/inference.ts");
      if (postMatches.length !== 1 || !reviewedFile || !reviewedGeneratePost.test(content)) {
        throw new Error(`unreviewed Console POST boundary in ${file.pathname}`);
      }
    }

    for (const match of content.matchAll(/\/v1\/[a-z0-9_/-]+/g)) {
      if (!allowedPaths.has(match[0])) {
        throw new Error(`unreviewed Gateway path ${match[0]} in ${file.pathname}`);
      }
    }
  }
  return files.length;
}

async function collectSourceFiles(directoryUrl) {
  const entries = await readdir(directoryUrl, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const child = new URL(entry.name, directoryUrl);
    if (entry.isDirectory()) {
      files.push(...(await collectSourceFiles(new URL(`${entry.name}/`, directoryUrl))));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      files.push(child);
    }
  }
  return files;
}

const invokedPath = process.argv[1];
if (invokedPath !== undefined && import.meta.url === pathToFileURL(fileURLToPath(pathToFileURL(invokedPath))).href) {
  const filesChecked = await checkConsoleBoundaries();
  console.log(`console_boundary_check: PASS (${filesChecked} source files)`);
}
