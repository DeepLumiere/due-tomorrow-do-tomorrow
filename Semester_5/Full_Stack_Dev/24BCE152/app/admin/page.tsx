"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Check,
  Clock,
  Database,
  Eye,
  EyeOff,
  KeyRound,
  Layers3,
  Lock,
  LogOut,
  Mail,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import ThemeToggle from "@/lib/ThemeToggle";

type AdminEvaluation = {
  _id: string;
  model: string;
  organization: string;
  benchmark: string;
  score: number;
  metric: string;
  category: string;
  source?: string;
  status?: "pending" | "approved" | "rejected";
  submittedBy?: string;
  submittedByEmail?: string;
  evaluatedAt: string;
  createdAt?: string;
  reviewedAt?: string;
  reviewedBy?: string;
};

type Counts = {
  total: number;
  pending: number;
  approved: number;
  rejected: number;
};

export default function AdminPage() {
  const [adminToken, setAdminToken] = useState<string | null>(null);
  const [adminEmail, setAdminEmail] = useState<string>("");
  const [authChecking, setAuthChecking] = useState(true);

  // Admin login form states
  const [loginEmail, setLoginEmail] = useState("admin@evalboard.com");
  const [loginPassword, setLoginPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  // Admin console states
  const [evaluations, setEvaluations] = useState<AdminEvaluation[]>([]);
  const [counts, setCounts] = useState<Counts>({ total: 0, pending: 0, approved: 0, rejected: 0 });
  const [activeTab, setActiveTab] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [selected, setSelected] = useState<AdminEvaluation | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function loadData(tokenToUse?: string) {
    const token = tokenToUse || adminToken;
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/evaluations", {
        headers: { "x-admin-token": token },
        cache: "no-store",
      });
      if (response.status === 401) {
        handleAdminLogout();
        throw new Error("Admin session expired. Please sign in again.");
      }
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to load admin evaluations.");
      setEvaluations(data.evaluations || []);
      setCounts(data.counts || { total: 0, pending: 0, approved: 0, rejected: 0 });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin evaluations.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    try {
      const storedToken =
        sessionStorage.getItem("evalboard_admin_token") || localStorage.getItem("evalboard_admin_token");
      const storedEmail =
        sessionStorage.getItem("evalboard_admin_email") || localStorage.getItem("evalboard_admin_email");
      if (storedToken) {
        setAdminToken(storedToken);
        setAdminEmail(storedEmail || "admin@evalboard.com");
        void loadData(storedToken);
      }
    } catch {
      /* Ignore */
    } finally {
      setAuthChecking(false);
    }
  }, []);

  async function handleAdminLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError("");
    try {
      const response = await fetch("/api/admin/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Invalid admin credentials.");

      sessionStorage.setItem("evalboard_admin_token", data.token);
      sessionStorage.setItem("evalboard_admin_email", data.admin.email);
      setAdminToken(data.token);
      setAdminEmail(data.admin.email);
      void loadData(data.token);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setLoginLoading(false);
    }
  }

  function handleAdminLogout() {
    try {
      sessionStorage.removeItem("evalboard_admin_token");
      sessionStorage.removeItem("evalboard_admin_email");
      localStorage.removeItem("evalboard_admin_token");
      localStorage.removeItem("evalboard_admin_email");
    } catch {
      /* Ignore */
    }
    setAdminToken(null);
    setEvaluations([]);
    setLoginPassword("");
  }

  async function updateStatus(id: string, status: "approved" | "rejected" | "pending") {
    if (!adminToken) return;
    setActionLoading(id);
    try {
      const response = await fetch("/api/admin/evaluations", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "x-admin-token": adminToken,
        },
        body: JSON.stringify({ id, status }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to update status.");

      setEvaluations((prev) =>
        prev.map((item) => (item._id === id ? { ...item, status, reviewedAt: new Date().toISOString() } : item))
      );

      void loadData();

      setNotice(`Evaluation marked as ${status}.`);
      setTimeout(() => setNotice(null), 3500);
      if (selected && selected._id === id) {
        setSelected((prev) => (prev ? { ...prev, status } : null));
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update status.");
    } finally {
      setActionLoading(null);
    }
  }

  async function deleteEvaluation(id: string, modelName: string) {
    if (!adminToken) return;
    if (!confirm(`Are you sure you want to permanently delete evaluation for "${modelName}"?`)) return;
    setActionLoading(id);
    try {
      const response = await fetch("/api/admin/evaluations", {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "x-admin-token": adminToken,
        },
        body: JSON.stringify({ id }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Failed to delete evaluation.");

      setEvaluations((prev) => prev.filter((item) => item._id !== id));
      void loadData();
      setNotice(`Evaluation deleted.`);
      setTimeout(() => setNotice(null), 3000);
      if (selected && selected._id === id) setSelected(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete evaluation.");
    } finally {
      setActionLoading(null);
    }
  }

  const visibleEvaluations = useMemo(() => {
    return evaluations.filter((item) => {
      const itemStatus = item.status || "approved";
      const matchesTab = activeTab === "all" || itemStatus === activeTab;
      const needle = query.toLowerCase().trim();
      const matchesQuery =
        !needle ||
        [
          item.model,
          item.organization,
          item.benchmark,
          item.category,
          item.submittedBy || "",
          item.submittedByEmail || "",
        ].some((v) => v.toLowerCase().includes(needle));
      return matchesTab && matchesQuery;
    });
  }, [evaluations, activeTab, query]);

  if (authChecking) {
    return (
      <main className="shell admin-shell" style={{ display: "grid", placeItems: "center", minHeight: "80vh" }}>
        <div style={{ textAlign: "center", color: "var(--text-secondary)" }}>
          <span className="spinner" /> Verifying administrator credentials…
        </div>
      </main>
    );
  }

  if (!adminToken) {
    return (
      <main className="shell admin-shell">
        <header className="topbar">
          <div className="admin-brand-wrap">
            <a className="brand" href="/" aria-label="Evalboard home">
              <span className="brand-mark">
                <Layers3 size={19} strokeWidth={2.3} />
              </span>
              <span>
                evalboard<span className="brand-dot">.</span>
              </span>
            </a>
            <span className="admin-pill">
              <Shield size={12} /> Restricted Area
            </span>
          </div>
          <div className="top-actions">
            <ThemeToggle />
            <a className="button button-outline button-small" href="/">
              <ArrowLeft size={14} /> Back to Live Board
            </a>
          </div>
        </header>

        <section className="admin-login-section">
          <div className="admin-login-card">
            <div className="admin-login-icon">
              <KeyRound size={28} />
            </div>
            <div className="eyebrow" style={{ justifyContent: "center" }}>
              <ShieldCheck size={12} /> EVALBOARD SECURITY GATEWAY
            </div>
            <h2>Admin Authentication</h2>
            <p>Enter your administrator credentials to access the evaluation card moderation console.</p>

            <form onSubmit={handleAdminLogin} className="admin-login-form">
              <label className="login-field">
                <span className="login-label">Admin Email</span>
                <div className="login-input-wrap">
                  <Mail size={15} className="login-input-icon" />
                  <input
                    type="email"
                    placeholder="admin@evalboard.com"
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    required
                    autoComplete="username"
                  />
                </div>
              </label>

              <label className="login-field">
                <span className="login-label">Admin Password</span>
                <div className="login-input-wrap">
                  <Lock size={15} className="login-input-icon" />
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter admin password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="login-eye"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </label>

              {loginError && <p className="login-error">{loginError}</p>}

              <button className="button button-dark login-submit" type="submit" disabled={loginLoading}>
                {loginLoading ? (
                  <>
                    <span className="spinner light-spinner" /> Verifying credentials…
                  </>
                ) : (
                  <>
                    <Shield size={15} /> Unlock Admin Console
                  </>
                )}
              </button>
            </form>

            <div className="admin-creds-hint">
              <Shield size={13} />
              <div>
                <strong>Default Administrator Access:</strong>
                <span>
                  Email: <code>admin@evalboard.com</code> &bull; Password: <code>admin123</code>
                </span>
              </div>
            </div>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell admin-shell">
      <header className="topbar">
        <div className="admin-brand-wrap">
          <a className="brand" href="/" aria-label="Evalboard home">
            <span className="brand-mark">
              <Layers3 size={19} strokeWidth={2.3} />
            </span>
            <span>
              evalboard<span className="brand-dot">.</span>
            </span>
          </a>
          <span className="admin-pill">
            <Shield size={12} /> Admin Console
          </span>
        </div>
        <nav className="topnav">
          <a className="active" href="/admin">
            Evaluation Cards ({counts.total})
          </a>
          <a href="/">Live Scoreboard</a>
        </nav>
        <div className="top-actions">
          <ThemeToggle />
          <div className="admin-user-tag">
            <ShieldCheck size={13} />
            <span>{adminEmail}</span>
          </div>
          <button className="button button-outline button-small" onClick={() => void loadData()} disabled={loading}>
            <RefreshCw size={13} className={loading ? "spin-icon" : ""} /> Refresh
          </button>
          <button
            className="button button-outline button-small"
            onClick={handleAdminLogout}
            title="Log out administrator"
          >
            <LogOut size={13} /> Log out
          </button>
          <a className="button button-dark button-small" href="/">
            <ArrowLeft size={14} /> Back to Board
          </a>
        </div>
      </header>

      {notice && (
        <div className="admin-banner-notice">
          <Check size={14} /> {notice}
        </div>
      )}

      {error && (
        <div
          className="admin-banner-notice"
          style={{
            background: "rgba(217, 83, 79, 0.15)",
            borderColor: "rgba(217, 83, 79, 0.3)",
            color: "#d9534f",
          }}
        >
          <XCircle size={14} /> {error}
        </div>
      )}

      <section className="admin-hero">
        <div>
          <div className="eyebrow muted">
            <ShieldCheck size={12} /> CONTENT MODERATION &amp; GOVERNANCE
          </div>
          <h1>
            Evaluation Cards <span>Management</span>
          </h1>
          <p>
            Review user-submitted evaluations before they go live on the public scoreboard. Approve valid benchmarks
            or manage existing ones.
          </p>
        </div>
      </section>

      <section className="stats admin-stats" aria-label="Admin overview">
        <div className="stat-item cursor-pointer" onClick={() => setActiveTab("all")}>
          <div className="stat-icon blue">
            <Database size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : counts.total}</div>
            <div className="stat-label">Total cards in system</div>
          </div>
          <span className="stat-note">all states</span>
        </div>
        <div className="stat-item cursor-pointer" onClick={() => setActiveTab("pending")}>
          <div className="stat-icon amber">
            <Clock size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : counts.pending}</div>
            <div className="stat-label">Pending approval</div>
          </div>
          <span className="stat-note">{counts.pending > 0 ? "needs review" : "up to date"}</span>
        </div>
        <div className="stat-item cursor-pointer" onClick={() => setActiveTab("approved")}>
          <div className="stat-icon green">
            <ShieldCheck size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : counts.approved}</div>
            <div className="stat-label">Approved &amp; live</div>
          </div>
          <span className="stat-note">shown on public board</span>
        </div>
        <div className="stat-item cursor-pointer" onClick={() => setActiveTab("rejected")}>
          <div className="stat-icon violet">
            <ShieldAlert size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : counts.rejected}</div>
            <div className="stat-label">Rejected</div>
          </div>
          <span className="stat-note">hidden from public</span>
        </div>
      </section>

      <section className="evaluations-section">
        <div className="toolbar admin-toolbar">
          <div className="tabs" role="tablist">
            <button className={`tab ${activeTab === "all" ? "selected" : ""}`} onClick={() => setActiveTab("all")}>
              All cards <span className="tab-pill">{counts.total}</span>
            </button>
            <button
              className={`tab ${activeTab === "pending" ? "selected" : ""}`}
              onClick={() => setActiveTab("pending")}
            >
              Pending Review{" "}
              <span className={`tab-pill ${counts.pending > 0 ? "pill-alert" : ""}`}>{counts.pending}</span>
            </button>
            <button
              className={`tab ${activeTab === "approved" ? "selected" : ""}`}
              onClick={() => setActiveTab("approved")}
            >
              Approved <span className="tab-pill">{counts.approved}</span>
            </button>
            <button
              className={`tab ${activeTab === "rejected" ? "selected" : ""}`}
              onClick={() => setActiveTab("rejected")}
            >
              Rejected <span className="tab-pill">{counts.rejected}</span>
            </button>
          </div>
          <label className="searchbox">
            <Search size={16} />
            <input
              placeholder="Search model, benchmark, submitter..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>MODEL &amp; ORGANIZATION</th>
                <th>BENCHMARK</th>
                <th>AREA</th>
                <th>SCORE</th>
                <th>SUBMITTER</th>
                <th>STATUS</th>
                <th style={{ textAlign: "right", paddingRight: 18 }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="empty-row">
                    <span className="spinner" /> Loading evaluation cards…
                  </td>
                </tr>
              ) : visibleEvaluations.length ? (
                visibleEvaluations.map((item) => {
                  const status = item.status || "approved";
                  const isBusy = actionLoading === item._id;
                  return (
                    <tr className="evaluation-row" key={item._id}>
                      <td onClick={() => setSelected(item)}>
                        <div className="model-cell">
                          <span className={`model-logo logo-${item.organization.length % 4}`}>
                            {item.organization.slice(0, 1).toUpperCase()}
                          </span>
                          <span>
                            <strong>{item.model}</strong>
                            <small>{item.organization}</small>
                          </span>
                        </div>
                      </td>
                      <td onClick={() => setSelected(item)}>
                        <span className="benchmark-name">{item.benchmark}</span>
                        <small className="subtle-cell">{item.metric}</small>
                      </td>
                      <td onClick={() => setSelected(item)}>
                        <span className={`category-pill category-${item.category.toLowerCase()}`}>{item.category}</span>
                      </td>
                      <td onClick={() => setSelected(item)}>
                        <span className="score-number">
                          {item.score.toFixed(1)}
                          <small>%</small>
                        </span>
                      </td>
                      <td onClick={() => setSelected(item)}>
                        <div className="admin-submitter-cell">
                          <strong>{item.submittedBy || "Admin"}</strong>
                          <small>{item.submittedByEmail || "Internal"}</small>
                        </div>
                      </td>
                      <td>
                        {status === "pending" && (
                          <span className="status-badge status-pending">
                            <Clock size={11} /> Pending
                          </span>
                        )}
                        {status === "approved" && (
                          <span className="status-badge status-approved">
                            <Check size={11} /> Approved
                          </span>
                        )}
                        {status === "rejected" && (
                          <span className="status-badge status-rejected">
                            <XCircle size={11} /> Rejected
                          </span>
                        )}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div className="admin-row-actions">
                          {status !== "approved" && (
                            <button
                              className="admin-action-btn approve"
                              title="Approve evaluation (publish to live scoreboard)"
                              disabled={isBusy}
                              onClick={() => void updateStatus(item._id, "approved")}
                            >
                              <Check size={13} /> Approve
                            </button>
                          )}
                          {status !== "rejected" && (
                            <button
                              className="admin-action-btn reject"
                              title="Reject evaluation"
                              disabled={isBusy}
                              onClick={() => void updateStatus(item._id, "rejected")}
                            >
                              <X size={13} /> Reject
                            </button>
                          )}
                          {status === "approved" && (
                            <button
                              className="admin-action-btn neutral"
                              title="Revoke approval (mark as pending)"
                              disabled={isBusy}
                              onClick={() => void updateStatus(item._id, "pending")}
                            >
                              Revoke
                            </button>
                          )}
                          <button
                            className="admin-action-btn delete"
                            title="Delete permanently"
                            disabled={isBusy}
                            onClick={() => void deleteEvaluation(item._id, item.model)}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={7} className="empty-row">
                    <div className="empty-icon">
                      <Database size={20} />
                    </div>
                    <strong>No evaluations found</strong>
                    <p>{query ? "Try clearing your search query." : "No cards in this category."}</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="table-footer">
          <span>
            Showing <b>{visibleEvaluations.length}</b> of <b>{evaluations.length}</b> cards
          </span>
          <span className="updated-label">
            <span className="live-dot" /> Connected to MongoDB ({counts.total} total)
          </span>
        </div>
      </section>

      {/* Detail Modal */}
      {selected && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <section className="modal detail-modal" role="dialog" aria-modal="true">
            <div className="modal-head">
              <div>
                <div className="eyebrow muted">CARD AUDIT &amp; MODERATION</div>
                <h2>{selected.model}</h2>
                <p>
                  {selected.organization} · {selected.category}
                </p>
              </div>
              <button className="icon-button" onClick={() => setSelected(null)}>
                <X size={19} />
              </button>
            </div>

            <div className="detail-score">
              <div>
                <span className="eyebrow muted">BENCHMARK SCORE</span>
                <div className="detail-number">
                  {selected.score.toFixed(1)}
                  <small>%</small>
                </div>
              </div>
              <span className={`status-badge status-${selected.status || "approved"}`}>
                {selected.status === "pending" && (
                  <>
                    <Clock size={12} /> Pending
                  </>
                )}
                {(!selected.status || selected.status === "approved") && (
                  <>
                    <Check size={12} /> Approved &amp; Live
                  </>
                )}
                {selected.status === "rejected" && (
                  <>
                    <XCircle size={12} /> Rejected
                  </>
                )}
              </span>
            </div>

            <div className="detail-list">
              <div>
                <span>Benchmark</span>
                <b>{selected.benchmark}</b>
              </div>
              <div>
                <span>Metric</span>
                <b>{selected.metric}</b>
              </div>
              <div>
                <span>Submitted By</span>
                <b>
                  {selected.submittedBy || "Admin"} ({selected.submittedByEmail || "Internal"})
                </b>
              </div>
              <div>
                <span>Submitted Date</span>
                <b>
                  {new Date(selected.evaluatedAt).toLocaleDateString(undefined, {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </b>
              </div>
              {selected.reviewedAt && (
                <div>
                  <span>Reviewed Date</span>
                  <b>{new Date(selected.reviewedAt).toLocaleDateString()}</b>
                </div>
              )}
              {selected.source && (
                <div>
                  <span>Source URL</span>
                  <a href={selected.source} target="_blank" rel="noreferrer">
                    Open link <ArrowUpRight size={13} />
                  </a>
                </div>
              )}
            </div>

            <div className="admin-modal-actions">
              {selected.status !== "approved" && (
                <button className="button button-dark" onClick={() => void updateStatus(selected._id, "approved")}>
                  <Check size={15} /> Approve &amp; Publish
                </button>
              )}
              {selected.status !== "rejected" && (
                <button
                  className="button button-outline"
                  style={{ color: "#d9534f" }}
                  onClick={() => void updateStatus(selected._id, "rejected")}
                >
                  <X size={15} /> Reject
                </button>
              )}
              <button
                className="button button-outline"
                onClick={() => void deleteEvaluation(selected._id, selected.model)}
              >
                <Trash2 size={15} /> Delete Card
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
