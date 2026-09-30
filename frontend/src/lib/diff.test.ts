import { describe, it, expect } from "vitest";
import { parseUnifiedDiff } from "@/lib/diff";

const SIMPLE_DIFF = `--- a/index.html
+++ b/index.html
@@ -1,3 +1,4 @@
 <html>
-<title>Old</title>
+<title>New</title>
+<meta charset="utf-8">
 </html>`;

const MULTI_HUNK_DIFF = `--- a/file.js
+++ b/file.js
@@ -1,4 +1,4 @@
 function foo() {
-  return 1;
+  return 2;
 }
@@ -10,3 +10,3 @@
 function bar() {
-  return "a";
+  return "b";
 }`;

const NO_NEWLINE_DIFF = `--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,2 @@
 context line
-old line
\\ No newline at end of file
+new line
\\ No newline at end of file`;

describe("parseUnifiedDiff - normal diff", () => {
  it("extracts fileA and fileB", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    expect(r.fileA).toBe("a/index.html");
    expect(r.fileB).toBe("b/index.html");
  });

  it("produces one hunk", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    expect(r.hunks).toHaveLength(1);
  });

  it("identifies del lines correctly", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    const dels = r.hunks[0]!.lines.filter((l) => l.type === "del");
    expect(dels).toHaveLength(1);
    expect(dels[0]!.content).toBe("<title>Old</title>");
  });

  it("identifies add lines correctly", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    const adds = r.hunks[0]!.lines.filter((l) => l.type === "add");
    expect(adds).toHaveLength(2);
  });

  it("identifies context lines correctly", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    const ctx = r.hunks[0]!.lines.filter((l) => l.type === "context");
    expect(ctx.length).toBeGreaterThanOrEqual(1);
  });

  it("assigns newLineNo to add lines", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    const adds = r.hunks[0]!.lines.filter((l) => l.type === "add");
    expect(adds[0]!.newLineNo).not.toBeNull();
    expect(adds[0]!.oldLineNo).toBeNull();
  });

  it("assigns oldLineNo to del lines", () => {
    const r = parseUnifiedDiff(SIMPLE_DIFF);
    const dels = r.hunks[0]!.lines.filter((l) => l.type === "del");
    expect(dels[0]!.oldLineNo).not.toBeNull();
    expect(dels[0]!.newLineNo).toBeNull();
  });
});

describe("parseUnifiedDiff - empty / blank input", () => {
  it("returns empty hunks for empty string", () => {
    const r = parseUnifiedDiff("");
    expect(r.hunks).toHaveLength(0);
    expect(r.fileA).toBe("");
    expect(r.fileB).toBe("");
  });

  it("does not throw for empty string", () => {
    expect(() => parseUnifiedDiff("")).not.toThrow();
  });

  it("returns empty hunks for whitespace-only string", () => {
    const r = parseUnifiedDiff("   \n  \n  ");
    expect(r.hunks).toHaveLength(0);
  });
});

describe("parseUnifiedDiff - multiple hunks", () => {
  it("produces two hunks", () => {
    const r = parseUnifiedDiff(MULTI_HUNK_DIFF);
    expect(r.hunks).toHaveLength(2);
  });

  it("both hunks have del and add lines", () => {
    const r = parseUnifiedDiff(MULTI_HUNK_DIFF);
    for (const hunk of r.hunks) {
      expect(hunk.lines.some((l) => l.type === "del")).toBe(true);
      expect(hunk.lines.some((l) => l.type === "add")).toBe(true);
    }
  });
});

describe("parseUnifiedDiff - no-trailing-newline marker", () => {
  it("does not throw", () => {
    expect(() => parseUnifiedDiff(NO_NEWLINE_DIFF)).not.toThrow();
  });

  it("produces meta lines for the no-newline markers", () => {
    const r = parseUnifiedDiff(NO_NEWLINE_DIFF);
    const metas = r.hunks[0]!.lines.filter((l) => l.type === "meta");
    expect(metas.length).toBeGreaterThanOrEqual(1);
  });
});

describe("parseUnifiedDiff - malformed input", () => {
  it("does not throw for random text", () => {
    expect(() => parseUnifiedDiff("hello world\nthis is not a diff")).not.toThrow();
  });

  it("does not throw for partial hunk header with no lines", () => {
    expect(() => parseUnifiedDiff("@@ -1,2 +1,2 @@")).not.toThrow();
  });

  it("returns fileA/fileB empty when headers are missing", () => {
    const r = parseUnifiedDiff("@@ -1,1 +1,1 @@\n-old\n+new\n");
    expect(r.fileA).toBe("");
    expect(r.fileB).toBe("");
  });

  it("does not throw for diff missing trailing newline", () => {
    const noeol = SIMPLE_DIFF.trimEnd();
    expect(() => parseUnifiedDiff(noeol)).not.toThrow();
  });
});