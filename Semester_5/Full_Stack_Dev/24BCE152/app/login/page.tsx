"use client";

import { useEffect, useState } from "react";
import { Layers3, Mail, Lock, Eye, EyeOff, ArrowRight, ArrowLeft, Sparkles, CheckCircle2 } from "lucide-react";
import ThemeToggle from "@/lib/ThemeToggle";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [mode, setMode] = useState<"login" | "signup">("login");

  useEffect(() => {
    try {
      const stored = localStorage.getItem("evalboard_user");
      if (stored) {
        const u = JSON.parse(stored);
        if (u?.email) {
          window.location.href = "/";
        }
      }
    } catch {
      // Ignore
    }
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      const response = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, mode }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Authentication failed.");
      if (data.user) {
        localStorage.setItem("evalboard_user", JSON.stringify(data.user));
      }
      setSuccessMsg(mode === "signup" ? "Account ready! Redirecting…" : "Signed in! Redirecting…");
      setTimeout(() => {
        window.location.href = "/";
      }, 600);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function handleQuickDemo() {
    setEmail("jeelpadsala15@gmail.com");
    setPassword("admin123");
  }

  return (
    <div className="login-page">
      <div className="login-left">
        <div className="login-left-content">
          <div className="login-art-grid" />
          <div className="login-art-orbit orbit-a" />
          <div className="login-art-orbit orbit-b" />
          <div className="login-art-orb">
            <Sparkles size={28} />
          </div>
          <div className="login-tagline">
            <h2>
              Know what a model<br />can <span>actually do.</span>
            </h2>
            <p>
              A clear, considered view of AI evaluation results. Explore benchmark scores, understand the context, and see where every number comes from.
            </p>
          </div>
          <div className="login-stats-row">
            <div className="login-stat">
              <strong>24+</strong>
              <span>Evaluations</span>
            </div>
            <div className="login-stat">
              <strong>15+</strong>
              <span>Models</span>
            </div>
            <div className="login-stat">
              <strong>4</strong>
              <span>Categories</span>
            </div>
          </div>
        </div>
      </div>

      <div className="login-right">
        <div className="login-form-container">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "18px" }}>
            <a className="brand login-brand" href="/" style={{ margin: 0 }}>
              <span className="brand-mark">
                <Layers3 size={19} strokeWidth={2.3} />
              </span>
              <span>
                evalboard<span className="brand-dot">.</span>
              </span>
            </a>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <ThemeToggle />
              <a
                href="/"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "5px",
                  fontSize: "12px",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                  fontWeight: 600,
                }}
              >
                <ArrowLeft size={13} /> Back to board
              </a>
            </div>
          </div>

          <div className="login-header">
            <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
            <p>
              {mode === "login"
                ? "Sign in to submit and track your model evaluation cards."
                : "Join Evalboard to submit benchmark results and track reviews."}
            </p>
          </div>

          <div className="login-tabs">
            <button
              className={`login-tab ${mode === "login" ? "active" : ""}`}
              onClick={() => {
                setMode("login");
                setError("");
                setSuccessMsg("");
              }}
            >
              Sign in
            </button>
            <button
              className={`login-tab ${mode === "signup" ? "active" : ""}`}
              onClick={() => {
                setMode("signup");
                setError("");
                setSuccessMsg("");
              }}
            >
              Create account
            </button>
          </div>

          <form onSubmit={handleSubmit} className="login-form">
            <label className="login-field">
              <span className="login-label">Email address</span>
              <div className="login-input-wrap">
                <Mail size={15} className="login-input-icon" />
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              </div>
            </label>

            <label className="login-field">
              <span className="login-label">Password</span>
              <div className="login-input-wrap">
                <Lock size={15} className="login-input-icon" />
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
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

            <div className="login-extras" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label className="login-remember">
                <input type="checkbox" defaultChecked />
                <span>Keep me signed in</span>
              </label>
              <button
                type="button"
                onClick={handleQuickDemo}
                style={{
                  background: "none",
                  border: 0,
                  color: "var(--green)",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                Use sample credentials
              </button>
            </div>

            {error && <p className="login-error">{error}</p>}
            {successMsg && (
              <p
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  color: "var(--green)",
                  background: "var(--accent)",
                  border: "1px solid var(--green)",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  margin: "10px 0 0",
                }}
              >
                <CheckCircle2 size={14} /> {successMsg}
              </p>
            )}

            <button className="button button-dark login-submit" type="submit" disabled={loading}>
              {loading ? (
                <>
                  <span className="spinner light-spinner" /> {mode === "login" ? "Signing in…" : "Creating account…"}
                </>
              ) : (
                <>
                  {mode === "login" ? "Sign in to Evalboard" : "Create account & enter"} <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>

          <p className="login-footer-text" style={{ marginTop: "24px" }}>
            {mode === "login" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  className="login-switch"
                  onClick={() => {
                    setMode("signup");
                    setError("");
                  }}
                >
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  type="button"
                  className="login-switch"
                  onClick={() => {
                    setMode("login");
                    setError("");
                  }}
                >
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
