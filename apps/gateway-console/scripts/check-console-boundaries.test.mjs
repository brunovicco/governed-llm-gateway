import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { checkConsoleBoundaries } from "./check-console-boundaries.mjs";

const temporaryRoots = [];

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("Console boundary checker", () => {
  it("accepts only the reviewed generate POST plus existing Operations GET paths", async () => {
    const root = await fixture({
      "api.ts": 'fetch("/v1/ops/overview"); fetch("/v1/ops/deployments");',
      "inference.ts": 'this.#fetch("/v1/generate", { method: "POST" });',
    });

    await expect(checkConsoleBoundaries(pathToFileURL(`${root}/`))).resolves.toBe(2);
  });

  it("rejects POST to any unreviewed endpoint even from inference.ts", async () => {
    const root = await fixture({
      "inference.ts": 'this.#fetch("/v1/route/explain", { method: "POST" });',
    });

    await expect(checkConsoleBoundaries(pathToFileURL(`${root}/`))).rejects.toThrow(
      "unreviewed Console POST boundary",
    );
  });

  it.each(["PUT", "PATCH", "DELETE"])("rejects %s even for the reviewed generate path", async (method) => {
    const root = await fixture({
      "inference.ts": `this.#fetch("/v1/generate", { method: "${method}" });`,
    });

    await expect(checkConsoleBoundaries(pathToFileURL(`${root}/`))).rejects.toThrow(
      "unreviewed mutation HTTP method",
    );
  });

  it("rejects a second POST even when one reviewed generate call is present", async () => {
    const root = await fixture({
      "inference.ts": [
        'this.#fetch("/v1/generate", { method: "POST" });',
        'this.#fetch("/v1/generate", { method: "POST" });',
      ].join("\n"),
    });

    await expect(checkConsoleBoundaries(pathToFileURL(`${root}/`))).rejects.toThrow(
      "unreviewed Console POST boundary",
    );
  });

  it("keeps browser persistence forbidden", async () => {
    const root = await fixture({
      "inference.ts": 'localStorage.setItem("credential", "unsafe");',
    });

    await expect(checkConsoleBoundaries(pathToFileURL(`${root}/`))).rejects.toThrow("localStorage");
  });
});

async function fixture(files) {
  const root = await mkdtemp(join(tmpdir(), "gateway-console-boundary-"));
  temporaryRoots.push(root);
  await Promise.all(
    Object.entries(files).map(([name, content]) => writeFile(join(root, name), content, "utf8")),
  );
  return root;
}
