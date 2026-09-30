// Unified diff parser - no React, no DOM, unit-testable

export type DiffLineType = "add" | "del" | "context" | "meta";

export interface DiffLine {
  type: DiffLineType;
  content: string;
  oldLineNo: number | null;
  newLineNo: number | null;
}

export interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

export interface ParsedDiff {
  hunks: DiffHunk[];
  fileA: string;
  fileB: string;
}

const HUNK_HEADER_RE = /^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)/;

/**
 * Parses a unified diff string into structured hunks and lines.
 * Handles: empty string, missing trailing newline, "\ No newline at end of file",
 * multiple hunks, malformed input. Never throws.
 */
export function parseUnifiedDiff(text: string): ParsedDiff {
  if (!text || typeof text !== "string") {
    return { hunks: [], fileA: "", fileB: "" };
  }

  const lines = text.split("\n");
  let fileA = "";
  let fileB = "";
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const rawLine of lines) {
    // File headers
    if (rawLine.startsWith("--- ")) {
      fileA = rawLine.slice(4).trim();
      continue;
    }
    if (rawLine.startsWith("+++ ")) {
      fileB = rawLine.slice(4).trim();
      continue;
    }

    // Hunk header
    const hunkMatch = HUNK_HEADER_RE.exec(rawLine);
    if (hunkMatch) {
      currentHunk = { header: rawLine, lines: [] };
      hunks.push(currentHunk);
      oldLine = parseInt(hunkMatch[1] ?? "1", 10);
      newLine = parseInt(hunkMatch[3] ?? "1", 10);
      continue;
    }

    // "\ No newline at end of file" marker
    if (rawLine.startsWith("\\ No newline")) {
      if (currentHunk) {
        currentHunk.lines.push({
          type: "meta",
          content: rawLine,
          oldLineNo: null,
          newLineNo: null,
        });
      }
      continue;
    }

    if (!currentHunk) {
      // Lines before first hunk header (e.g. index/diff --git headers) are meta
      if (rawLine.trim() !== "") {
        currentHunk = { header: rawLine, lines: [] };
        // Don't push as hunk - treat as file-level meta; just skip
      }
      continue;
    }

    if (rawLine.startsWith("+")) {
      currentHunk.lines.push({
        type: "add",
        content: rawLine.slice(1),
        oldLineNo: null,
        newLineNo: newLine++,
      });
    } else if (rawLine.startsWith("-")) {
      currentHunk.lines.push({
        type: "del",
        content: rawLine.slice(1),
        oldLineNo: oldLine++,
        newLineNo: null,
      });
    } else if (rawLine.startsWith(" ") || rawLine === "") {
      currentHunk.lines.push({
        type: "context",
        content: rawLine.startsWith(" ") ? rawLine.slice(1) : "",
        oldLineNo: oldLine++,
        newLineNo: newLine++,
      });
    }
    // Any other line (index, diff --git inside a hunk) treated as meta - skip
  }

  return { hunks, fileA, fileB };
}