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

// 统一任务轮询:用户已离开 hashPrefix 屏即静默停止(返回 {status:"detached"}),
// 任务本身在服务端继续——绝不在别的屏上"完成后劫持/重画"。P0 串台修复的公共件。
export async function pollJob(jobId, { hashPrefix, onTick, intervalMs = 1000, maxTicks = 1800 } = {}) {
  for (let i = 0; i < maxTicks; i++) {
    if (hashPrefix && !location.hash.startsWith(hashPrefix)) {
      return { status: "detached", job_id: jobId };
    }
    const job = await getJSON("/jobs/" + jobId);
    if (onTick) onTick(job, i);
    if (job.status !== "running") return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return { status: "timeout", job_id: jobId };
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
