import { describe, expect, it } from "vitest";
import { translate } from "./i18n";

describe("LIFF i18n", () => {
  it("switches among supported languages", () => {
    expect(translate("zh-TW", "home")).toBe("總覽");
    expect(translate("en-US", "home")).toBe("Overview");
    expect(translate("ja-JP", "home")).toBe("概要");
  });

  it("falls back to zh-TW", () => {
    expect(translate("invalid", "home")).toBe("總覽");
  });

  it("interpolates dashboard values", () => {
    expect(translate("zh-TW", "heroSummary", { history: 2, favorites: 3 }))
      .toBe("已有 2 筆探索紀錄 · 收藏 3 筆地方記憶");
  });
});
