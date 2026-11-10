const ACCOUNT_PATTERN = /^[a-z0-9-]{1,32}$/;
const STORAGE_KEY = "liff_account_id";

export function resolveAccountId(search, storage = window.localStorage) {
  const requested = new URLSearchParams(search).get("account");
  if (ACCOUNT_PATTERN.test(requested || "")) {
    try { storage.setItem(STORAGE_KEY, requested); } catch { /* storage unavailable */ }
    return requested;
  }
  try {
    const saved = storage.getItem(STORAGE_KEY);
    if (ACCOUNT_PATTERN.test(saved || "")) return saved;
  } catch { /* storage unavailable */ }
  return "default";
}
