import { useEffect, useState, useContext } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { ThemeContext } from "../App";
import { getGithubLoginUrl, setScopedApiKey, setScopedProvider } from "../api/client";
import { useSession } from "../hooks/useSession";

const PROVIDER_LIST = [
  { id: "claude",  label: "Claude Sonnet",   sub: "Anthropic · Best for code",    placeholder: "sk-ant-...", recommended: true  },
  { id: "gpt",    label: "GPT-4o",          sub: "OpenAI · Most popular",         placeholder: "sk-...",     recommended: false },
  { id: "gemini",  label: "Gemini 1.5 Pro",  sub: "Google · Free tier available",  placeholder: "AIza...",    recommended: false },
];

const getStyles = (theme) => {
  const dark = theme === "dark";
  return `
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Syne:wght@400;500;600;700;800&display=swap');

    .auth-root {
      min-height: 100vh;
      background: ${dark ? "#0a0a0a" : "#f4f1eb"};
      display: flex; align-items: center; justify-content: center;
      font-family: 'Syne', sans-serif;
      position: relative; overflow: hidden; padding-top: 56px;
    }
    .auth-grid {
      position: absolute; inset: 0;
      background-image:
        linear-gradient(${dark ? "rgba(234,179,8,0.04)" : "rgba(120,80,0,0.06)"} 1px, transparent 1px),
        linear-gradient(90deg, ${dark ? "rgba(234,179,8,0.04)" : "rgba(120,80,0,0.06)"} 1px, transparent 1px);
      background-size: 48px 48px; pointer-events: none;
    }
    .auth-glow {
      position: absolute; width: 600px; height: 600px; border-radius: 50%;
      background: radial-gradient(circle, rgba(234,179,8,0.07) 0%, transparent 70%);
      top: -200px; right: -200px; pointer-events: none;
    }
    .auth-glow-2 {
      position: absolute; width: 400px; height: 400px; border-radius: 50%;
      background: radial-gradient(circle, rgba(234,179,8,0.05) 0%, transparent 70%);
      bottom: -150px; left: -100px; pointer-events: none;
    }
    .auth-navbar {
      position: fixed; top: 0; left: 0; right: 0; height: 56px;
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 24px;
      background: ${dark ? "rgba(10,10,10,0.85)" : "rgba(244,241,235,0.9)"};
      backdrop-filter: blur(12px);
      border-bottom: 1px solid ${dark ? "#1a1a1a" : "#e5e0d5"};
      z-index: 100;
    }
    .nav-logo { display: flex; align-items: center; gap: 8px; }
    .nav-logo-icon {
      width: 28px; height: 28px; background: #eab308; border-radius: 6px;
      display: flex; align-items: center; justify-content: center;
      font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 11px; color: #0a0a0a;
    }
    .nav-logo-name { font-size: 15px; font-weight: 700; color: ${dark ? "#ffffff" : "#0a0a0a"}; letter-spacing: -0.2px; }
    .theme-toggle {
      width: 34px; height: 34px;
      background: ${dark ? "#1a1a1a" : "#ece7dc"};
      border: 1px solid ${dark ? "#2a2a2a" : "#ddd8cc"};
      border-radius: 8px; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      font-size: 15px; transition: background 0.2s;
      color: ${dark ? "#888888" : "#666"};
    }
    .theme-toggle:hover { background: ${dark ? "#222222" : "#e2ddd2"}; }

    /* ── Card ── */
    .auth-card {
      position: relative; width: 460px;
      max-width: calc(100vw - 48px);
      background: ${dark ? "#111111" : "#ffffff"};
      border: 1px solid ${dark ? "#1e1e1e" : "#e8e3d8"};
      border-radius: 16px; padding: 40px 36px;
      opacity: 0; transform: translateY(20px);
      transition: opacity 0.45s ease, transform 0.45s ease;
      ${!dark ? "box-shadow: 0 4px 24px rgba(0,0,0,0.06);" : ""}
    }
    .auth-card.visible { opacity: 1; transform: translateY(0); }

    .auth-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }
    .auth-logo-icon {
      width: 34px; height: 34px; background: #eab308; border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 12px; color: #0a0a0a;
    }
    .auth-logo-name { font-size: 17px; font-weight: 700; color: ${dark ? "#ffffff" : "#0a0a0a"}; letter-spacing: -0.3px; }

    /* ── Step indicator ── */
    .step-indicator {
      display: flex; align-items: center; gap: 0;
      margin-bottom: 28px;
    }
    .step-item {
      display: flex; align-items: center; gap: 8px;
      font-size: 11px; font-family: 'JetBrains Mono', monospace;
    }
    .step-dot {
      width: 22px; height: 22px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 10px; font-weight: 700; flex-shrink: 0;
      transition: all 0.2s;
    }
    .step-dot.active { background: #eab308; color: #0a0a0a; }
    .step-dot.done { background: #22c55e; color: #ffffff; }
    .step-dot.inactive { background: ${dark ? "#1e1e1e" : "#e8e3d8"}; color: ${dark ? "#444" : "#aaa"}; }
    .step-label.active { color: ${dark ? "#ffffff" : "#0a0a0a"}; font-weight: 600; }
    .step-label.done { color: #22c55e; }
    .step-label.inactive { color: ${dark ? "#444444" : "#aaaaaa"}; }
    .step-line {
      flex: 1; height: 1px; margin: 0 10px;
      background: ${dark ? "#1e1e1e" : "#e8e3d8"};
      transition: background 0.3s;
    }
    .step-line.done { background: #22c55e; }

    /* ── Badge ── */
    .rag-badge {
      display: inline-flex; align-items: center; gap: 7px;
      background: ${dark ? "#181818" : "#f4efe4"};
      border: 1px solid ${dark ? "#282828" : "#e8e3d8"};
      border-radius: 20px; padding: 5px 12px; font-size: 11px;
      color: ${dark ? "#777777" : "#888888"};
      font-family: 'JetBrains Mono', monospace; margin-bottom: 20px; letter-spacing: 0.2px;
    }
    .rag-badge-dot { width: 6px; height: 6px; border-radius: 50%; background: #eab308; flex-shrink: 0; }

    .auth-heading { font-size: 22px; font-weight: 800; color: ${dark ? "#ffffff" : "#0a0a0a"}; line-height: 1.25; margin: 0 0 10px; letter-spacing: -0.5px; }
    .auth-heading .accent { color: #eab308; }
    .auth-sub { font-size: 13px; color: ${dark ? "#555555" : "#888888"}; margin: 0 0 24px; line-height: 1.6; font-family: 'JetBrains Mono', monospace; }

    .signup-notice {
      margin: 0 0 16px;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      line-height: 1.5;
      border: 1px solid;
    }
    .signup-notice.warn {
      color: ${dark ? "#fcd34d" : "#92400e"};
      background: ${dark ? "rgba(250,204,21,0.08)" : "rgba(251,191,36,0.12)"};
      border-color: ${dark ? "rgba(250,204,21,0.25)" : "rgba(217,119,6,0.28)"};
    }
    .signup-notice.info {
      color: ${dark ? "#93c5fd" : "#1d4ed8"};
      background: ${dark ? "rgba(59,130,246,0.08)" : "rgba(59,130,246,0.1)"};
      border-color: ${dark ? "rgba(59,130,246,0.25)" : "rgba(29,78,216,0.24)"};
    }
    .signup-notice a {
      color: inherit;
      text-decoration: underline;
      font-weight: 700;
    }

    /* ── Step 1: perks ── */
    .signup-perks { display: flex; flex-direction: column; gap: 8px; margin-bottom: 28px; }
    .perk-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .perk-card {
      background: ${dark ? "#181818" : "#f8f4ec"};
      border: 1px solid ${dark ? "#222222" : "#ece7dc"};
      border-radius: 10px; padding: 12px 14px;
      display: flex; flex-direction: column; gap: 6px;
    }
    .perk-num { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: #eab308; letter-spacing: 1px; }
    .perk-text { font-size: 12px; color: ${dark ? "#888888" : "#666666"}; font-family: 'JetBrains Mono', monospace; line-height: 1.4; }

    /* ── Step 2: provider rows ── */
    .provider-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
    .provider-row {
      background: ${dark ? "#181818" : "#f8f4ec"};
      border: 1px solid ${dark ? "#222222" : "#ece7dc"};
      border-radius: 10px; padding: 14px;
      transition: border-color 0.2s;
    }
    .provider-row.connected { border-color: #22c55e55; }
    .provider-row-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .provider-info { display: flex; align-items: center; gap: 8px; }
    .provider-status-dot {
      width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
      transition: background 0.2s;
    }
    .provider-name { font-size: 12px; font-weight: 600; color: ${dark ? "#ffffff" : "#0a0a0a"}; font-family: 'JetBrains Mono', monospace; }
    .provider-badge-recommended {
      font-size: 9px; padding: 1px 5px; border-radius: 3px;
      color: #eab308; background: rgba(234,179,8,0.12); border: 1px solid rgba(234,179,8,0.25);
    }
    .provider-badge-free {
      font-size: 9px; padding: 1px 5px; border-radius: 3px;
      color: #22c55e; background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.25);
    }
    .provider-active-label { font-size: 9px; color: #22c55e; font-family: 'JetBrains Mono', monospace; }
    .provider-sub { font-size: 10px; color: ${dark ? "#555555" : "#999999"}; font-family: 'JetBrains Mono', monospace; margin-bottom: 8px; }
    .provider-input-row { display: flex; gap: 6px; }
    .provider-input-wrap {
      flex: 1; display: flex; align-items: center;
      background: ${dark ? "#0f0f0f" : "#f0ece4"};
      border: 1px solid ${dark ? "#2a2a2a" : "#ddd8cc"};
      border-radius: 7px; overflow: hidden;
      transition: border-color 0.2s;
    }
    .provider-input-wrap.connected { border-color: #22c55e55; }
    .provider-input-wrap input {
      flex: 1; padding: 7px 10px; font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      background: transparent; border: none; outline: none;
      color: ${dark ? "#ffffff" : "#0a0a0a"};
    }
    .provider-input-wrap input::placeholder { color: ${dark ? "#333333" : "#bbbbbb"}; }
    .eye-btn {
      padding: 0 8px; background: transparent; border: none; cursor: pointer;
      color: ${dark ? "#555555" : "#999999"}; display: flex; align-items: center;
      transition: color 0.15s;
    }
    .eye-btn:hover { color: ${dark ? "#aaaaaa" : "#555555"}; }
    .save-btn {
      padding: 7px 12px; font-size: 11px; font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
      border-radius: 7px; cursor: pointer; transition: all 0.15s; flex-shrink: 0;
    }
    .save-btn:disabled { cursor: not-allowed; opacity: 0.5; }

    /* ── Skip note ── */
    .skip-note {
      text-align: center; font-size: 11px;
      color: ${dark ? "#3a3a3a" : "#bbbbbb"};
      font-family: 'JetBrains Mono', monospace;
      margin-bottom: 20px; line-height: 1.5;
    }
    .skip-note span { color: #eab308; }

    /* ── Buttons ── */
    .github-btn {
      width: 100%; display: flex; align-items: center; justify-content: center;
      gap: 11px; padding: 13px 24px; background: #eab308; color: #0a0a0a;
      border: none; border-radius: 10px; font-family: 'Syne', sans-serif;
      font-size: 15px; font-weight: 700; cursor: pointer;
      transition: background 0.2s, transform 0.15s, box-shadow 0.2s; letter-spacing: -0.2px;
    }
    .github-btn:hover { background: #f0c020; transform: translateY(-1px); box-shadow: 0 8px 24px rgba(234,179,8,0.28); }
    .github-btn:active { transform: translateY(0); box-shadow: none; }

    .continue-btn {
      width: 100%; padding: 13px 24px; background: #eab308; color: #0a0a0a;
      border: none; border-radius: 10px; font-family: 'Syne', sans-serif;
      font-size: 15px; font-weight: 700; cursor: pointer;
      transition: background 0.2s, transform 0.15s, box-shadow 0.2s; letter-spacing: -0.2px;
    }
    .continue-btn:hover { background: #f0c020; transform: translateY(-1px); box-shadow: 0 8px 24px rgba(234,179,8,0.28); }
    .continue-btn:active { transform: translateY(0); box-shadow: none; }

    .back-btn {
      background: transparent;
      border: 1px solid ${dark ? "#2a2a2a" : "#ddd8cc"};
      color: ${dark ? "#555555" : "#999999"};
      border-radius: 8px; padding: 7px 14px;
      font-size: 11px; font-family: 'JetBrains Mono', monospace;
      cursor: pointer; transition: all 0.15s;
    }
    .back-btn:hover { color: ${dark ? "#aaaaaa" : "#555555"}; border-color: ${dark ? "#444444" : "#bbbbbb"}; }

    /* ── Note row ── */
    .auth-note-row { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 14px; flex-wrap: wrap; }
    .auth-note-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: ${dark ? "#555555" : "#999999"}; font-family: 'JetBrains Mono', monospace; }
    .check-dot { width: 5px; height: 5px; border-radius: 50%; background: #eab308; flex-shrink: 0; }

    .auth-legal { text-align: center; font-size: 11px; color: ${dark ? "#3d3d3d" : "#aaaaaa"}; font-family: 'JetBrains Mono', monospace; line-height: 1.6; margin-top: 18px; margin-bottom: 0; }
    .auth-legal a { color: #eab308; text-decoration: none; }
    .auth-legal a:hover { text-decoration: underline; }
    .auth-switch { text-align: center; margin-top: 16px; font-size: 12px; color: ${dark ? "#444444" : "#aaaaaa"}; font-family: 'JetBrains Mono', monospace; margin-bottom: 0; }
    .auth-switch a { color: #eab308; text-decoration: none; font-weight: 600; }
    .auth-switch a:hover { text-decoration: underline; }
  `;
};

function EyeIcon({ open }) {
  return open ? (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

export default function Signup() {
  const { theme, toggleTheme } = useContext(ThemeContext);
  const location = useLocation();
  const { loading, isAdmin, isUser } = useSession();
  const dark = theme === "dark";
  const [mounted, setMounted] = useState(false);
  const [step, setStep] = useState(1);

  // Step 2 state
  const [apiKeys,   setApiKeys]   = useState({ claude: "", gpt: "", gemini: "" });
  const [showKeys,  setShowKeys]  = useState({ claude: false, gpt: false, gemini: false });
  const [savedKeys, setSavedKeys] = useState({ claude: false, gpt: false, gemini: false });
  const [connected, setConnected] = useState({ claude: false, gpt: false, gemini: false });
  const [activeId,  setActiveId]  = useState(null);

  useEffect(() => { setMounted(true); }, []);

  const handleGitHubSignup = () => {
    window.location.href = getGithubLoginUrl();
  };

  const handleSaveKey = (providerId) => {
    const key = apiKeys[providerId];
    if (!key) return;
    setScopedProvider(providerId);
    setScopedApiKey(key);
    setActiveId(providerId);
    setConnected(prev => ({ ...prev, [providerId]: true }));
    setSavedKeys(prev => ({ ...prev, [providerId]: true }));
    setTimeout(() => setSavedKeys(prev => ({ ...prev, [providerId]: false })), 1500);
  };

  const connectedCount = Object.values(connected).filter(Boolean).length;
  const params = new URLSearchParams(location.search || "");
  const reason = (params.get("reason") || "").toLowerCase();
  const existing = (params.get("existing_account") || "").toLowerCase();

  let notice = null;
  if (reason === "admin_local_login_required") {
    notice = {
      tone: "warn",
      text: "Admin accounts use the admin login page. Please continue there.",
      ctaHref: "/admin/login",
      ctaLabel: "Go to admin login",
    };
  } else if (reason === "account_exists" || existing === "1" || existing === "true") {
    notice = {
      tone: "info",
      text: "An account already exists for this email. Please sign in instead of creating a new account.",
      ctaHref: "/login",
      ctaLabel: "Go to login",
    };
  }

  if (!loading && isAdmin) {
    return <Navigate to="/admin/login?reason=admin_local_login_required" replace />;
  }

  if (!loading && isUser) {
    return <Navigate to="/dashboard" replace />;
  }

  const saveBtnStyle = (id) => ({
    border: `1px solid ${savedKeys[id] ? "#22c55e" : apiKeys[id] ? "#eab308" : dark ? "#2a2a2a" : "#ddd8cc"}`,
    background: savedKeys[id] ? "rgba(34,197,94,0.12)" : apiKeys[id] ? "rgba(234,179,8,0.15)" : dark ? "#0f0f0f" : "#f0ece4",
    color: savedKeys[id] ? "#22c55e" : apiKeys[id] ? "#eab308" : dark ? "#444444" : "#bbbbbb",
  });

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

          {notice && (
            <div className={`signup-notice ${notice.tone}`}>
              {notice.text} <Link to={notice.ctaHref}>{notice.ctaLabel}</Link>
            </div>
          )}

          {/* Logo */}
          <div className="auth-logo">
            <div className="auth-logo-icon">PG</div>
            <span className="auth-logo-name">PRGuard</span>
          </div>

          {/* Step indicator */}
          <div className="step-indicator">
            <div className="step-item">
              <div className={`step-dot ${step === 1 ? "active" : "done"}`}>
                {step > 1 ? "✓" : "1"}
              </div>
              <span className={`step-label ${step === 1 ? "active" : "done"}`}>GitHub</span>
            </div>
            <div className={`step-line ${step > 1 ? "done" : ""}`} />
            <div className="step-item">
              <div className={`step-dot ${step === 2 ? "active" : "inactive"}`}>2</div>
              <span className={`step-label ${step === 2 ? "active" : "inactive"}`}>API Key</span>
            </div>
          </div>

          {/* ── STEP 1 ── */}
          {step === 1 && (
            <>
              <div className="rag-badge">
                <span className="rag-badge-dot" />
                Free to get started
              </div>

              <h1 className="auth-heading">
                Start understanding<br />
                <span className="accent">any codebase.</span>
              </h1>
              <p className="auth-sub">
                One GitHub connection. PRGuard indexes your repo and answers anything — so you contribute with confidence.
              </p>

              <div className="signup-perks">
                <div className="perk-row">
                  <div className="perk-card">
                    <span className="perk-num">01</span>
                    <span className="perk-text">Connect a GitHub repo</span>
                  </div>
                  <div className="perk-card">
                    <span className="perk-num">02</span>
                    <span className="perk-text">PRGuard indexes the full codebase</span>
                  </div>
                </div>
                <div className="perk-row">
                  <div className="perk-card">
                    <span className="perk-num">03</span>
                    <span className="perk-text">Ask anything, get grounded answers</span>
                  </div>
                  <div className="perk-card">
                    <span className="perk-num">04</span>
                    <span className="perk-text">Ship PRs without getting lost</span>
                  </div>
                </div>
              </div>

              <button className="github-btn" onClick={() => setStep(2)}>
                <GitHubIcon />
                Sign up with GitHub
              </button>

              <div className="auth-note-row">
                <span className="auth-note-item"><span className="check-dot" />Free tier available</span>
                <span className="auth-note-item"><span className="check-dot" />No credit card needed</span>
                <span className="auth-note-item"><span className="check-dot" />Read-only access</span>
              </div>

              <p className="auth-legal">
                By creating an account, you agree to our{" "}
                <a href="#">Terms of Service</a> and <a href="#">Privacy Policy</a>.
              </p>
              <p className="auth-switch">
                Already have an account? <a href="/login">Sign in →</a>
              </p>
            </>
          )}

          {/* ── STEP 2 ── */}
          {step === 2 && (
            <>
              <div className="rag-badge">
                <span className="rag-badge-dot" />
                Connect an LLM provider
              </div>

              <h1 className="auth-heading">
                Add your API key.<br />
                <span className="accent">Power up PRGuard.</span>
              </h1>
              <p className="auth-sub">
                PRGuard uses your own API key to query the LLM — your key stays in your browser, never on our servers.
              </p>

              <div className="provider-list">
                {PROVIDER_LIST.map(provider => (
                  <div key={provider.id} className={`provider-row ${connected[provider.id] ? "connected" : ""}`}>
                    <div className="provider-row-top">
                      <div className="provider-info">
                        <span className="provider-status-dot"
                          style={{ background: connected[provider.id] ? "#22c55e" : dark ? "#2a2a2a" : "#ddd8cc" }} />
                        <span className="provider-name">{provider.label}</span>
                        {provider.recommended && <span className="provider-badge-recommended">recommended</span>}
                        {provider.id === "gemini" && <span className="provider-badge-free">free tier</span>}
                      </div>
                      {connected[provider.id] && activeId === provider.id &&
                        <span className="provider-active-label">● active</span>}
                    </div>
                    <div className="provider-sub">{provider.sub}</div>
                    <div className="provider-input-row">
                      <div className={`provider-input-wrap ${connected[provider.id] ? "connected" : ""}`}>
                        <input
                          type={showKeys[provider.id] ? "text" : "password"}
                          value={apiKeys[provider.id]}
                          placeholder={provider.placeholder}
                          onChange={e => setApiKeys(prev => ({ ...prev, [provider.id]: e.target.value }))}
                          onKeyDown={e => { if (e.key === "Enter") handleSaveKey(provider.id) }}
                        />
                        <button className="eye-btn"
                          onClick={() => setShowKeys(prev => ({ ...prev, [provider.id]: !prev[provider.id] }))}>
                          <EyeIcon open={showKeys[provider.id]} />
                        </button>
                      </div>
                      <button className="save-btn" style={saveBtnStyle(provider.id)}
                        disabled={!apiKeys[provider.id]}
                        onClick={() => handleSaveKey(provider.id)}>
                        {savedKeys[provider.id] ? "✓ Saved" : connected[provider.id] ? "Update" : "Save"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <p className="skip-note">
                🔒 Stored locally in your browser only.{" "}
                {connectedCount === 0 && <><br /><span>You can add this later from the dashboard.</span></>}
              </p>

              <button
                className="continue-btn"
                onClick={handleGitHubSignup}
              >
                {connectedCount > 0 ? `Continue with ${connectedCount} key${connectedCount > 1 ? "s" : ""} set →` : "Skip for now →"}
              </button>

              <div style={{ display: "flex", justifyContent: "center", marginTop: 14 }}>
                <button className="back-btn" onClick={() => setStep(1)}>← Back</button>
              </div>
            </>
          )}
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
  )
}