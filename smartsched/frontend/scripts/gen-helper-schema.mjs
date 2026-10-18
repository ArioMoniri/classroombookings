#!/usr/bin/env node
// HX-01: generate the zod schema of the helper card contract (`helper.card.v1`) from the backend's JSON Schema
// snapshot (smartsched/backend/tests/helper/fixtures/helper_card_v1.schema.json, the same object `GET /helper/schema`
// answers under `card`). Run after the backend refreshes its snapshot (`UPDATE_HELPER_SNAPSHOT=1`):
//
//   node scripts/gen-helper-schema.mjs            # rewrites src/components/helper/schema.gen.ts
//   node scripts/gen-helper-schema.mjs --check    # exit 1 when the generated file is out of date
//
// Only the JSON Schema subset pydantic emits for the card models is supported (object, string with pattern /
// maxLength / minLength / format, integer, number, boolean, null, enum, const, array with min / max items, anyOf,
// $ref, patternProperties records, the root oneOf with a discriminator). Anything else throws, so a new keyword in
// the backend snapshot fails loudly instead of being dropped.
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const SCHEMA_PATH = resolve(here, "../../backend/tests/helper/fixtures/helper_card_v1.schema.json");
export const OUT_PATH = resolve(here, "../src/components/helper/schema.gen.ts");

const KNOWN = new Set([
  "type", "title", "description", "default", "$ref", "pattern", "maxLength", "minLength", "anyOf", "additionalProperties",
  "properties", "required", "const", "items", "maxItems", "minItems", "enum", "patternProperties", "propertyNames",
  "format", "minimum", "maximum",
]);

const lit = (v) => JSON.stringify(v);
const re = (pattern) => `new RegExp(${lit(pattern)})`;

function refName(ref) {
  const m = /^#\/\$defs\/(\w+)$/.exec(ref);
  if (!m) throw new Error(`unsupported $ref ${ref}`);
  return m[1];
}

function check(node, where) {
  for (const k of Object.keys(node)) if (!KNOWN.has(k)) throw new Error(`unsupported keyword "${k}" at ${where}`);
}

/** zod expression for one schema node (without optional / default handling). */
function expr(node, where) {
  check(node, where);
  if (node.$ref) return refName(node.$ref);
  if (node.anyOf) {
    const nonNull = node.anyOf.filter((n) => n.type !== "null");
    const hasNull = nonNull.length !== node.anyOf.length;
    const inner = nonNull.length === 1 ? expr(nonNull[0], `${where}.anyOf`) : `z.union([${nonNull.map((n, i) => expr(n, `${where}.anyOf[${i}]`)).join(", ")}])`;
    return hasNull ? `${inner}.nullable()` : inner;
  }
  if ("const" in node) return `z.literal(${lit(node.const)})`;
  if (node.enum) return `z.enum([${node.enum.map(lit).join(", ")}])`;
  switch (node.type) {
    case "string": {
      let s = node.format === "date-time" ? "z.iso.datetime({ offset: true, local: true })" : "z.string()";
      if (node.format && node.format !== "date-time") throw new Error(`unsupported format ${node.format} at ${where}`);
      if (node.minLength !== undefined) s += `.min(${node.minLength})`;
      if (node.maxLength !== undefined) s += `.max(${node.maxLength})`;
      if (node.pattern) s += `.regex(${re(node.pattern)})`;
      return s;
    }
    case "integer":
    case "number": {
      let s = node.type === "integer" ? "z.number().int()" : "z.number()";
      if (node.minimum !== undefined) s += `.min(${node.minimum})`;
      if (node.maximum !== undefined) s += `.max(${node.maximum})`;
      return s;
    }
    case "boolean":
      return "z.boolean()";
    case "null":
      return "z.null()";
    case "array": {
      let s = `z.array(${expr(node.items, `${where}.items`)})`;
      if (node.minItems !== undefined) s += `.min(${node.minItems})`;
      if (node.maxItems !== undefined) s += `.max(${node.maxItems})`;
      return s;
    }
    case "object":
      return object(node, where);
    default:
      throw new Error(`unsupported type ${node.type} at ${where}`);
  }
}

function object(node, where) {
  if (node.patternProperties) {
    const entries = Object.entries(node.patternProperties);
    if (entries.length !== 1 || node.properties) throw new Error(`unsupported patternProperties at ${where}`);
    const [pattern, value] = entries[0];
    let key = `z.string().regex(${re(pattern)})`;
    if (node.propertyNames?.maxLength !== undefined) key += `.max(${node.propertyNames.maxLength})`;
    return `z.record(${key}, ${expr(value, `${where}.patternProperties`)})`;
  }
  const required = new Set(node.required ?? []);
  const props = Object.entries(node.properties ?? {}).map(([name, prop]) => {
    let e = expr(prop, `${where}.${name}`);
    // the discriminator (`type`) is always sent; it stays a plain literal so the union can switch on it
    if (name === "type" && "const" in prop) return `  ${name}: ${e},`;
    if (!required.has(name)) {
      const nullable = prop.anyOf?.some((n) => n.type === "null");
      // the server dumps with exclude_none: a null field is simply absent
      if (prop.default === null || nullable) e = nullable ? e.replace(/\.nullable\(\)$/, "") + ".nullish()" : `${e}.nullish()`;
      else if (prop.default !== undefined) e += `.default(${lit(prop.default)})`;
      else e += ".optional()";
    }
    return `  ${name}: ${e},`;
  });
  const body = `{\n${props.join("\n")}\n}`;
  return node.additionalProperties === false ? `z.strictObject(${body})` : `z.object(${body})`;
}

function deps(node, out = new Set()) {
  if (Array.isArray(node)) node.forEach((n) => deps(n, out));
  else if (node && typeof node === "object") {
    if (typeof node.$ref === "string") out.add(refName(node.$ref));
    Object.values(node).forEach((n) => deps(n, out));
  }
  return out;
}

/** The generated TypeScript for one JSON Schema object (pure: the test calls it on the backend snapshot). */
export function generate(schema, sourceText) {
  const defs = schema.$defs ?? {};
  const order = [];
  const seen = new Set();
  const visit = (name, stack = []) => {
    if (seen.has(name)) return;
    if (stack.includes(name)) throw new Error(`recursive $ref ${[...stack, name].join(" → ")}`);
    for (const d of deps(defs[name])) visit(d, [...stack, name]);
    seen.add(name);
    order.push(name);
  };
  Object.keys(defs).sort().forEach((n) => visit(n));
  const disc = schema.discriminator?.propertyName;
  if (!disc || !Array.isArray(schema.oneOf)) throw new Error("the root must be a oneOf with a discriminator");
  const members = schema.oneOf.map((n) => refName(n.$ref));
  const mapping = Object.entries(schema.discriminator.mapping ?? {}).map(([type, ref]) => [type, refName(ref)]);
  const sha = createHash("sha256").update(sourceText).digest("hex");
  const lines = [
    "// GENERATED by scripts/gen-helper-schema.mjs from smartsched/backend/tests/helper/fixtures/helper_card_v1.schema.json",
    "// (`GET /helper/schema` → `card`). Do not edit: run `node scripts/gen-helper-schema.mjs` after the backend snapshot",
    "// changes; schema.gen.test.ts fails while this file is out of date.",
    'import { z } from "zod";',
    "",
    `export const HELPER_CARD_SCHEMA_ID = ${lit(schema.$id ?? "")};`,
    `export const HELPER_CARD_SCHEMA_SHA256 = ${lit(sha)};`,
    "",
  ];
  for (const name of order) {
    const def = defs[name];
    if (def.description) lines.push(`/** ${def.description.replace(/\*\//g, "* /").replace(/\s*\n\s*/g, " ")} */`);
    lines.push(`export const ${name} = ${expr(def, name)};`);
    lines.push(`export type ${name} = z.infer<typeof ${name}>;`);
    lines.push("");
  }
  lines.push(`/** ${schema.title ?? "card"}: one of the wire types, switched on \`${disc}\`. */`);
  lines.push(`export const HelperCard = z.discriminatedUnion(${lit(disc)}, [${members.join(", ")}]);`);
  lines.push("export type HelperCard = z.infer<typeof HelperCard>;");
  lines.push("");
  lines.push(`export const CARD_TYPES = [${mapping.map(([t]) => lit(t)).join(", ")}] as const;`);
  lines.push("export type CardType = (typeof CARD_TYPES)[number];");
  lines.push("");
  return lines.join("\n");
}

function main() {
  const text = readFileSync(SCHEMA_PATH, "utf8");
  const out = generate(JSON.parse(text), text);
  if (process.argv.includes("--check")) {
    const now = readFileSync(OUT_PATH, "utf8");
    if (now !== out) {
      console.error("schema.gen.ts is out of date: run node scripts/gen-helper-schema.mjs");
      process.exit(1);
    }
    console.log("schema.gen.ts is up to date");
    return;
  }
  writeFileSync(OUT_PATH, out);
  console.log(`wrote ${OUT_PATH}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
