import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { getGithubLoginUrl } from "../api/client";
import { useSession } from "../hooks/useSession";

export const getStyles = (theme) => {
  const dark = theme === "dark";
  return `
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Syne:wght@400;500;600;700;800&display=swap');

    .auth-root {
      min-height: 100vh;
      background: ${dark ? "#0a0a0a" : "#f4f1eb"};
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Syne', sans-serif;
      position: relative;
      overflow: hidden;
      padding-top: 56px;
    }

    .auth-grid {
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(${dark ? "rgba(234,179,8,0.04)" : "rgba(120,80,0,0.06)"} 1px, transparent 1px),
        linear-gradient(90deg, ${dark ? "rgba(234,179,8,0.04)" : "rgba(120,80,0,0.06)"} 1px, transparent 1px);
      background-size: 48px 48px;
      pointer-events: none;
    }

    .auth-glow {
      position: absolute;
      width: 600px;
      height: 600px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(234,179,8,0.07) 0%, transparent 70%);
      top: -200px;
      right: -200px;
      pointer-events: none;
    }

    .auth-glow-2 {
      position: absolute;
      width: 400px;
      height: 400px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(234,179,8,0.05) 0%, transparent 70%);
      bottom: -150px;
      left: -100px;
      pointer-events: none;
    }

    .auth-navbar {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      background: ${dark ? "rgba(10,10,10,0.85)" : "rgba(244,241,235,0.9)"};
      backdrop-filter: blur(12px);
      border-bottom: 1px solid ${dark ? "#1a1a1a" : "#e5e0d5"};
      z-index: 100;
    }

    .nav-logo {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .nav-logo-icon {
      width: 28px;
      height: 28px;
      background: #eab308;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      font-size: 11px;
      color: #0a0a0a;
    }

    .nav-logo-name {
      font-size: 15px;
      font-weight: 700;
      color: ${dark ? "#ffffff" : "#0a0a0a"};
      letter-spacing: -0.2px;
    }

    .theme-toggle {
      width: 34px;
      height: 34px;
      background: ${dark ? "#1a1a1a" : "#ece7dc"};
      border: 1px solid ${dark ? "#2a2a2a" : "#ddd8cc"};
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 15px;
      transition: background 0.2s;
      color: ${dark ? "#888888" : "#666"};
    }

    .theme-toggle:hover {
      background: ${dark ? "#222222" : "#e2ddd2"};
    }

    .auth-card {
      position: relative;
      width: 420px;
      max-width: calc(100vw - 48px);
      background: ${dark ? "#111111" : "#ffffff"};
      border: 1px solid ${dark ? "#1e1e1e" : "#e8e3d8"};
      border-radius: 16px;
      padding: 40px 36px;
      opacity: 0;
      transform: translateY(20px);
      transition: opacity 0.45s ease, transform 0.45s ease;
      ${!dark ? "box-shadow: 0 4px 24px rgba(0,0,0,0.06);" : ""}
    }

    .auth-card.visible {
      opacity: 1;
      transform: translateY(0);
    }

    .auth-logo {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 24px;
    }

    .auth-logo-icon {
      width: 34px;
      height: 34px;
      background: #eab308;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      font-size: 12px;
      color: #0a0a0a;
    }

    .auth-logo-name {
      font-size: 17px;
      font-weight: 700;
      color: ${dark ? "#ffffff" : "#0a0a0a"};
      letter-spacing: -0.3px;
    }

    .rag-badge {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      background: ${dark ? "#181818" : "#f4efe4"};
      border: 1px solid ${dark ? "#282828" : "#e8e3d8"};
      border-radius: 20px;
      padding: 5px 12px;
      font-size: 11px;
      color: ${dark ? "#777777" : "#888888"};
      font-family: 'JetBrains Mono', monospace;
      margin-bottom: 20px;
      letter-spacing: 0.2px;
    }

    .rag-badge-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #eab308;
      flex-shrink: 0;
    }

    .auth-heading {
      font-size: 24px;
      font-weight: 800;
      color: ${dark ? "#ffffff" : "#0a0a0a"};
      line-height: 1.25;
      margin: 0 0 10px;
      letter-spacing: -0.5px;
    }

    .auth-heading .accent {
      color: #eab308;
    }

    .auth-sub {
      font-size: 13px;
      color: ${dark ? "#555555" : "#888888"};
      margin: 0 0 28px;
      line-height: 1.6;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 400;
    }

    .auth-features {
      display: flex;
      flex-direction: column;
      gap: 9px;
      margin-bottom: 28px;
    }

    .auth-feature-item {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
      color: ${dark ? "#777777" : "#666666"};
      font-family: 'JetBrains Mono', monospace;
    }

    .auth-feature-dot {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #eab308;
      flex-shrink: 0;
    }

    .github-btn {
      width: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 11px;
      padding: 13px 24px;
      background: #eab308;
      color: #0a0a0a;
      border: none;
      border-radius: 10px;
      font-family: 'Syne', sans-serif;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.2s, transform 0.15s, box-shadow 0.2s;
      letter-spacing: -0.2px;
    }

    .github-btn:hover {
      background: #f0c020;
      transform: translateY(-1px);
      box-shadow: 0 8px 24px rgba(234,179,8,0.28);
    }

    .github-btn:active {
      transform: translateY(0);
      box-shadow: none;
    }

    .auth-legal {
      text-align: center;
      font-size: 11px;
      color: ${dark ? "#3d3d3d" : "#aaaaaa"};
      font-family: 'JetBrains Mono', monospace;
      line-height: 1.6;
      margin-top: 18px;
      margin-bottom: 0;
    }

    .auth-legal a {
      color: #eab308;
      text-decoration: none;
    }

    .auth-legal a:hover {
      text-decoration: underline;
    }

    .auth-switch {
      text-align: center;
      margin-top: 16px;
      font-size: 12px;
      color: ${dark ? "#444444" : "#aaaaaa"};
      font-family: 'JetBrains Mono', monospace;
      margin-bottom: 0;
    }

    .auth-switch a {
      color: #eab308;
      text-decoration: none;
      font-weight: 600;
    }

    .auth-switch a:hover {
      text-decoration: underline;
    }

    .auth-form {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 14px;
    }

    .auth-input {
      width: 100%;
      border: 1px solid ${dark ? '#2a2a2a' : '#ddd8cc'};
      background: ${dark ? '#0f0f0f' : '#fcfbf8'};
      color: ${dark ? '#f3f4f6' : '#1f2937'};
      border-radius: 10px;
      padding: 11px 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      outline: none;
    }

    .auth-input:focus {
      border-color: #eab308;
      box-shadow: 0 0 0 3px rgba(234,179,8,0.18);
    }

    .auth-error {
      margin: 0 0 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: #ef4444;
      background: rgba(239, 68, 68, 0.08);
      border: 1px solid rgba(239, 68, 68, 0.28);
      border-radius: 8px;
      padding: 8px 10px;
    }
  `;
};

export default function Login() {
  const { loading, isAdmin, isUser } = useSession();
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState(() =>
    localStorage.getItem("prguard-theme") || "dark"
  );

  useEffect(() => {
    setMounted(true);
  }, []);

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0d0f12', color: '#6b7280' }}>
        Loading...
      </div>
    )
  }

  if (isAdmin) {
    return <Navigate to="/admin/dashboard" replace />
  }

  if (isUser) {
    return <Navigate to="/dashboard" replace />
  }

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("prguard-theme", next);
  };

  const handleGitHubLogin = () => {
    window.location.href = getGithubLoginUrl();
  };

  return (
    <>
      <style>{getStyles(theme)}</style>
      <div className="auth-root">
        <div className="auth-grid" />
        <div className="auth-glow" />
        <div className="auth-glow-2" />

        <nav className="auth-navbar">
          <div className="nav-logo">
            <div className="nav-logo-icon">PG</div>
            <span className="nav-logo-name">PRGuard</span>
          </div>
          <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
            {theme === "dark" ? "☀" : "◑"}
          </button>
        </nav>

        <div className={`auth-card ${mounted ? "visible" : ""}`}>
          <div className="auth-logo">
            <div className="auth-logo-icon">PG</div>
            <span className="auth-logo-name">PRGuard</span>
          </div>

          <div className="rag-badge">
            <span className="rag-badge-dot" />
            Codebase Learning Assistant
          </div>

          <h1 className="auth-heading">
            Welcome back.<br />
            <span className="accent">Sign in to continue.</span>
          </h1>

          <p className="auth-sub">
            Connect your GitHub account to access your indexed repos and AI-powered codebase insights.
          </p>

          <div className="auth-features">
            {[
              "RAG-powered codebase indexing",
              "GitHub issues linked to code",
              "Claude Sonnet + LangSmith tracing",
            ].map((f) => (
              <div className="auth-feature-item" key={f}>
                <span className="auth-feature-dot" />
                {f}
              </div>
            ))}
          </div>

          <button className="github-btn" onClick={handleGitHubLogin} type="button">
            <GitHubIcon />
            Continue with GitHub
          </button>

          <p className="auth-switch">
            Admin access? <a href="/admin/login">Use email sign-in →</a>
          </p>

          <p className="auth-legal">
            By signing in, you agree to our{" "}
            <a href="#">Terms of Service</a> and{" "}
            <a href="#">Privacy Policy</a>.
          </p>

          <p className="auth-switch">
            No account yet?
            <a href="/signup"> Create one →</a>
          </p>
        </div>
      </div>
    </>
  );
}

function GitHubIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
    </svg>
  );
}