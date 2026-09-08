import { readdir, readFile } from "node:fs/promises";

const root = new URL("../src/", import.meta.url);
const forbiddenPatterns = [
  ["localStorage", /\blocalStorage\b/],
  ["sessionStorage", /\bsessionStorage\b/],
  ["document.cookie", /\bdocument\s*\.\s*cookie\b/],
  ["location.search", /\b(?:window\s*\.\s*)?location\s*\.\s*search\b/],
  ["mutation HTTP method", /\bmethod\s*:\s*["'`](?:POST|PUT|PATCH|DELETE)["'`]/],
  ["Authorization header", /["'`]Authorization["'`]\s*:/],
  ["absolute HTTP URL", /https?:\/\//],
];
const allowedOperationsPaths = new Set(["/v1/ops/overview", "/v1/ops/deployments"]);

const files = await collectSourceFiles(root);
for (const file of files) {
  const content = await readFile(file, "utf8");
  for (const [label, pattern] of forbiddenPatterns) {
    if (pattern.test(content)) {
      throw new Error(`forbidden console boundary ${JSON.stringify(label)} in ${file.pathname}`);
    }
  }

  for (const match of content.matchAll(/\/v1\/ops\/[a-z0-9_/-]+/g)) {
    if (!allowedOperationsPaths.has(match[0])) {
      throw new Error(`unreviewed Operations path ${match[0]} in ${file.pathname}`);
    }
  }
}

console.log(`console_boundary_check: PASS (${files.length} source files)`);

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
