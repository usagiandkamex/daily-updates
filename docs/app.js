/* global app.js — Daily Updates GitHub Pages */
/* eslint-env browser */
(function () {
  "use strict";

  // ── constants ────────────────────────────────────────────────────
  const PAGE_SIZE    = 12;
  const LATEST_COUNT = 6;

  const TYPE_LABEL = {
    daily:          "Daily",
    smallchat_am:   "SmallChat AM",
    smallchat_pm:   "SmallChat PM",
  };
  const TYPE_BADGE = {
    daily:          "badge-daily",
    smallchat_am:   "badge-sm-am",
    smallchat_pm:   "badge-sm-pm",
  };

  // tag name → CSS class suffix (keeps class names ASCII-safe)
  const TAG_CLASS = {
    "Azure":        "azure",
    "AI":           "ai",
    "Microsoft":    "microsoft",
    "セキュリティ":  "security",
    "クラウド":      "cloud",
    "ニュース":      "news",
    "ビジネス":      "business",
    "SNS":          "sns",
  };

  // ── state ────────────────────────────────────────────────────────
  let allUpdates      = [];
  let filteredUpdates = [];
  let currentPage     = 1;
  let activeTags      = new Set();
  let dateFrom        = "";
  let dateTo          = "";
  let searchQuery     = "";
  let activeTypes     = new Set(["daily", "smallchat_am", "smallchat_pm"]);

  // ── DOM helpers ──────────────────────────────────────────────────
  const $  = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];

  function esc(str) {
    const d = document.createElement("div");
    d.appendChild(document.createTextNode(str ?? ""));
    return d.innerHTML;
  }

  function highlight(text, query) {
    if (!query) return esc(text);
    const safe   = esc(text);
    const re     = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    return safe.replace(re, (m) => `<mark class="hl">${m}</mark>`);
  }

  // ── rendering ────────────────────────────────────────────────────
  function tagClass(tag) {
    return "tag-" + (TAG_CLASS[tag] || "default");
  }

  function tagsHtml(tags) {
    if (!tags || !tags.length) return "";
    return (
      '<div class="card-tags">' +
      tags
        .map(
          (t) =>
            `<span class="tag ${tagClass(t)}" data-tag="${esc(t)}">${esc(t)}</span>`
        )
        .join("") +
      "</div>"
    );
  }

  function cardHtml(u, query) {
    const badge  = TYPE_BADGE[u.type] || "badge-daily";
    const label  = TYPE_LABEL[u.type] || u.type;
    const title  = highlight(u.title, query);
    const excerpt = u.excerpt ? highlight(u.excerpt, query) : "";

    return `
<div class="card" data-date="${esc(u.date)}" data-type="${esc(u.type)}">
  <div class="card-header">
    <span class="badge ${badge}">${esc(label)}</span>
    <span class="card-date">${esc(u.date_formatted || u.date)}</span>
  </div>
  <h3 class="card-title">${title}</h3>
  ${excerpt ? `<p class="card-excerpt">${excerpt}</p>` : ""}
  ${tagsHtml(u.tags)}
  <div class="card-footer">
    <a href="article.html?slug=${esc(u.slug)}" class="btn-read">Read →</a>
  </div>
</div>`;
  }

  // ── Latest section ───────────────────────────────────────────────
  function renderLatest() {
    const latest = allUpdates.slice(0, LATEST_COUNT);
    const grid   = $("#latest-grid");
    if (latest.length === 0) {
      grid.innerHTML = `
<div class="empty-state">
  <div class="empty-state-icon">📭</div>
  <p>アップデートはありません</p>
</div>`;
      return;
    }
    grid.innerHTML = latest.map((u) => cardHtml(u, "")).join("");

    // Tag click → jump to archive with that tag active
    $$(".tag", grid).forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const tag = el.dataset.tag;
        if (tag) {
          addTagFilter(tag);
          $("#archive").scrollIntoView({ behavior: "smooth" });
        }
      });
    });
  }

  // ── Archive section ──────────────────────────────────────────────
  function applyFilters() {
    const q = searchQuery.toLowerCase();
    filteredUpdates = allUpdates.filter((u) => {
      if (!activeTypes.has(u.type)) return false;
      if (activeTags.size > 0) {
        const uSet = new Set(u.tags || []);
        if (![...activeTags].every((t) => uSet.has(t))) return false;
      }
      if (dateFrom && u.date < dateFrom) return false;
      if (dateTo   && u.date > dateTo)   return false;
      if (q) {
        if (!(u.search_text || "").includes(q)) return false;
      }
      return true;
    });
    currentPage = 1;
    renderPage();
  }

  function renderPage() {
    const total      = filteredUpdates.length;
    const totalPages = Math.ceil(total / PAGE_SIZE);
    const start      = (currentPage - 1) * PAGE_SIZE;
    const slice      = filteredUpdates.slice(start, start + PAGE_SIZE);

    $("#archive-count").textContent = `${total} 件`;

    const grid = $("#archive-grid");
    if (slice.length === 0) {
      grid.innerHTML = `
<div class="empty-state">
  <div class="empty-state-icon">🔍</div>
  <p>条件に一致するアップデートが見つかりませんでした</p>
</div>`;
    } else {
      grid.innerHTML = slice.map((u) => cardHtml(u, searchQuery)).join("");
      $$(".tag", grid).forEach((el) => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          const tag = el.dataset.tag;
          if (tag) addTagFilter(tag);
        });
      });
    }

    // Pagination
    const pager = $("#pagination");
    if (totalPages <= 1) {
      pager.innerHTML = "";
      return;
    }

    const lo    = Math.max(1, currentPage - 2);
    const hi    = Math.min(totalPages, currentPage + 2);
    let html    = "";

    if (currentPage > 1)
      html += `<button class="page-btn" data-page="${currentPage - 1}">‹ 前へ</button>`;
    for (let i = lo; i <= hi; i++)
      html += `<button class="page-btn${i === currentPage ? " active" : ""}" data-page="${i}">${i}</button>`;
    if (currentPage < totalPages)
      html += `<button class="page-btn" data-page="${currentPage + 1}">次へ ›</button>`;

    pager.innerHTML = html;
    $$(".page-btn", pager).forEach((btn) => {
      btn.addEventListener("click", () => {
        currentPage = parseInt(btn.dataset.page, 10);
        renderPage();
        $("#archive").scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  // ── Tag filter buttons ───────────────────────────────────────────
  function allTagsSorted() {
    const s = new Set();
    allUpdates.forEach((u) => (u.tags || []).forEach((t) => s.add(t)));
    return [...s].sort();
  }

  function renderTagFilters() {
    const container = $("#tag-filters");
    const tags = allTagsSorted();
    const tagRow = container.closest(".filter-row");

    // Hide entire tag filter row when no tags exist
    if (tags.length === 0) {
      if (tagRow) tagRow.style.display = "none";
      container.innerHTML = "";
      return;
    }
    if (tagRow) tagRow.style.display = "";

    container.innerHTML = tags
      .map(
        (tag) =>
          `<button class="tag-filter-btn${activeTags.has(tag) ? " active" : ""}" data-tag="${esc(tag)}">${esc(tag)}</button>`
      )
      .join("");

    $$(".tag-filter-btn", container).forEach((btn) => {
      btn.addEventListener("click", () => {
        const tag = btn.dataset.tag;
        if (activeTags.has(tag)) {
          activeTags.delete(tag);
          btn.classList.remove("active");
        } else {
          activeTags.add(tag);
          btn.classList.add("active");
        }
        syncClearTagsBtn();
        syncClearAllBtn();
        applyFilters();
      });
    });
  }

  function addTagFilter(tag) {
    activeTags.add(tag);
    renderTagFilters();
    syncClearTagsBtn();
    syncClearAllBtn();
    applyFilters();
  }

  function syncClearTagsBtn() {
    $("#clear-tags").style.display = activeTags.size ? "" : "none";
  }

  function syncClearDatesBtn() {
    $("#clear-dates").style.display = dateFrom || dateTo ? "" : "none";
  }

  function syncClearSearchBtn() {
    $("#clear-search").style.display = searchQuery ? "" : "none";
  }

  function syncClearTypesBtn() {
    const allChecked = activeTypes.size === 3;
    $("#clear-types").style.display = allChecked ? "none" : "";
  }

  function syncClearAllBtn() {
    const hasAny =
      activeTags.size > 0 ||
      dateFrom || dateTo ||
      searchQuery ||
      activeTypes.size !== 3;
    $("#clear-all").style.display = hasAny ? "" : "none";
  }

  // ── Event wiring ─────────────────────────────────────────────────
  function bindEvents() {
    // Search input in archive filter bar
    $("#global-search").addEventListener("input", (e) => {
      searchQuery = e.target.value.trim();
      syncClearSearchBtn();
      syncClearAllBtn();
      applyFilters();
    });

    // Date filters
    $("#date-from").addEventListener("change", (e) => {
      dateFrom = e.target.value.replace(/-/g, "");
      syncClearDatesBtn();
      syncClearAllBtn();
      applyFilters();
    });
    $("#date-to").addEventListener("change", (e) => {
      dateTo = e.target.value.replace(/-/g, "");
      syncClearDatesBtn();
      syncClearAllBtn();
      applyFilters();
    });

    // Clear buttons
    $("#clear-tags").addEventListener("click", () => {
      activeTags.clear();
      renderTagFilters();
      syncClearTagsBtn();
      syncClearAllBtn();
      applyFilters();
    });
    $("#clear-dates").addEventListener("click", () => {
      dateFrom = dateTo = "";
      $("#date-from").value = "";
      $("#date-to").value   = "";
      syncClearDatesBtn();
      syncClearAllBtn();
      applyFilters();
    });
    $("#clear-search").addEventListener("click", () => {
      searchQuery = "";
      $("#global-search").value = "";
      syncClearSearchBtn();
      syncClearAllBtn();
      applyFilters();
    });
    $("#clear-types").addEventListener("click", () => {
      activeTypes = new Set(["daily", "smallchat_am", "smallchat_pm"]);
      $$(".type-checkbox input").forEach((cb) => { cb.checked = true; });
      syncClearTypesBtn();
      syncClearAllBtn();
      applyFilters();
    });

    // Clear all button
    $("#clear-all").addEventListener("click", () => {
      // Reset search
      searchQuery = "";
      $("#global-search").value = "";
      // Reset tags
      activeTags.clear();
      renderTagFilters();
      // Reset dates
      dateFrom = dateTo = "";
      $("#date-from").value = "";
      $("#date-to").value   = "";
      // Reset types
      activeTypes = new Set(["daily", "smallchat_am", "smallchat_pm"]);
      $$(".type-checkbox input").forEach((cb) => { cb.checked = true; });
      // Sync all clear buttons
      syncClearSearchBtn();
      syncClearTagsBtn();
      syncClearDatesBtn();
      syncClearTypesBtn();
      syncClearAllBtn();
      applyFilters();
    });

    // Type checkboxes
    $$(".type-checkbox input").forEach((cb) => {
      cb.addEventListener("change", () => {
        activeTypes = new Set(
          $$(".type-checkbox input:checked").map((c) => c.value)
        );
        syncClearTypesBtn();
        syncClearAllBtn();
        applyFilters();
      });
    });
  }

  // ── Bootstrap ────────────────────────────────────────────────────
  async function init() {
    try {
      const res  = await fetch("data.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      allUpdates = data.updates || [];

      if (data.generated_at) {
        const dt = new Date(data.generated_at);
        $("#footer-generated").textContent =
          "Data generated: " +
          dt.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" }) +
          " JST";
      }
    } catch (err) {
      console.error("Failed to load data.json:", err);
      const msg = '<div class="loading">データの読み込みに失敗しました</div>';
      $("#latest-grid").innerHTML  = msg;
      $("#archive-grid").innerHTML = msg;
      return;
    }

    renderLatest();
    renderTagFilters();
    applyFilters();
    bindEvents();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
