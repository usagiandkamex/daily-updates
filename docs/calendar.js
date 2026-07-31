/* calendar.js — Events Calendar section for Daily Updates */
/* eslint-env browser */
(function () {
  "use strict";

  // ── DOM helpers ──────────────────────────────────────────────────
  const $  = (sel, ctx) => (ctx || document).querySelector(sel);

  function esc(str) {
    const d = document.createElement("div");
    d.appendChild(document.createTextNode(str ?? ""));
    return d.innerHTML;
  }

  // ── State ────────────────────────────────────────────────────────
  let allEvents     = [];       // raw event array from events.json
  let eventsByDate  = {};       // { "2026-05-15": [event, ...], ... }
  let currentYear   = 0;
  let currentMonth  = 0;        // 0-indexed (0=Jan)
  let selectedDate  = null;     // "YYYY-MM-DD" | null

  // ── Helpers ──────────────────────────────────────────────────────

  /** 現在時刻を Asia/Tokyo の {year, month(0-indexed), day} として返す。 */
  function nowInJst() {
    // events.json は JST 基準で生成されるため、表示側も JST に揃える。
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const get = (t) => parts.find((p) => p.type === t).value;
    return {
      year: Number(get("year")),
      month: Number(get("month")) - 1, // 0-indexed
      day: Number(get("day")),
    };
  }

  /** connpass.com (subdomain ok) の HTTPS /event/ URL のみ許可。
   *  生成側 (_is_connpass_event_url) と同じポリシー。 */
  function isConnpassEventUrl(url) {
    if (typeof url !== "string") return false;
    let parsed;
    try {
      parsed = new URL(url);
    } catch (_) {
      return false;
    }
    if (parsed.protocol !== "https:") return false;
    const host = (parsed.hostname || "").toLowerCase();
    if (host !== "connpass.com" && !host.endsWith(".connpass.com")) return false;
    return parsed.pathname.startsWith("/event/");
  }

  /** 大手ベンダー・大規模カンファレンスおよびニュースサイトの HTTPS URL を許可。
   *  events.json の vendor_event フラグが付いたエントリに使用する。 */
  const _TRUSTED_VENDOR_HOSTS = new Set([
    "news.google.com",
    "microsoft.com", "build.microsoft.com", "ignite.microsoft.com",
    "techcommunity.microsoft.com", "azure.microsoft.com",
    "aws.amazon.com", "awsevents.com", "reinvent.awsevents.com",
    "cloud.google.com", "next.google.com",
    "cncf.io", "events.linuxfoundation.org", "linuxfoundation.org",
    "github.com", "githubuniverse.com",
    "redhat.com", "summit.redhat.com",
    "hashicorp.com", "hashiconf.com",
    "vmware.com", "explore.vmware.com",
    "databricks.com", "dataaisummit.com",
    "openai.com",
    "nvidia.com", "gtc.nvidia.com",
    "io.google", "events.google.com",
  ]);

  function isTrustedVendorUrl(url) {
    if (typeof url !== "string") return false;
    let parsed;
    try {
      parsed = new URL(url);
    } catch (_) {
      return false;
    }
    if (parsed.protocol !== "https:") return false;
    const host = (parsed.hostname || "").toLowerCase();
    // 完全一致またはサブドメイン一致（e.g. "foo.aws.amazon.com"）
    for (const trusted of _TRUSTED_VENDOR_HOSTS) {
      if (host === trusted || host.endsWith("." + trusted)) return true;
    }
    return false;
  }

  /** イベント URL が安全かどうかを判定する（connpass または信頼できるベンダー URL）。 */
  function isSafeEventUrl(url, isVendorEvent) {
    if (isVendorEvent) return isTrustedVendorUrl(url);
    return isConnpassEventUrl(url);
  }

  /** "2026/05/15 19:00" → "2026-05-15" */
  function startedAtToDate(startedAt) {
    if (!startedAt) return null;
    const m = startedAt.match(/^(\d{4})\/(\d{2})\/(\d{2})/);
    return m ? `${m[1]}-${m[2]}-${m[3]}` : null;
  }

  /** Build eventsByDate index */
  function indexEvents() {
    eventsByDate = {};
    for (const ev of allEvents) {
      const d = startedAtToDate(ev.started_at);
      if (!d) continue;
      if (!eventsByDate[d]) eventsByDate[d] = [];
      eventsByDate[d].push(ev);
    }
  }

  // ── Calendar render ──────────────────────────────────────────────

  function renderMonthLabel() {
    const label = $(`#cal-month-label`);
    if (label) {
      label.textContent =
        `${currentYear}年 ${String(currentMonth + 1).padStart(2, "0")}月`;
    }
  }

  function renderDays() {
    const container = $("#cal-days");
    if (!container) return;

    const t = nowInJst();
    const todayStr = `${t.year}-${String(t.month + 1).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;

    // First day-of-week for the month (0=Sun)
    const firstDow = new Date(currentYear, currentMonth, 1).getDay();
    // Number of days in the month
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

    let html = "";

    // Total cells = leading empty + days. Pad to a full week for clean rows.
    const totalCells = firstDow + daysInMonth;
    const totalRows  = Math.ceil(totalCells / 7);

    for (let row = 0; row < totalRows; row++) {
      html += `<div class="cal-row" role="row">`;
      for (let col = 0; col < 7; col++) {
        const cellIndex = row * 7 + col;
        if (cellIndex < firstDow || cellIndex >= firstDow + daysInMonth) {
          // Leading or trailing empty cell
          html += `<div class="cal-cell cal-cell-empty" role="gridcell"></div>`;
          continue;
        }
        const day     = cellIndex - firstDow + 1;
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const evs     = eventsByDate[dateStr] || [];
        const hasEvs  = evs.length > 0;
        const isToday = dateStr === todayStr;
        const isSel   = dateStr === selectedDate;

        let cls = "cal-cell";
        if (hasEvs)  cls += " cal-cell-has-events";
        if (isToday) cls += " cal-cell-today";
        if (isSel)   cls += " cal-cell-selected";

        const countBadge = hasEvs
          ? `<span class="cal-event-count">${evs.length}</span>`
          : "";

        // ARIA grid モデル: row の子は gridcell。インタラクティブ化はネスト
        // した <button> で実現することで「ボタン」セマンティクスと grid 階層
        // 双方を満たす。イベントのない日は単なる gridcell。
        const ariaLabel = `${dateStr}${hasEvs ? ` (${evs.length}件のイベント)` : ""}`;
        if (hasEvs) {
          html += `
<div class="${cls}" role="gridcell">
  <button type="button" class="cal-cell-button" data-date="${dateStr}" aria-label="${ariaLabel}">
    <span class="cal-day-num">${day}</span>
    ${countBadge}
  </button>
</div>`;
        } else {
          html += `
<div class="${cls}" role="gridcell" aria-label="${ariaLabel}">
  <span class="cal-day-num">${day}</span>
</div>`;
        }
      }
      html += `</div>`;
    }

    container.innerHTML = html;

    // Click / keyboard handlers (button が click/Enter/Space をネイティブで処理)
    container.querySelectorAll(".cal-cell-button").forEach((btn) => {
      btn.addEventListener("click", () => selectDate(btn.dataset.date));
    });
  }

  function focusDayButton(dateStr) {
    if (!dateStr) return;
    const container = $("#cal-days");
    if (!container) return;
    const btn = container.querySelector(`.cal-cell-button[data-date="${dateStr}"]`);
    if (btn) btn.focus();
  }

  function selectDate(dateStr) {
    selectedDate = dateStr;

    // Re-render days to reflect new selected state
    renderDays();

    // Restore focus to the same day's button after re-render so that
    // keyboard / screen-reader users don't lose their place when the
    // grid's innerHTML is rebuilt.
    focusDayButton(dateStr);

    // Render event list panel
    renderDayPanel(dateStr);
  }

  function renderDayPanel(dateStr) {
    const panel = $("#cal-day-panel");
    const title = $("#cal-day-title");
    const list  = $("#cal-events-list");
    if (!panel || !title || !list) return;

    const evs = eventsByDate[dateStr] || [];
    const [y, mo, d] = dateStr.split("-");
    title.textContent = `${y}年${mo}月${d}日 のイベント (${evs.length}件)`;

    if (evs.length === 0) {
      list.innerHTML = `<li class="cal-event-item cal-event-empty">この日のイベントはありません</li>`;
    } else {
      list.innerHTML = evs
        .map((ev) => {
          const time  = ev.started_at ? ev.started_at.slice(11) : "";
          const place = ev.place || "";
          const descText = ev.description || ev.catch || "";
          const descHtml = descText ? `<p class="cal-event-catch">${esc(descText)}</p>` : "";
          const placeHtml = place
            ? `<span class="cal-event-place">📍 ${esc(place)}</span>`
            : "";
          const timeHtml = time
            ? `<span class="cal-event-time">🕐 ${esc(time)}</span>`
            : "";
          const meta = (timeHtml || placeHtml)
            ? `<div class="cal-event-meta">${timeHtml}${placeHtml}</div>`
            : "";
          const hasSafeUrl = isSafeEventUrl(ev.event_url, !!ev.vendor_event);
          const contentHtml = `
    <strong class="cal-event-title">${esc(ev.title)}</strong>
    ${meta}
    ${descHtml}
  `;
          return `
<li class="cal-event-item">
  ${hasSafeUrl
    ? `<a href="${esc(ev.event_url)}" target="_blank" rel="noopener noreferrer" class="cal-event-link cal-event-link--anchor">${contentHtml}</a>`
    : `<div class="cal-event-link cal-event-link--text">${contentHtml}</div>`}
</li>`;
        })
        .join("");
    }

    panel.hidden = false;
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ── Navigation ───────────────────────────────────────────────────

  function gotoMonth(year, month) {
    currentYear  = year;
    currentMonth = month;
    selectedDate = null;

    const panel = $("#cal-day-panel");
    if (panel) panel.hidden = true;

    renderMonthLabel();
    renderDays();
  }

  // ── Bootstrap ────────────────────────────────────────────────────

  async function initCalendar() {
    const widget = $("#calendar-widget");
    if (!widget) return;

    // Show loading
    const loadingEl = $("#cal-loading");

    try {
      const res = await fetch("events.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allEvents = data.events || [];
    } catch (err) {
      console.error("Failed to load events.json:", err);
      if (loadingEl) {
        loadingEl.textContent = "イベントデータの読み込みに失敗しました";
      }
      return;
    }

    if (loadingEl) loadingEl.remove();

    indexEvents();

    // Set initial month to today (JST)
    const t = nowInJst();
    currentYear  = t.year;
    currentMonth = t.month;

    renderMonthLabel();
    renderDays();

    // Wire up navigation buttons
    const prevBtn = $("#cal-prev");
    const nextBtn = $("#cal-next");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        let m = currentMonth - 1;
        let y = currentYear;
        if (m < 0) { m = 11; y--; }
        gotoMonth(y, m);
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        let m = currentMonth + 1;
        let y = currentYear;
        if (m > 11) { m = 0; y++; }
        gotoMonth(y, m);
      });
    }

    // Close panel button
    const closeBtn = $("#cal-close-panel");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        const prevSelectedDate = selectedDate;
        selectedDate = null;
        const panel = $("#cal-day-panel");
        if (panel) panel.hidden = true;
        renderDays();
        focusDayButton(prevSelectedDate);
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initCalendar);
})();
