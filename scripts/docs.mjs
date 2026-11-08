// Documentation tooling (skill `documentation`): generate the API reference from the code and
// check that the documentation set is complete and current.
//   node scripts/docs.mjs api        export the OpenAPI document and regenerate docs/api/reference.md
//   node scripts/docs.mjs reference  regenerate docs/api/reference.md from docs/api/openapi.json only
//   node scripts/docs.mjs check      fail when documentation is missing, stale or has broken links
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const METHODS = ["get", "put", "post", "delete", "options", "head", "patch"];
const GUIDE_DIRS = ["user-guide", "technical", "architecture", "api", "tutorials"];
const cell = (text) => String(text ?? "").replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ").trim();
const sha256 = (text) => createHash("sha256").update(text).digest("hex");

/** The first paragraph of a description, without the Args/Returns/Raises sections of a docstring. */
function summaryText(text) {
  if (!text) return "";
  const cut = text.split(/\n\s*(?:Args|Returns|Raises|Yields):/)[0];
  return cut.split(/\n\s*\n/)[0].replace(/\s*\n\s*/g, " ").trim();
}

function resolveRef(spec, ref) {
  return ref.replace(/^#\//, "").split("/").reduce((node, key) => node?.[key], spec);
}

function exampleValue(spec, schema, depth = 0) {
  if (!schema || depth > 4) return null;
  if (schema.$ref) return exampleValue(spec, resolveRef(spec, schema.$ref), depth + 1);
  if (schema.example !== undefined) return schema.example;
  if (schema.default !== undefined) return schema.default;
  if (schema.enum) return schema.enum[0];
  const branch = schema.anyOf ?? schema.oneOf;
  if (branch) return exampleValue(spec, branch.find((b) => b.type !== "null") ?? branch[0], depth + 1);
  if (schema.type === "object" || schema.properties) {
    return Object.fromEntries(Object.entries(schema.properties ?? {}).map(([key, value]) => [key, exampleValue(spec, value, depth + 1)]));
  }
  if (schema.type === "array") return [exampleValue(spec, schema.items, depth + 1)];
  return { string: "string", integer: 0, number: 0, boolean: true }[schema.type] ?? null;
}

function schemaName(schema) {
  if (!schema) return "";
  if (schema.$ref) return schema.$ref.split("/").pop();
  if (schema.type === "array") return `array of ${schemaName(schema.items) || "any"}`;
  return schema.type ?? (schema.anyOf ? schema.anyOf.map(schemaName).join(" or ") : "");
}

function requirements(spec, operation) {
  const list = operation.security ?? spec.security ?? [];
  return list.filter((entry) => Object.keys(entry).length > 0);
}

function accessText(requirement) {
  if (requirement.length === 0) return "Public (no authentication)";
  return requirement
    .map((entry) => Object.entries(entry).map(([name, scopes]) => `\`${name}\`${scopes.length ? ` with scope ${scopes.map((s) => `\`${s}\``).join(", ")}` : ""}`).join(" and "))
    .join(" or ");
}

function curlExample(spec, pathName, method, operation, requirement) {
  const query = (operation.parameters ?? []).filter((p) => p.in === "query" && p.required).map((p) => `${p.name}=<${p.name}>`);
  const url = `"$BASE_URL${pathName.replace(/\{(\w+)\}/g, "<$1>")}${query.length ? `?${query.join("&")}` : ""}"`;
  const lines = [`curl -s -X ${method.toUpperCase()} ${url}`];
  if (requirement.length > 0) {
    const scheme = spec.components?.securitySchemes?.[Object.keys(requirement[0])[0]];
    lines.push(scheme?.type === "apiKey" && scheme.in === "header" ? `  -H "${scheme.name}: $API_KEY"` : `  -H "Authorization: Bearer $TOKEN"`);
  }
  const body = operation.requestBody?.content?.["application/json"]?.schema;
  if (body) {
    lines.push(`  -H "Content-Type: application/json"`, `  -d '${JSON.stringify(exampleValue(spec, body))}'`);
  }
  return lines.join(" \\\n");
}

function renderSecuritySection(spec) {
  const schemes = Object.entries(spec.components?.securitySchemes ?? {});
  const out = ["## Authentication", ""];
  if (schemes.length === 0) {
    out.push("The document defines no security schemes: every operation is public. Once an identity provider is added, its scheme and the scopes per operation appear here.", "");
    return out;
  }
  out.push("| Scheme | Type | How it is sent | Scopes |", "|---|---|---|---|");
  for (const [name, scheme] of schemes) {
    const how = scheme.type === "http" ? `HTTP ${scheme.scheme}${scheme.bearerFormat ? ` (${scheme.bearerFormat})` : ""}`
      : scheme.type === "apiKey" ? `${scheme.in} \`${scheme.name}\``
      : scheme.type === "oauth2" ? Object.keys(scheme.flows ?? {}).join(", ")
      : scheme.openIdConnectUrl ?? "";
    const scopes = Object.values(scheme.flows ?? {}).flatMap((flow) => Object.entries(flow.scopes ?? {})).map(([scope, text]) => `\`${scope}\`: ${text}`).join("; ");
    out.push(`| \`${name}\` | ${cell(scheme.type)} | ${cell(how)} | ${cell(scopes)} |`);
  }
  out.push("");
  return out;
}

function renderOperation(spec, pathName, method, operation) {
  const requirement = requirements(spec, operation);
  const out = [`### \`${method.toUpperCase()} ${pathName}\``, ""];
  const text = summaryText(operation.description) || operation.summary;
  if (text) out.push(text, "");
  out.push(`**Access:** ${accessText(requirement)}.`, "");
  const parameters = operation.parameters ?? [];
  if (parameters.length > 0) {
    out.push("| Parameter | In | Type | Required | Description |", "|---|---|---|---|---|");
    for (const p of parameters) out.push(`| \`${p.name}\` | ${p.in} | ${cell(schemaName(p.schema))} | ${p.required ? "yes" : "no"} | ${cell(p.description)} |`);
    out.push("");
  }
  const body = operation.requestBody?.content?.["application/json"]?.schema;
  if (body) out.push(`**Request body:** \`${schemaName(body)}\` (JSON)${operation.requestBody.required ? ", required" : ""}.`, "");
  out.push("| Response | Description | Body |", "|---|---|---|");
  for (const [code, response] of Object.entries(operation.responses ?? {})) {
    const content = Object.values(response.content ?? {})[0]?.schema;
    out.push(`| ${code} | ${cell(response.description)} | ${content ? `\`${cell(schemaName(content))}\`` : ""} |`);
  }
  out.push("", "```bash", curlExample(spec, pathName, method, operation, requirement), "```", "");
  return out;
}

/** Render the API reference (Markdown that passes markdownlint) from an OpenAPI document. */
export function renderReference(spec, hash) {
  const operations = Object.entries(spec.paths ?? {}).flatMap(([pathName, item]) =>
    METHODS.filter((method) => item[method]).map((method) => ({ pathName, method, operation: item[method] })));
  const out = [
    `<!-- Generated by scripts/docs.mjs from docs/api/openapi.json (sha256:${hash}). Do not edit; run "node scripts/docs.mjs api". -->`,
    "",
    `# ${spec.info?.title ?? "Application"} API reference`,
    "",
    `Version ${spec.info?.version ?? "unknown"}, OpenAPI ${spec.openapi}. In the examples set \`BASE_URL\` (for example \`http://localhost:8000\`) and, for protected operations, \`TOKEN\` or \`API_KEY\`.`,
    "",
    ...renderSecuritySection(spec),
    "## Operations",
    "",
    "| Method | Path | Summary | Access |",
    "|---|---|---|---|",
    ...operations.map(({ pathName, method, operation }) => `| ${method.toUpperCase()} | \`${pathName}\` | ${cell(operation.summary)} | ${cell(accessText(requirements(spec, operation)))} |`),
    "",
    "## Details",
    "",
    ...operations.flatMap(({ pathName, method, operation }) => renderOperation(spec, pathName, method, operation)),
  ];
  return `${out.join("\n").replace(/\n{3,}/g, "\n\n").trimEnd()}\n`;
}

function frontmatter(text) {
  const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text)?.[1] ?? "";
  return Object.fromEntries(block.split(/\r?\n/).map((line) => /^([\w-]+):\s*(.*)$/.exec(line)).filter(Boolean).map(([, key, value]) => [key, value.trim().replace(/^["']|["']$/g, "")]));
}

function markdownFiles(dir) {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : markdownFiles(full);
    return entry.name.endsWith(".md") ? [full] : [];
  });
}

function brokenLinks(root, file) {
  const text = readFileSync(file, "utf8").replace(/```[\s\S]*?```/g, "").replace(/`[^`\n]*`/g, "");
  const problems = [];
  for (const [, target] of text.matchAll(/\]\(([^)\s]+)\)/g)) {
    if (/^([a-z][a-z0-9+.-]*:|#|\/\/)/i.test(target)) continue;
    const clean = decodeURI(target.split("#")[0]);
    if (clean && !existsSync(path.resolve(path.dirname(file), clean))) problems.push(`${path.relative(root, file).split(path.sep).join("/")}: broken link ${target}`);
  }
  return problems;
}

/** Everything that is missing, stale or broken in the documentation set; an empty list is a pass. */
export function checkDocs(root) {
  const problems = [];
  const readme = path.join(root, "README.md");
  if (!existsSync(readme)) problems.push("README.md is missing");
  else if (readFileSync(readme, "utf8").includes("{{")) problems.push("README.md still contains template placeholders");

  const openapi = path.join(root, "docs", "api", "openapi.json");
  const reference = path.join(root, "docs", "api", "reference.md");
  if (!existsSync(openapi)) problems.push("docs/api/openapi.json is missing: run node scripts/docs.mjs api");
  else if (!existsSync(reference)) problems.push("docs/api/reference.md is missing: run node scripts/docs.mjs api");
  else if (!readFileSync(reference, "utf8").includes(`sha256:${sha256(readFileSync(openapi, "utf8"))}`)) {
    problems.push("docs/api/reference.md does not match docs/api/openapi.json: run node scripts/docs.mjs api");
  }

  const specsDir = path.join(root, "docs", "specs");
  const guideIndex = path.join(root, "docs", "user-guide", "README.md");
  const indexText = existsSync(guideIndex) ? readFileSync(guideIndex, "utf8") : "";
  for (const file of existsSync(specsDir) ? readdirSync(specsDir).filter((f) => f.endsWith(".md") && f !== "README.md") : []) {
    const meta = frontmatter(readFileSync(path.join(specsDir, file), "utf8"));
    if (!["done", "released"].includes(meta.status)) continue;
    const docs = meta.docs ?? "";
    if (docs === "") problems.push(`docs/specs/${file}: status ${meta.status} but no "docs:" field (a documentation path, or "none: <reason>")`);
    else if (/^none\b/i.test(docs)) {
      if (!/^none:\s*\S/i.test(docs)) problems.push(`docs/specs/${file}: "docs: none" needs a reason ("none: <reason>")`);
    } else if (!existsSync(path.join(root, docs))) problems.push(`docs/specs/${file}: documentation ${docs} does not exist`);
    else if (docs.startsWith("docs/user-guide/") && !indexText.includes(path.basename(docs))) problems.push(`docs/user-guide/README.md does not list ${docs}`);
  }

  const files = [readme, ...GUIDE_DIRS.flatMap((dir) => markdownFiles(path.join(root, "docs", dir)))].filter((f) => existsSync(f));
  for (const file of files) problems.push(...brokenLinks(root, file));
  return problems;
}

function main(argv) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const [command] = argv;
  const openapi = path.join(root, "docs", "api", "openapi.json");
  if (command === "api" || command === "reference") {
    if (command === "api") {
      const exported = spawnSync("uv", ["run", "--directory", "backend", "python", "-m", "app.export_openapi"], { cwd: root, stdio: "inherit" });
      if (exported.status !== 0) process.exit(exported.status ?? 1);
    }
    const text = readFileSync(openapi, "utf8");
    mkdirSync(path.dirname(openapi), { recursive: true });
    writeFileSync(path.join(root, "docs", "api", "reference.md"), renderReference(JSON.parse(text), sha256(text)), "utf8");
    console.log("docs/api/openapi.json and docs/api/reference.md are current");
  } else if (command === "check") {
    const problems = checkDocs(root);
    if (problems.length > 0) {
      console.error(`Documentation check failed:\n${problems.map((p) => `  - ${p}`).join("\n")}`);
      process.exit(1);
    }
    console.log("Documentation is complete and current");
  } else {
    console.error("Usage: node scripts/docs.mjs api | reference | check");
    process.exit(2);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) main(process.argv.slice(2));
