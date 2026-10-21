"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  Check,
  ChevronDown,
  CircleHelp,
  Clock,
  Database,
  FilePlus2,
  Layers3,
  LogIn,
  LogOut,
  Plus,
  Search,
  Send,
  Shield,
  ShieldCheck,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import ThemeToggle from "@/lib/ThemeToggle";

type Evaluation = {
  _id: string;
  model: string;
  organization: string;
  benchmark: string;
  score: number;
  metric: string;
  category: string;
  source?: string;
  evaluatedAt: string;
  status?: "pending" | "approved" | "rejected";
  submittedBy?: string;
  submittedByEmail?: string;
};

type UserSession = { id: string; email: string };
const baseCategories = ["All evaluations", "Reasoning", "Coding", "Knowledge", "Safety"];

type Recommendation = {
  model: string;
  organization: string;
  average: number;
  demo: boolean;
  evidence: Array<{ benchmark: string; metric: string; score: number; category: string }>;
};

export default function Home() {
  const [user, setUser] = useState<UserSession | null>(null);
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [userEvaluations, setUserEvaluations] = useState<Evaluation[]>([]);
  const [submissionNotice, setSubmissionNotice] = useState<string | null>(null);
  const [category, setCategory] = useState("All evaluations");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [selected, setSelected] = useState<Evaluation | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [showFinder, setShowFinder] = useState(false);
  const [workDescription, setWorkDescription] = useState("");
  const [finding, setFinding] = useState(false);
  const [recommendation, setRecommendation] = useState<{
    recommendation: Recommendation;
    reason: string;
    candidates: Recommendation[];
  } | null>(null);
  const [finderError, setFinderError] = useState("");

  async function loadEvaluations() {
    setLoading(true);
    try {
      const response = await fetch("/api/evaluations", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Unable to load evaluation cards.");
      setEvaluations(data.evaluations || []);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load evaluation cards.");
    } finally {
      setLoading(false);
    }
  }

  async function loadUserEvaluations(email: string) {
    try {
      const response = await fetch(`/api/evaluations?user=${encodeURIComponent(email)}`, { cache: "no-store" });
      const data = await response.json();
      if (response.ok) setUserEvaluations(data.evaluations || []);
    } catch {
      /* Ignore */
    }
  }

  useEffect(() => {
    void loadEvaluations();
    try {
      const stored = localStorage.getItem("evalboard_user");
      if (stored) {
        const u = JSON.parse(stored);
        setUser(u);
        if (u?.email) void loadUserEvaluations(u.email);
      }
    } catch {
      /* Ignore storage parse error */
    }
  }, []);

  useEffect(() => {
    if (!showProfileMenu) return;

    function handleClickOutside(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      if (target && !target.closest(".profile-menu-container")) {
        setShowProfileMenu(false);
      }
    }

    window.addEventListener("click", handleClickOutside);
    return () => window.removeEventListener("click", handleClickOutside);
  }, [showProfileMenu]);

  function handleLogout() {
    try {
      localStorage.removeItem("evalboard_user");
      document.cookie = "evalboard_user=; Max-Age=0; path=/";
      void fetch("/api/auth", { method: "DELETE" }).catch(() => {});
    } catch {
      /* Ignore */
    }
    setUser(null);
    setUserEvaluations([]);
    if (category === "My Submissions") setCategory("All evaluations");
    setShowProfileMenu(false);
  }

  const isMySubmissions = category === "My Submissions";
  const activeList = isMySubmissions ? userEvaluations : evaluations;

  const visibleEvaluations = useMemo(() => {
    return activeList.filter((item) => {
      const matchesCategory = isMySubmissions || category === "All evaluations" || item.category === category;
      const needle = query.toLowerCase().trim();
      return (
        matchesCategory &&
        (!needle ||
          [item.model, item.organization, item.benchmark, item.category].some((value) =>
            value.toLowerCase().includes(needle)
          ))
      );
    });
  }, [activeList, isMySubmissions, category, query]);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {
      "All evaluations": evaluations.length,
      Reasoning: 0,
      Coding: 0,
      Knowledge: 0,
      Safety: 0,
      "My Submissions": userEvaluations.length,
    };
    evaluations.forEach((item) => {
      if (counts[item.category] !== undefined) {
        counts[item.category] += 1;
      }
    });
    return counts;
  }, [evaluations, userEvaluations]);

  const avg = evaluations.length
    ? (evaluations.reduce((sum, item) => sum + item.score, 0) / evaluations.length).toFixed(1)
    : "—";
  const organizations = new Set(evaluations.map((item) => item.organization)).size;

  async function createEvaluation(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const form = new FormData(event.currentTarget);
    const payload = {
      model: String(form.get("model") || ""),
      organization: String(form.get("organization") || ""),
      benchmark: String(form.get("benchmark") || ""),
      score: Number(form.get("score")),
      metric: String(form.get("metric") || ""),
      category: String(form.get("category") || ""),
      source: String(form.get("source") || ""),
      submittedBy: user ? user.email.split("@")[0] : "community",
      submittedByEmail: user ? user.email : "",
    };
    try {
      const response = await fetch("/api/evaluations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not save this evaluation.");
      setUserEvaluations((items) => [data.evaluation, ...items]);
      setShowForm(false);
      setSubmissionNotice(
        "Your evaluation has been submitted for review! It is pending admin approval and visible in 'My Submissions'."
      );
      setTimeout(() => setSubmissionNotice(null), 9000);
      if (user) setCategory("My Submissions");
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : "Could not save this evaluation.");
    } finally {
      setSaving(false);
    }
  }

  async function findModel(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFinding(true);
    setFinderError("");
    setRecommendation(null);
    try {
      const response = await fetch("/api/recommendations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work: workDescription }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not find a model recommendation.");
      setRecommendation(data);
    } catch (cause) {
      setFinderError(cause instanceof Error ? cause.message : "Could not find a model recommendation.");
    } finally {
      setFinding(false);
    }
  }

  const categoriesToDisplay = user ? [...baseCategories, "My Submissions"] : baseCategories;

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Evalboard home">
          <span className="brand-mark">
            <Layers3 size={19} strokeWidth={2.3} />
          </span>
          <span>
            evalboard<span className="brand-dot">.</span>
          </span>
        </a>
        <nav className="topnav">
          <a className="active" href="#evaluations">
            Evaluations
          </a>
          <a href="#about">About</a>
        </nav>
        <div className="top-actions">
          <ThemeToggle />
          {user ? (
            <div className="profile-menu-container">
              <button
                className="profile-button"
                onClick={() => setShowProfileMenu((prev) => !prev)}
                aria-label="User profile"
              >
                <span className="profile-avatar">{user.email.slice(0, 1).toUpperCase()}</span>
                <span className="profile-name">{user.email.split("@")[0]}</span>
                <ChevronDown size={12} className={`profile-chevron ${showProfileMenu ? "open" : ""}`} />
              </button>
              {showProfileMenu && (
                <div className="profile-dropdown">
                  <div className="profile-dropdown-header">
                    <span className="profile-dropdown-avatar">{user.email.slice(0, 1).toUpperCase()}</span>
                    <div>
                      <strong>{user.email.split("@")[0]}</strong>
                      <small>{user.email}</small>
                    </div>
                  </div>
                  <div className="profile-dropdown-divider" />
                  <div className="profile-dropdown-badge">
                    <Sparkles size={12} /> Evalboard Member
                  </div>
                  <div className="profile-dropdown-divider" />
                  <button
                    className="profile-dropdown-item"
                    onClick={() => {
                      setCategory("My Submissions");
                      setShowProfileMenu(false);
                    }}
                  >
                    <FilePlus2 size={13} /> My Submissions ({userEvaluations.length})
                  </button>
                  <a className="profile-dropdown-item" href="/admin">
                    <Shield size={13} /> Admin Console
                  </a>
                  <div className="profile-dropdown-divider" />
                  <button className="profile-dropdown-item logout" onClick={handleLogout}>
                    <LogOut size={13} /> Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <a className="button button-outline button-small" href="/login">
              <LogIn size={14} /> Sign in
            </a>
          )}
          <a className="button button-outline button-small" href="/admin" title="Admin moderation portal">
            <Shield size={13} /> Admin
          </a>
          <button className="button button-soft button-small finder-trigger" onClick={() => setShowFinder(true)}>
            <Sparkles size={14} /> Find my model
          </button>
          <button className="button button-dark button-small" onClick={() => setShowForm(true)}>
            <Plus size={15} /> Add evaluation
          </button>
        </div>
      </header>

      {submissionNotice && (
        <div className="admin-banner-notice" style={{ margin: "16px 0 -10px" }}>
          <Check size={14} /> {submissionNotice}
        </div>
      )}

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" /> MODEL EVALUATION, MADE CLEAR
          </div>
          <h1>
            Know what a model
            <br />
            can <span>actually do.</span>
          </h1>
          <p>
            A clear, considered view of AI evaluation results. Explore benchmark scores, understand the context, and
            see where every number comes from.
          </p>
          <a className="text-link" href="#evaluations">
            Explore evaluations <ArrowRight size={15} />
          </a>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-grid" />
          <div className="art-orbit orbit-one" />
          <div className="art-orbit orbit-two" />
          <div className="floating-card card-top">
            <div className="tiny-label">
              MODEL PERFORMANCE <span>↗</span>
            </div>
            <div className="mini-chart">
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
            <div className="chart-footer">
              <b>+12.8%</b>
              <span>across benchmarks</span>
            </div>
          </div>
          <div className="floating-card card-bottom">
            <div className="score-badge">
              <Sparkles size={14} />
            </div>
            <div>
              <div className="tiny-label">LATEST EVALUATION</div>
              <strong>Reasoning · MATH</strong>
              <span className="card-meta">
                Claude 3.7 Sonnet <b>·</b> 94.2%
              </span>
            </div>
            <ArrowUpRight className="card-arrow" size={17} />
          </div>
          <div className="art-orb">
            <Activity size={29} />
          </div>
          <div className="art-caption">
            Better context.
            <br />
            <b>Smarter decisions.</b>
          </div>
        </div>
      </section>

      <section className="stats" aria-label="Evaluation overview">
        <div className="stat-item">
          <div className="stat-icon violet">
            <BarChart3 size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : evaluations.length}</div>
            <div className="stat-label">Evaluations tracked</div>
          </div>
          <span className="stat-note">across all models</span>
        </div>
        <div className="stat-item">
          <div className="stat-icon green">
            <Sparkles size={17} />
          </div>
          <div>
            <div className="stat-value">
              {loading ? "…" : avg}
              {avg !== "—" && <small>%</small>}
            </div>
            <div className="stat-label">Average score</div>
          </div>
          <span className="stat-note">all benchmarks</span>
        </div>
        <div className="stat-item">
          <div className="stat-icon amber">
            <ShieldCheck size={17} />
          </div>
          <div>
            <div className="stat-value">{loading ? "…" : organizations}</div>
            <div className="stat-label">Reporting teams</div>
          </div>
          <span className="stat-note">sources represented</span>
        </div>
        <div className="stat-item">
          <div className="stat-icon blue">
            <Layers3 size={17} />
          </div>
          <div>
            <div className="stat-value">
              {loading ? "…" : new Set(evaluations.map((item) => item.category)).size}
            </div>
            <div className="stat-label">Benchmark areas</div>
          </div>
          <span className="stat-note">areas of capability</span>
        </div>
      </section>

      <section className="evaluations-section" id="evaluations">
        <div className="section-heading">
          <div>
            <div className="eyebrow muted">{isMySubmissions ? "YOUR CONTRIBUTIONS" : "THE SCOREBOARD"}</div>
            <h2>
              {isMySubmissions ? "My submitted evaluations" : "Evaluation cards"}
              <span className="heading-count">{visibleEvaluations.length}</span>
            </h2>
            <p>
              {isMySubmissions
                ? "Track the approval status of benchmarks you submitted."
                : "Each result, with the context that makes it meaningful."}
            </p>
          </div>
          <button className="button button-outline" onClick={() => setShowForm(true)}>
            <FilePlus2 size={16} /> Submit a result
          </button>
        </div>
        <div className="toolbar">
          <div className="tabs" role="tablist" aria-label="Filter by category">
            {categoriesToDisplay.map((item) => {
              const count = categoryCounts[item] ?? 0;
              const hasAlert = item === "My Submissions" && userEvaluations.some((e) => e.status === "pending");
              return (
                <button
                  key={item}
                  className={`tab ${category === item ? "selected" : ""}`}
                  onClick={() => setCategory(item)}
                  role="tab"
                  aria-selected={category === item}
                >
                  {item}
                  <span className={`tab-pill ${hasAlert ? "pill-alert" : ""}`}>{count}</span>
                </button>
              );
            })}
          </div>
          <label className="searchbox">
            <Search size={16} />
            <input
              placeholder="Search models, benchmarks..."
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <kbd>⌘ K</kbd>
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
                <th>{isMySubmissions ? "STATUS" : "REPORTED"}</th>
                <th>
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="empty-row">
                    <span className="spinner" /> Loading evaluations…
                  </td>
                </tr>
              ) : visibleEvaluations.length ? (
                visibleEvaluations.map((item) => (
                  <tr className="evaluation-row" key={item._id} onClick={() => setSelected(item)}>
                    <td>
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
                    <td>
                      <span className="benchmark-name">{item.benchmark}</span>
                      <small className="subtle-cell">{item.metric}</small>
                    </td>
                    <td>
                      <span className={`category-pill category-${item.category.toLowerCase()}`}>{item.category}</span>
                    </td>
                    <td>
                      <span className="score-number">
                        {item.score.toFixed(1)}
                        <small>%</small>
                      </span>
                      <div className="score-track">
                        <span style={{ width: `${item.score}%` }} />
                      </div>
                    </td>
                    <td>
                      {isMySubmissions ? (
                        item.status === "pending" ? (
                          <span className="status-badge status-pending">
                            <Clock size={11} /> Pending Review
                          </span>
                        ) : item.status === "rejected" ? (
                          <span className="status-badge status-rejected">
                            <XCircle size={11} /> Rejected
                          </span>
                        ) : (
                          <span className="status-badge status-approved">
                            <Check size={11} /> Approved &amp; Live
                          </span>
                        )
                      ) : (
                        <span className="date-cell">
                          {new Date(item.evaluatedAt).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                      )}
                    </td>
                    <td>
                      <ArrowUpRight className="row-arrow" size={16} />
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="empty-row">
                    <div className="empty-icon">
                      <Database size={20} />
                    </div>
                    <strong>
                      {error
                        ? "Database connection needed"
                        : isMySubmissions
                        ? "No submitted evaluations yet"
                        : query || category !== "All evaluations"
                        ? "No matching evaluations"
                        : "Your evaluation board is ready"}
                    </strong>
                    <p>
                      {error ||
                        (isMySubmissions
                          ? "Submit an evaluation card using the button below. It will be reviewed by an admin before going live."
                          : query || category !== "All evaluations"
                          ? "Try another search or category."
                          : "Connect MongoDB and add your first result to get started.")}
                    </p>
                    {error ? (
                      <button className="button button-outline" onClick={() => void loadEvaluations()}>
                        Retry connection
                      </button>
                    ) : (
                      (isMySubmissions || (!query && category === "All evaluations")) && (
                        <button className="button button-dark button-small" onClick={() => setShowForm(true)}>
                          <Plus size={15} /> Add evaluation
                        </button>
                      )
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <footer id="about">
        <a className="brand footer-brand" href="#top">
          <span className="brand-mark">
            <Layers3 size={16} />
          </span>
          evalboard<span className="brand-dot">.</span>
        </a>
        <span>Thoughtful evaluation for a clearer picture of AI.</span>
        <a href="#top">Back to top ↑</a>
      </footer>

      {showForm && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowForm(false);
          }}
        >
          <section className="modal" role="dialog" aria-modal="true" aria-labelledby="form-title">
            <div className="modal-head">
              <div>
                <div className="eyebrow muted">CONTRIBUTE A RESULT</div>
                <h2 id="form-title">Add an evaluation</h2>
                <p>Share a model result with its benchmark context. User submissions are reviewed by an admin.</p>
              </div>
              <button className="icon-button" aria-label="Close" onClick={() => setShowForm(false)}>
                <X size={19} />
              </button>
            </div>
            <form onSubmit={createEvaluation}>
              <div className="form-grid">
                <label>
                  Model name
                  <input name="model" placeholder="e.g. Claude 3.7 Sonnet" required maxLength={100} />
                </label>
                <label>
                  Organization
                  <input name="organization" placeholder="e.g. Anthropic" required maxLength={100} />
                </label>
                <label>
                  Benchmark
                  <input name="benchmark" placeholder="e.g. MATH-500" required maxLength={120} />
                </label>
                <label>
                  Score (%)
                  <input name="score" type="number" min="0" max="100" step="0.1" placeholder="e.g. 94.2" required />
                </label>
                <label>
                  Metric
                  <input name="metric" placeholder="e.g. pass@1" required maxLength={60} />
                </label>
                <label>
                  Area
                  <select name="category" defaultValue="Reasoning">
                    <option>Reasoning</option>
                    <option>Coding</option>
                    <option>Knowledge</option>
                    <option>Safety</option>
                  </select>
                  <ChevronDown className="select-chevron" size={14} />
                </label>
                <label className="full-field">
                  Source URL <span className="optional">Optional</span>
                  <input name="source" type="url" placeholder="https://..." maxLength={300} />
                </label>
              </div>
              {formError && <p className="form-error">{formError}</p>}
              <div className="form-actions">
                <span>
                  <CircleHelp size={14} /> {user ? `Submitting as ${user.email}` : "Scores undergo admin review."}
                </span>
                <button className="button button-dark" disabled={saving}>
                  {saving ? (
                    "Submitting…"
                  ) : (
                    <>
                      <Plus size={15} /> Submit for review
                    </>
                  )}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {showFinder && (
        <div
          className="modal-backdrop finder-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowFinder(false);
          }}
        >
          <section className="modal finder-modal" role="dialog" aria-modal="true" aria-labelledby="finder-title">
            <div className="modal-head">
              <div>
                <div className="eyebrow">
                  <Sparkles size={12} /> MODEL ADVISOR
                </div>
                <h2 id="finder-title">Find the right model for your work</h2>
                <p>Tell us what you want to get done. We’ll match it to evaluation evidence.</p>
              </div>
              <button className="icon-button" aria-label="Close" onClick={() => setShowFinder(false)}>
                <X size={19} />
              </button>
            </div>
            <form onSubmit={findModel}>
              <label className="finder-label" htmlFor="work-description">
                What are you working on?
              </label>
              <textarea
                id="work-description"
                className="finder-input"
                value={workDescription}
                onChange={(event) => setWorkDescription(event.target.value)}
                placeholder="For example: I need help building a React app, writing tests, and reviewing code changes."
                minLength={12}
                maxLength={1200}
                required
              />
              <div className="finder-meta">
                <span>{workDescription.length}/1,200 characters</span>
                <span>Be specific for a more useful match</span>
              </div>
              <button
                className="button button-dark finder-submit"
                disabled={finding || workDescription.trim().length < 12}
              >
                {finding ? (
                  <>
                    <span className="spinner light-spinner" /> Finding a match…
                  </>
                ) : (
                  <>
                    <Send size={14} /> Find my model
                  </>
                )}
              </button>
            </form>
            {finderError && <p className="form-error finder-error">{finderError}</p>}
            {recommendation && (
              <div className="recommendation-result">
                <div className="result-kicker">
                  <span>
                    <Sparkles size={13} />
                    RECOMMENDED MODEL
                  </span>
                </div>
                <div className="best-match">
                  <div className="match-icon">
                    <Bot size={19} />
                  </div>
                  <div>
                    <span className="eyebrow muted">BEST AVAILABLE MATCH</span>
                    <h3>{recommendation.recommendation.model.replace(/^Demo\s*[·-]\s*/i, "")}</h3>
                    <p>{recommendation.recommendation.organization}</p>
                  </div>
                  <span className="match-score">
                    {recommendation.recommendation.average.toFixed(1)}
                    <small>% avg.</small>
                  </span>
                </div>
                <p className="match-reason">{recommendation.reason.replace(/^Demo\s*[·-]\s*/i, "")}</p>
                <div className="evidence-list">
                  <span className="evidence-heading">SUPPORTING BENCHMARKS</span>
                  {recommendation.recommendation.evidence.map((item) => (
                    <div className="evidence-item" key={`${item.category}-${item.benchmark}`}>
                      <span>
                        <b>{item.benchmark}</b>
                        <small>
                          {item.category} · {item.metric}
                        </small>
                      </span>
                      <strong>{item.score.toFixed(1)}%</strong>
                    </div>
                  ))}
                </div>
                {recommendation.candidates.length > 1 && (
                  <details className="other-matches">
                    <summary>See other matching models</summary>
                    <div>
                      {recommendation.candidates.slice(1).map((item) => (
                        <span key={item.model}>
                          {item.model.replace(/^Demo\s*[·-]\s*/i, "")}
                          <b>{item.average.toFixed(1)}%</b>
                        </span>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </section>
        </div>
      )}

      {selected && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelected(null);
          }}
        >
          <section className="modal detail-modal" role="dialog" aria-modal="true">
            <div className="modal-head">
              <div>
                <div className="eyebrow muted">EVALUATION DETAIL</div>
                <h2>{selected.model}</h2>
                <p>
                  {selected.organization} · {selected.category}
                </p>
              </div>
              <button className="icon-button" aria-label="Close" onClick={() => setSelected(null)}>
                <X size={19} />
              </button>
            </div>
            <div className="detail-score">
              <div>
                <span className="eyebrow muted">REPORTED SCORE</span>
                <div className="detail-number">
                  {selected.score.toFixed(1)}
                  <small>%</small>
                </div>
              </div>
              <span className="category-pill category-reasoning">{selected.metric}</span>
            </div>
            <div className="detail-list">
              <div>
                <span>Benchmark</span>
                <b>{selected.benchmark}</b>
              </div>
              <div>
                <span>Area</span>
                <b>{selected.category}</b>
              </div>
              <div>
                <span>Status</span>
                <b style={{ textTransform: "capitalize" }}>{selected.status || "Approved"}</b>
              </div>
              {selected.submittedBy && (
                <div>
                  <span>Submitted By</span>
                  <b>{selected.submittedBy}</b>
                </div>
              )}
              <div>
                <span>Reported</span>
                <b>
                  {new Date(selected.evaluatedAt).toLocaleDateString(undefined, {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })}
                </b>
              </div>
              {selected.source && (
                <div>
                  <span>Source</span>
                  <a href={selected.source} target="_blank" rel="noreferrer">
                    View report <ArrowUpRight size={14} />
                  </a>
                </div>
              )}
            </div>
            <div className="detail-note">
              {selected.status === "pending" ? (
                <>
                  <Clock size={15} /> Pending review. This card will appear publicly once approved by an admin.
                </>
              ) : selected.status === "rejected" ? (
                <>
                  <XCircle size={15} /> This evaluation was rejected and is not visible publicly.
                </>
              ) : (
                <>
                  <Check size={15} /> Score verified and published to this evaluation board.
                </>
              )}
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
