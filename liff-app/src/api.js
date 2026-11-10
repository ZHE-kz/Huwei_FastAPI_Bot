let csrfToken = "";

export const setCsrfToken = (value) => { csrfToken = value; };

export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken && !["GET", "HEAD"].includes(options.method || "GET")
        ? { "X-CSRF-Token": csrfToken }
        : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? null : response.json();
}
