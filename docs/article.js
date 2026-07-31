/* article.js — Daily Updates article detail page */
/* eslint-env browser */
(function () {
  "use strict";

  const TYPE_LABEL = {
    daily:        "Daily",
    smallchat_am: "SmallChat AM",
    smallchat_pm: "SmallChat PM",
  };
  const TYPE_BADGE = {
    daily:        "badge-daily",
    smallchat_am: "badge-sm-am",
    smallchat_pm: "badge-sm-pm",
  };
  const TAG_CLASS = {
    "Azure":       "azure",
    "AI":          "ai",
    "Microsoft":   "microsoft",
    "セキュリティ": "security",
    "クラウド":     "cloud",
    "ニュース":     "news",
    "ビジネス":     "business",
    "SNS":         "sns",
  };

  // ── DOM helpers ──────────────────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);

  function esc(str) {
    const d = document.createElement("div");
    d.appendChild(document.createTextNode(str ?? ""));
    return d.innerHTML;
  }

  function tagClass(tag) {
    return "tag-" + (TAG_CLASS[tag] || "default");
  }

  // ── Simple markdown → HTML renderer ─────────────────────────────
  // Handles the subset of markdown used in daily update / smallchat files:
  // # H1, ## H2, ### H3, **bold**, [link](url), --- (hr), paragraphs.
  function renderMarkdown(md) {
    // Normalise line endings
    const lines = md.replace(/\r\n/g, "\n").split("\n");
    let html = "";
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];

      // Headings
      if (/^### /.test(line)) {
        html += `<h3>${inlineMarkdown(line.slice(4).trim())}</h3>\n`;
        i++;
        continue;
      }
      if (/^## /.test(line)) {
        html += `<h2>${inlineMarkdown(line.slice(3).trim())}</h2>\n`;
        i++;
        continue;
      }
      if (/^# /.test(line)) {
        html += `<h1>${inlineMarkdown(line.slice(2).trim())}</h1>\n`;
        i++;
        continue;
      }

      // Horizontal rule
      if (/^---+$/.test(line.trim())) {
        html += "<hr>\n";
        i++;
        continue;
      }

      // Blank line — paragraph separator
      if (line.trim() === "") {
        i++;
        continue;
      }

      // Paragraph: collect consecutive non-blank, non-heading lines
      const paraLines = [];
      while (
        i < lines.length &&
        lines[i].trim() !== "" &&
        !/^#{1,3} /.test(lines[i]) &&
        !/^---+$/.test(lines[i].trim())
      ) {
        paraLines.push(lines[i].trim());
        i++;
      }
      if (paraLines.length > 0) {
        html += `<p>${inlineMarkdown(paraLines.join(" "))}</p>\n`;
      }
    }
    return html;
  }

  function inlineMarkdown(text) {
    // Escape HTML
    text = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    // Bold: **text**
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Links: [label](url) - label may contain [] (e.g. [[In preview] text](url))
    text = text.replace(
      /\[([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]\(([^)]+)\)/g,
      (_, label, url) =>
        `<a href="${url.replace(/"/g, "&quot;")}" target="_blank" rel="noopener">${label}</a>`
    );
    // Auto-link bare URLs not already inside an <a> tag
    text = text.replace(
      /(?<!href="|>)(https?:\/\/[^\s<"]+[^\s<".,;:!?)」』）】])/g,
      '<a href="$1" target="_blank" rel="noopener">$1</a>'
    );
    return text;
  }

  // ── Render article ───────────────────────────────────────────────
  function renderArticle(data) {
    document.title = `${data.title} — Daily Updates`;

    const badge = TYPE_BADGE[data.type] || "badge-daily";
    const label = TYPE_LABEL[data.type] || data.type;

    const tagPills = (data.tags || [])
      .map(
        (t) =>
          `<span class="tag ${tagClass(t)}">${esc(t)}</span>`
      )
      .join("");

    const githubLink = data.github_url
      ? `<a href="${esc(data.github_url)}" target="_blank" rel="noopener" class="article-github-link">GitHubで見る →</a>`
      : "";

    $("#article-meta").innerHTML = `
<div class="article-header">
  <div class="article-header-row">
    <span class="badge ${badge}">${esc(label)}</span>
    <span class="article-date">${esc(data.date_formatted || data.date)}</span>
    ${githubLink}
  </div>
  <h1 class="article-title">${esc(data.title)}</h1>
  ${tagPills ? `<div class="card-tags">${tagPills}</div>` : ""}
</div>`;

    $("#article-body").innerHTML = renderMarkdown(data.content || "");
  }

  // ── Bootstrap ────────────────────────────────────────────────────
  async function init() {
    const params = new URLSearchParams(window.location.search);
    const slug   = params.get("slug") || "";

    if (!slug) {
      $("#article-body").innerHTML =
        '<div class="loading">記事が指定されていません</div>';
      return;
    }

    // Validate slug to prevent path traversal (only allow word chars, digits, underscores)
    if (!/^[\w-]+$/.test(slug)) {
      $("#article-body").innerHTML =
        '<div class="loading">無効な記事IDです</div>';
      return;
    }

    try {
      const res = await fetch(`articles/${slug}.json`, { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      renderArticle(data);
    } catch (err) {
      console.error("Failed to load article:", err);
      $("#article-body").innerHTML =
        '<div class="loading">記事の読み込みに失敗しました</div>';
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
