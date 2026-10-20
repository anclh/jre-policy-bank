(() => {
  const state = {
    lang: localStorage.getItem("jre-lang") || "zh",
    view: "browse",
    query: "",
    departments: new Set(),
    themes: new Set(),
    sort: "newest",
    data: null,
  };

  const el = {
    search: document.getElementById("search"),
    clear: document.getElementById("clearSearch"),
    deptChips: document.getElementById("deptChips"),
    themeChips: document.getElementById("themeChips"),
    cards: document.getElementById("cards"),
    count: document.getElementById("count"),
    sort: document.getElementById("sort"),
    browse: document.getElementById("browse"),
    digest: document.getElementById("digest"),
    digestBody: document.getElementById("digestBody"),
    langBtns: document.querySelectorAll("[data-lang]"),
    viewBtns: document.querySelectorAll("[data-view]"),
    i18n: document.querySelectorAll("[data-i18n]"),
  };

  const i18n = {
    zh: {
      subtitle: "面試取向時事／政策資料庫（公開政府來源）",
      heroTitle: "搜尋近期香港政策動向",
      heroLede: "關鍵字搜尋、政策局／署過濾、主題標籤、摘要與面試角度——素材來自 info.gov.hk 等公開公報，非任何收費資料庫內容。",
      disclaimer: "免責：本工具僅供面試備試參考。摘要與面試角度為原創整理，請以原文公報為準。與 CS Radar 無關，亦未使用其付費內容。",
      searchPh: "搜尋標題、摘要、部門、主題…",
      clear: "清除",
      depts: "政策局／部門",
      themes: "政策主題",
      results: "結果",
      sortLabel: "排序",
      newest: "最新優先",
      oldest: "最舊優先",
      angles: "面試角度／提問",
      source: "原文連結",
      browse: "瀏覽",
      digest: "每周摘要",
      digestTitle: "近14天按部門／局別整理",
      digestLede: "將最近兩周的政策項目按部門分組，方便快速複習。",
      empty: "沒有符合條件的項目。試試清空篩選或換關鍵字。",
      loadError: "無法載入 data/policies.json。請用本地伺服器開啟（見 README），勿直接用 file:// 若瀏覽器封鎖 fetch。",
      items: "項",
      all: "全部",
    },
    en: {
      subtitle: "Interview-oriented HK policy bank (public sources)",
      heroTitle: "Search recent Hong Kong policy developments",
      heroLede: "Keyword search, bureau filters, theme chips, summaries and interview angles — from public info.gov.hk releases, not any paid database.",
      disclaimer: "Disclaimer: For interview prep only. Summaries and angles are original notes; rely on the official release. Not affiliated with CS Radar; no paid content used.",
      searchPh: "Search title, summary, departments, themes…",
      clear: "Clear",
      depts: "Bureaux / departments",
      themes: "Policy themes",
      results: "Results",
      sortLabel: "Sort",
      newest: "Newest first",
      oldest: "Oldest first",
      angles: "Interview angles / questions",
      source: "Source link",
      browse: "Browse",
      digest: "Weekly digest",
      digestTitle: "Last 14 days by department",
      digestLede: "Recent items grouped by bureau/department for quick revision.",
      empty: "No matching items. Clear filters or try another keyword.",
      loadError: "Could not load data/policies.json. Serve via a local server (see README); file:// may block fetch.",
      items: "items",
      all: "All",
    },
  };

  function t(key) {
    return i18n[state.lang][key] || key;
  }

  function applyI18n() {
    el.i18n.forEach((node) => {
      const key = node.getAttribute("data-i18n");
      if (key) node.textContent = t(key);
    });
    el.search.placeholder = t("searchPh");
    el.langBtns.forEach((b) => b.classList.toggle("active", b.dataset.lang === state.lang));
    el.viewBtns.forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
    document.documentElement.lang = state.lang === "zh" ? "zh-Hant" : "en";
  }

  function deptLabel(id) {
    const d = state.data.departments.find((x) => x.id === id);
    if (!d) return id;
    return state.lang === "zh" ? d.zh : d.en;
  }

  function themeLabel(id) {
    const th = state.data.themes.find((x) => x.id === id);
    if (!th) return id;
    return state.lang === "zh" ? th.zh : th.en;
  }

  function itemTitle(item) {
    if (state.lang === "en" && item.title_en) return item.title_en;
    return item.title;
  }

  function buildChips() {
    const mk = (container, list, set, kind) => {
      container.innerHTML = "";
      const all = document.createElement("button");
      all.type = "button";
      all.className = "chip" + (set.size === 0 ? " active" : "");
      all.textContent = t("all");
      all.addEventListener("click", () => {
        set.clear();
        buildChips();
        render();
      });
      container.appendChild(all);

      list.forEach((entry) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip" + (set.has(entry.id) ? " active" : "");
        btn.textContent = state.lang === "zh" ? entry.zh : entry.en;
        btn.addEventListener("click", () => {
          if (set.has(entry.id)) set.delete(entry.id);
          else set.add(entry.id);
          buildChips();
          render();
        });
        container.appendChild(btn);
      });
    };
    mk(el.deptChips, state.data.departments, state.departments, "dept");
    mk(el.themeChips, state.data.themes, state.themes, "theme");
  }

  function matches(item) {
    const q = state.query.trim().toLowerCase();
    if (state.departments.size) {
      const ok = item.departments.some((d) => state.departments.has(d));
      if (!ok) return false;
    }
    if (state.themes.size) {
      const ok = item.themes.some((th) => state.themes.has(th));
      if (!ok) return false;
    }
    if (!q) return true;
    const hay = [
      item.title,
      item.title_en || "",
      item.summary,
      ...(item.interview_angles || []),
      ...item.departments.map(deptLabel),
      ...item.themes.map(themeLabel),
      item.source_name || "",
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  }

  function filtered() {
    let items = state.data.items.filter(matches);
    items.sort((a, b) => {
      const cmp = a.date.localeCompare(b.date);
      return state.sort === "newest" ? -cmp : cmp;
    });
    return items;
  }

  function renderCards(items) {
    el.cards.innerHTML = "";
    if (!items.length) {
      el.cards.innerHTML = `<div class="empty">${t("empty")}</div>`;
      return;
    }
    const frag = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "card";
      const titleEn =
        state.lang === "zh" && item.title_en
          ? `<div class="title-en">${escapeHtml(item.title_en)}</div>`
          : state.lang === "en" && item.title && item.title_en
            ? `<div class="title-en">${escapeHtml(item.title)}</div>`
            : "";
      const deptTags = item.departments
        .map((d) => `<span class="tag">${escapeHtml(deptLabel(d))}</span>`)
        .join("");
      const themeTags = item.themes
        .map((th) => `<span class="tag theme">${escapeHtml(themeLabel(th))}</span>`)
        .join("");
      const angles = (item.interview_angles || [])
        .map((a) => `<li>${escapeHtml(a)}</li>`)
        .join("");
      card.innerHTML = `
        <div class="card-top">
          <span class="date-badge">${escapeHtml(item.date)}</span>
        </div>
        <h3>${escapeHtml(itemTitle(item))}</h3>
        ${titleEn}
        <div class="meta-tags">${deptTags}${themeTags}</div>
        <p class="summary">${escapeHtml(item.summary)}</p>
        <div class="angles">
          <h4>${t("angles")}</h4>
          <ol>${angles}</ol>
        </div>
        <div class="card-foot">
          <a class="source-link" href="${escapeAttr(item.source_url)}" target="_blank" rel="noopener noreferrer">${t("source")} ↗</a>
          <span class="source-name">${escapeHtml(item.source_name || "")}</span>
        </div>`;
      frag.appendChild(card);
    });
    el.cards.appendChild(frag);
  }

  function renderDigest() {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 14);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    const recent = state.data.items
      .filter((i) => i.date >= cutoffStr)
      .sort((a, b) => b.date.localeCompare(a.date));

    const byDept = new Map();
    recent.forEach((item) => {
      item.departments.forEach((d) => {
        if (!byDept.has(d)) byDept.set(d, []);
        byDept.get(d).push(item);
      });
    });

    const ordered = [...byDept.entries()].sort((a, b) => b[1].length - a[1].length);
    if (!ordered.length) {
      el.digestBody.innerHTML = `<div class="empty">${t("empty")}</div>`;
      return;
    }

    el.digestBody.innerHTML = ordered
      .map(([deptId, items]) => {
        const unique = [];
        const seen = new Set();
        items.forEach((it) => {
          if (!seen.has(it.id)) {
            seen.add(it.id);
            unique.push(it);
          }
        });
        const lis = unique
          .map(
            (it) => `<li>
              <div class="d-date">${escapeHtml(it.date)}</div>
              <a href="${escapeAttr(it.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(itemTitle(it))}</a>
              <p class="d-summary">${escapeHtml(it.summary.slice(0, 140))}${it.summary.length > 140 ? "…" : ""}</p>
            </li>`
          )
          .join("");
        return `<section class="digest-group">
          <h3>${escapeHtml(deptLabel(deptId))} · ${unique.length}</h3>
          <ul class="digest-list">${lis}</ul>
        </section>`;
      })
      .join("");
  }

  function render() {
    applyI18n();
    const items = filtered();
    el.count.textContent = `${t("results")}: ${items.length} ${t("items")}`;
    if (state.view === "browse") {
      el.browse.classList.remove("hidden");
      el.digest.classList.remove("visible");
      renderCards(items);
    } else {
      el.browse.classList.add("hidden");
      el.digest.classList.add("visible");
      renderDigest();
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  async function init() {
    applyI18n();
    el.langBtns.forEach((b) =>
      b.addEventListener("click", () => {
        state.lang = b.dataset.lang;
        localStorage.setItem("jre-lang", state.lang);
        buildChips();
        render();
      })
    );
    el.viewBtns.forEach((b) =>
      b.addEventListener("click", () => {
        state.view = b.dataset.view;
        render();
      })
    );
    el.search.addEventListener("input", () => {
      state.query = el.search.value;
      render();
    });
    el.clear.addEventListener("click", () => {
      el.search.value = "";
      state.query = "";
      render();
    });
    el.sort.addEventListener("change", () => {
      state.sort = el.sort.value;
      render();
    });

    try {
      const res = await fetch("data/policies.json", { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      state.data = await res.json();
      buildChips();
      render();
    } catch (err) {
      el.cards.innerHTML = `<div class="error">${t("loadError")}<br><small>${escapeHtml(String(err))}</small></div>`;
    }
  }

  init();
})();
