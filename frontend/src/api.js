// Thin API client. The demo role is sent as a header; this is NOT real authentication (see README).
let role = "client";
export const setRole = (r) => { role = r; };

async function call(method, path, body) {
  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-Demo-Role": role },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach the ProofPay server. Start the backend on port 8000.");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const msg = (data && (data.error || (typeof data.detail === "string" && data.detail))) ||
      (data && Array.isArray(data.detail) && "Please check the form: " + data.detail.map((d) => d.loc.slice(1).join(".")).join(", ")) ||
      `Request failed (${res.status}).`;
    const err = new Error(msg);
    err.code = data && data.code;
    throw err;
  }
  return data;
}

export const api = {
  config: () => call("GET", "/config"),
  list: () => call("GET", "/milestones"),
  get: (id) => call("GET", `/milestones/${id}`),
  create: (b) => call("POST", "/milestones", b),
  editCriteria: (id, criteria) => call("PUT", `/milestones/${id}/criteria`, criteria),
  suggest: (description) => call("POST", "/criteria/suggest", { description }),
  createOrder: (id) => call("POST", `/milestones/${id}/fund/create-order`),
  authorize: (id, order_id) => call("POST", `/milestones/${id}/fund/authorize`, { order_id }),
  submit: (id, b) => call("POST", `/milestones/${id}/submit`, b),
  release: (id, b) => call("POST", `/milestones/${id}/release`, b),
  reset: () => call("POST", "/demo/reset"),
};

export const STATUS = {
  draft: { label: "Not funded", tone: "idle" },
  funded: { label: "Funds on hold", tone: "hold" },
  verified: { label: "Proof ready", tone: "info" },
  revision_requested: { label: "Revision requested", tone: "hold" },
  paid: { label: "Paid", tone: "ok" },
  partially_paid: { label: "Partly paid", tone: "ok" },
  voided: { label: "Hold released", tone: "idle" },
  payment_pending: { label: "Payment pending", tone: "hold" },
  authorization_expired: { label: "Hold expired", tone: "bad" },
  needs_attention: { label: "Needs attention", tone: "bad" },
};

export const money = (v, cur = "USD") => `${cur === "USD" ? "$" : cur + " "}${v}`;
export const fmtDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};
