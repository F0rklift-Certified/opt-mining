/**
 * Static scope-guard test for the Opt-Mining Frontend_App (S3-01a, task 6.6).
 *
 * This is the FRONTEND HALF of the design's Property 3 ("Cross-service URLs and
 * origins are env-driven, never hard-coded") plus the design's static
 * frontend-scope guard from the Testing Strategy. It reads the actual web
 * sources under `app/web/` and asserts the thin-shell scope boundary this
 * ticket must hold (Requirements 3.5, 4.3, 8.1, 8.2):
 *
 *   1. NO scoring / ranking / normalisation / exclusion arithmetic — i.e. no
 *      decision logic lives in the frontend (R3.5, R8.2).
 *   2. NO typed service client — the S3-01b client is not present yet (R8.1).
 *   3. NO data-quality banner — the S3-01b banner is not present yet (R8.1).
 *   4. NO hard-coded host address — the backend base URL resolves ONLY from
 *      `NEXT_PUBLIC_API_BASE_URL`; the sole reference is
 *      `process.env.NEXT_PUBLIC_API_BASE_URL` and no bare `http(s)://<host>`
 *      literal appears in source (R4.3).
 *
 * Feature: s3-01a-application-shell-scaffold, Property 3: Cross-service URLs and
 * origins are env-driven, never hard-coded (frontend half — R4.3).
 *
 * Because this is a source-content scan, it deliberately strips comments and
 * string/template literals before checking for host literals and decision
 * arithmetic, so prose that merely NAMES a scheme (e.g. a docstring mentioning
 * `http://localhost:8000` as an example) does not trip a false positive. Only
 * live code is inspected for banned patterns.
 */
import { readFileSync } from "fs";
import { join } from "path";

/** Repo-relative root of the frontend app (this test lives in app/web/__tests__). */
const WEB_ROOT = join(__dirname, "..");

/**
 * The frontend source files this ticket produces. layout.tsx, the two shell
 * components, page.tsx and next.config.js are the entire hand-written surface
 * of the shell; globals.css is pure styling. If a new source file is added it
 * should be listed here so the guard keeps full coverage.
 */
const SOURCE_FILES = [
  "app/layout.tsx",
  "app/page.tsx",
  "app/shell/AppShell.tsx",
  "app/shell/PlaceholderRegion.tsx",
  "next.config.js",
] as const;

/** Read a frontend source file as UTF-8 text. */
function readSource(relPath: string): string {
  return readFileSync(join(WEB_ROOT, relPath), "utf8");
}

/**
 * Strip line comments (`// …`) and block comments only, leaving string/template
 * literal CONTENTS intact. Used for the host-literal check: a hard-coded URL is
 * always written as a string (a bare `http://…` is not valid JS), so we must
 * keep string contents to catch it — while still ignoring a scheme/host that is
 * only NAMED in a comment or docstring (the false-positive the task warns about).
 *
 * `.env.example` is documentation and is not scanned; `next.config.js` documents
 * the variable only in a comment, which this strips.
 */
function stripCommentsOnly(src: string): string {
  let out = "";
  let i = 0;
  const n = src.length;
  type Mode = "code" | "line-comment" | "block-comment" | "single" | "double" | "template";
  let mode: Mode = "code";
  while (i < n) {
    const c = src[i];
    const next = i + 1 < n ? src[i + 1] : "";
    if (mode === "code") {
      if (c === "/" && next === "/") { mode = "line-comment"; i += 2; continue; }
      if (c === "/" && next === "*") { mode = "block-comment"; i += 2; continue; }
      if (c === "'") { out += c; mode = "single"; i += 1; continue; }
      if (c === '"') { out += c; mode = "double"; i += 1; continue; }
      if (c === "`") { out += c; mode = "template"; i += 1; continue; }
      out += c; i += 1; continue;
    }
    if (mode === "line-comment") { if (c === "\n") { out += "\n"; mode = "code"; } i += 1; continue; }
    if (mode === "block-comment") { if (c === "*" && next === "/") { mode = "code"; i += 2; continue; } if (c === "\n") out += "\n"; i += 1; continue; }
    // inside a string: keep everything, but handle escapes and closing quote
    if (c === "\\") { out += c + next; i += 2; continue; }
    const closes =
      (mode === "single" && c === "'") ||
      (mode === "double" && c === '"') ||
      (mode === "template" && c === "`");
    out += c;
    if (closes) mode = "code";
    i += 1;
  }
  return out;
}

/**
 * Strip line comments (`// …`), block comments (`/* … *\/`) and string/template
 * literals from JS/TS source, leaving only "live" code. Used so that a scheme
 * or host mentioned in prose or documented in an example string is not mistaken
 * for a hard-coded literal in executable code.
 *
 * This is a pragmatic scanner (not a full parser); it is intentionally
 * conservative — it blanks the CONTENTS of literals rather than removing the
 * quotes, which is all the assertions below need.
 */
function stripCommentsAndStrings(src: string): string {
  let out = "";
  let i = 0;
  const n = src.length;

  type Mode =
    | "code"
    | "line-comment"
    | "block-comment"
    | "single"
    | "double"
    | "template";
  let mode: Mode = "code";

  while (i < n) {
    const c = src[i];
    const next = i + 1 < n ? src[i + 1] : "";

    if (mode === "code") {
      if (c === "/" && next === "/") {
        mode = "line-comment";
        i += 2;
        continue;
      }
      if (c === "/" && next === "*") {
        mode = "block-comment";
        i += 2;
        continue;
      }
      if (c === "'") {
        out += "'";
        mode = "single";
        i += 1;
        continue;
      }
      if (c === '"') {
        out += '"';
        mode = "double";
        i += 1;
        continue;
      }
      if (c === "`") {
        out += "`";
        mode = "template";
        i += 1;
        continue;
      }
      out += c;
      i += 1;
      continue;
    }

    if (mode === "line-comment") {
      if (c === "\n") {
        out += "\n";
        mode = "code";
      }
      i += 1;
      continue;
    }

    if (mode === "block-comment") {
      if (c === "*" && next === "/") {
        mode = "code";
        i += 2;
        continue;
      }
      // Preserve newlines so line-based reasoning stays roughly aligned.
      if (c === "\n") out += "\n";
      i += 1;
      continue;
    }

    // Inside a string/template literal: skip escaped chars, blank the contents.
    if (mode === "single" || mode === "double" || mode === "template") {
      if (c === "\\") {
        i += 2; // skip the escaped char
        continue;
      }
      const closes =
        (mode === "single" && c === "'") ||
        (mode === "double" && c === '"') ||
        (mode === "template" && c === "`");
      if (closes) {
        out += c;
        mode = "code";
        i += 1;
        continue;
      }
      // Blank literal content (keep newlines to preserve line structure).
      if (c === "\n") out += "\n";
      i += 1;
      continue;
    }
  }

  return out;
}

describe("Frontend scope guard — thin, decision-free shell (S3-01a, task 6.6)", () => {
  /** Live code (comments + string contents removed) for every source file. */
  const liveCode: Record<string, string> = {};
  /** Comments removed, string CONTENTS kept — for the host-literal check. */
  const codeWithStrings: Record<string, string> = {};
  /** Raw text for every source file (used only for env-reference assertions). */
  const rawText: Record<string, string> = {};

  beforeAll(() => {
    for (const f of SOURCE_FILES) {
      const raw = readSource(f);
      rawText[f] = raw;
      liveCode[f] = stripCommentsAndStrings(raw);
      codeWithStrings[f] = stripCommentsOnly(raw);
    }
  });

  describe("no decision logic — no scoring / ranking / normalisation / exclusion (R3.5, R8.2)", () => {
    // Identifiers that would indicate decision arithmetic being performed in
    // the frontend. Matched as whole words in LIVE CODE only, so a comment or
    // a region label string that merely mentions "ranked results" is ignored.
    const DECISION_TERMS = [
      "suitabilityScore",
      "suitability_score",
      "normalise",
      "normalize",
      "computeScore",
      "computeRank",
      "rankCells",
      "weightedSum",
      "exclusionMask",
      "applyWeights",
    ];

    it.each(SOURCE_FILES)(
      "%s contains no decision-arithmetic identifiers in live code",
      (file) => {
        const code = liveCode[file];
        for (const term of DECISION_TERMS) {
          const re = new RegExp(`\\b${term}\\b`);
          expect(code).not.toMatch(re);
        }
      },
    );

    it.each(SOURCE_FILES)(
      "%s does not iterate/sort a collection to rank or score it",
      (file) => {
        const code = liveCode[file];
        // No array sort/reduce (the shapes ranking/scoring would take) and no
        // arithmetic-bearing map over cells. The shell renders fixed markup.
        expect(code).not.toMatch(/\.sort\s*\(/);
        expect(code).not.toMatch(/\.reduce\s*\(/);
      },
    );
  });

  describe("no typed service client (S3-01b) (R8.1)", () => {
    it.each(SOURCE_FILES)("%s performs no HTTP request", (file) => {
      const code = liveCode[file];
      // The shell makes NO calls in this ticket (calling the backend is S3-01b).
      expect(code).not.toMatch(/\bfetch\s*\(/);
      expect(code).not.toMatch(/\baxios\b/);
      expect(code).not.toMatch(/XMLHttpRequest/);
      expect(code).not.toMatch(/new\s+WebSocket/);
      // No React data-fetching effects wired up either.
      expect(code).not.toMatch(/\buseSWR\b/);
      expect(code).not.toMatch(/\buseQuery\b/);
    });

    it.each(SOURCE_FILES)(
      "%s imports no generated/typed service client module",
      (file) => {
        const code = liveCode[file];
        // No import of a client/api/sdk/openapi module (the S3-01b artefact).
        expect(code).not.toMatch(
          /import[^;]*from\s*['"][^'"]*(apiClient|api-client|serviceClient|service-client|generated|openapi|sdk)[^'"]*['"]/i,
        );
      },
    );
  });

  describe("no data-quality banner (S3-01b) (R8.1)", () => {
    it.each(SOURCE_FILES)(
      "%s references no data-quality banner symbol in live code",
      (file) => {
        const code = liveCode[file];
        expect(code).not.toMatch(/\bDataQualityBanner\b/);
        expect(code).not.toMatch(/\bdataQuality\b/i);
        expect(code).not.toMatch(/\bqualityBanner\b/i);
      },
    );
  });

  describe("backend base URL is env-driven, never hard-coded (R4.3, Property 3)", () => {
    it.each(SOURCE_FILES)(
      "%s hard-codes no http(s) host literal (comments excluded, string literals scanned)",
      (file) => {
        // A hard-coded URL is always a STRING literal (a bare http://… is not
        // valid JS), so we scan code WITH string contents but WITHOUT comments:
        // a real baked-in host is caught, while a scheme merely named in a
        // comment/docstring is not (the false positive the task warns about).
        const code = codeWithStrings[file];
        expect(code).not.toMatch(/https?:\/\//);
      },
    );

    it("the only source that resolves the base URL is AppShell, via process.env.NEXT_PUBLIC_API_BASE_URL", () => {
      // Exactly one source file may read the base URL, and it must read it from
      // the environment variable — not from any other source.
      const referencing = SOURCE_FILES.filter((f) =>
        /NEXT_PUBLIC_API_BASE_URL/.test(rawText[f]),
      );

      // layout/page/shell components: only AppShell surfaces the value; and the
      // .env.example / next.config.js DOCUMENT the variable in comments.
      const codeReferencing = SOURCE_FILES.filter((f) =>
        /NEXT_PUBLIC_API_BASE_URL/.test(liveCode[f]),
      );

      expect(codeReferencing).toEqual(["app/shell/AppShell.tsx"]);
      // Sanity: the variable is at least documented/used somewhere.
      expect(referencing.length).toBeGreaterThan(0);
    });

    it("AppShell reads the base URL only through process.env.NEXT_PUBLIC_API_BASE_URL", () => {
      const code = liveCode["app/shell/AppShell.tsx"];
      // The env read must be present…
      expect(code).toMatch(/process\.env\.NEXT_PUBLIC_API_BASE_URL/);
      // …and it must be the ONLY way the base URL enters the component: every
      // NEXT_PUBLIC_API_BASE_URL occurrence in live code is prefixed by
      // `process.env.`.
      const bareEnvRefs = code.match(/(?<!process\.env\.)NEXT_PUBLIC_API_BASE_URL/g);
      expect(bareEnvRefs).toBeNull();
    });
  });
});
