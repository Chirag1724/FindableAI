import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  URL_HISTORY_KEY,
  clearUrlHistory,
  pushUrlHistory,
  readUrlHistory,
  removeUrlHistory,
} from "./urlHistory";

describe("urlHistory", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => store.clear(),
    });
    store.clear();
  });

  it("stores up to 3 URLs, newest first, deduped", () => {
    pushUrlHistory("https://a.com");
    pushUrlHistory("https://b.com");
    pushUrlHistory("https://c.com");
    pushUrlHistory("https://d.com");
    expect(readUrlHistory()).toEqual([
      "https://d.com",
      "https://c.com",
      "https://b.com",
    ]);

    pushUrlHistory("https://B.com");
    expect(readUrlHistory()).toEqual([
      "https://B.com",
      "https://d.com",
      "https://c.com",
    ]);
  });

  it("removes a single entry", () => {
    pushUrlHistory("https://a.com");
    pushUrlHistory("https://b.com");
    expect(removeUrlHistory("https://a.com")).toEqual(["https://b.com"]);
  });

  it("clears all", () => {
    pushUrlHistory("https://a.com");
    clearUrlHistory();
    expect(readUrlHistory()).toEqual([]);
    expect(localStorage.getItem(URL_HISTORY_KEY)).toBe("[]");
  });
});
