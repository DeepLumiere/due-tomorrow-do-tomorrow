"use client";

import { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem("evalboard_theme");
    if (stored === "dark" || stored === "light") {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      setTheme("dark");
      document.documentElement.setAttribute("data-theme", "dark");
    }
  }, []);

  function toggleTheme() {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);
    localStorage.setItem("evalboard_theme", nextTheme);
    document.documentElement.setAttribute("data-theme", nextTheme);
  }

  if (!mounted) {
    return (
      <button className="button button-outline button-small theme-toggle-btn" type="button" aria-label="Toggle theme">
        <Sun size={14} />
      </button>
    );
  }

  return (
    <button
      className="button button-outline button-small theme-toggle-btn"
      onClick={toggleTheme}
      title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
      aria-label="Toggle light/dark theme"
      type="button"
    >
      {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
      <span className="theme-toggle-text">{theme === "light" ? "Dark" : "Light"}</span>
    </button>
  );
}
