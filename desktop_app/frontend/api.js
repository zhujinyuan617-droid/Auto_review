// Thin fetch wrapper. Throws Error with .code = HTTP status; 503 is surfaced
// distinctly so views can render "未接通" instead of a generic error.
export async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = new Error(res.status === 503 ? "not_configured" : "HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}

export async function postJSON(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = new Error(res.status === 503 ? "not_configured" : "HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}

export async function putJSON(path, body) {
  const res = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = new Error(res.status === 503 ? "not_configured" : "HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}

export async function delJSON(path) {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) {
    const err = new Error("HTTP " + res.status);
    err.code = res.status;
    throw err;
  }
  return res.json();
}
