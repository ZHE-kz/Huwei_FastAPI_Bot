import { describe, expect, it } from "vitest";
import { resolveAccountId } from "./account";

function storage(initial = {}) {
  const values = { ...initial };
  return {
    getItem: (key) => values[key] ?? null,
    setItem: (key, value) => { values[key] = value; },
  };
}

describe("LIFF account scope", () => {
  it("remembers an explicit account for later LIFF launches", () => {
    const saved = storage();
    expect(resolveAccountId("?account=second", saved)).toBe("second");
    expect(resolveAccountId("", saved)).toBe("second");
  });

  it("ignores invalid account values", () => {
    expect(resolveAccountId("?account=../../bad", storage())).toBe("default");
  });
});
