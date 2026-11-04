(() => {
  "use strict";

  const I18N = {
    zh: {
      listen: "听简报", listenAllTitle: "朗读今天的简报", archive: "往期", prev: "前一天", next: "后一天",
      deskAi: "人工智能", deskAiSub: "模型、产品、算力与资本",
      deskWorld: "全球要闻", deskWorldSub: "地缘、经济与社会",
      deskQuick: "简讯", deskQuickSub: "还值得知道的事，每条一句话",
      tagline: "人工智能 · 全球要闻 · 每日凌晨出版", todayKicker: "今日要点", issue: (n) => `第 ${n} 期`, terms: "名词", listenShort: "朗读",
      howTitle: "这份简报是怎么来的",
      how: "每天凌晨，系统自动从 OpenAI、Google DeepMind、Reuters、AP、BBC、Hacker News 等数十个信源抓取前一天的新闻，由 Claude 担任主编挑选与合并，再逐条写成中英双语的故事化解读。每条都附原始来源，方便你核实。",
      archiveTitle: "往期简报", stop: "停止", why: "为什么重要", pro: "专业视角", sources: "来源", lead: "头条",
      toc: "今日目录", stories: "篇深度", quickN: "条速览", readMin: "分钟读完", outlets: "个信源",
      edition: "日报", generated: "生成于", by: "编辑模型", empty: "这一天还没有简报。", failed: "简报加载失败，请稍后刷新。",
      reading: "正在朗读", noSpeech: "你的浏览器不支持朗读。", listenStory: "朗读这一篇",
      sec: { ai: "AI", world: "世界" },
    },
    en: {
      listen: "Listen", listenAllTitle: "Read today's brief aloud", archive: "Archive", prev: "Previous day", next: "Next day",
      deskAi: "Artificial Intelligence", deskAiSub: "Models, products, compute and capital",
      deskWorld: "The World", deskWorldSub: "Geopolitics, economy and society",
      deskQuick: "In Brief", deskQuickSub: "More worth knowing, one line each",
      tagline: "AI · The World · Published every dawn", todayKicker: "Today", issue: (n) => `No. ${n}`, terms: "Terms", listenShort: "Listen",
      howTitle: "How this brief is made",
      how: "Every night an automated pipeline gathers the previous day's news from dozens of sources — OpenAI, Google DeepMind, Reuters, AP, BBC, Hacker News and more. Claude acts as editor-in-chief, picks and merges what matters, and writes each story as a plain-language explainer in Chinese and English. Every story links back to its sources.",
      archiveTitle: "Past editions", stop: "Stop", why: "Why it matters", pro: "Pro lens", sources: "Sources", lead: "Lead story",
      toc: "In this edition", stories: "stories", quickN: "quick hits", readMin: "min read", outlets: "outlets",
      edition: "Edition", generated: "Generated", by: "Model", empty: "No brief for this day yet.", failed: "Couldn't load the brief. Please refresh in a moment.",
      reading: "Reading", noSpeech: "Your browser can't read aloud.", listenStory: "Listen to this story",
      sec: { ai: "AI", world: "World" },
    },
  };

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  let lang = store.get("daybreak.lang") || ((navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en");
  let index = null;
  let edition = null;
  const t = (k) => I18N[lang][k] ?? k;
  const L = (o) => (o && typeof o === "object" ? (o[lang] || o.zh || o.en || "") : o || "");

  // ------------------------------------------------------------ formatting
  function fmtDate(iso) {
    const d = new Date(iso + "T12:00:00");
    return lang === "zh"
      ? d.toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long" })
      : d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  }
  function readMinutes(ed) {
    let n = 0;
    for (const s of [...ed.sections.ai, ...ed.sections.world]) n += (L(s.story) + L(s.why) + L(s.pro)).length;
    for (const q of ed.quick_hits) n += L(q.line).length;
    return Math.max(1, Math.round(lang === "zh" ? n / 450 : n / 5.6 / 230));
  }
  const paras = (s) => L(s).split(/\n\s*\n|\n/).map((p) => p.trim()).filter(Boolean);
  // Chinese headlines: keep each clause together so lines break at punctuation.
  const clauses = (s) => lang === "zh"
    ? esc(s).split(/(?<=[，、：；！？])/).map((c) => `<span class="cl">${c}</span>`).join("")
    : esc(s);
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };

  // ------------------------------------------------------------ static text
  function applyStatic() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    document.querySelectorAll(".lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === lang));
  }

  // ------------------------------------------------------------ render
  const ICON_SPEAK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 8.5a5 5 0 0 1 0 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';

  function storyHTML(s, i, desk) {
    const id = `${desk}-${i + 1}`;
    const hasStat = s.stat && s.stat.value;
    const lead = s.importance >= 3;
    const terms = (s.terms || []).filter((x) => L(x.term));
    return `<article class="story${lead ? " lead" : ""}" id="${id}" data-id="${id}">
      <aside class="s-side">
        <span class="num">${i + 1}</span>
        ${L(s.tag) ? `<span class="tag">${esc(L(s.tag))}</span>` : ""}
        ${lead ? `<span class="lead-badge">${t("lead")}</span>` : ""}
        ${hasStat ? `<div class="stat"><div class="v">${esc(s.stat.value)}</div><div class="l">${esc(L(s.stat.label))}</div></div>` : ""}
        <button class="speak" type="button" data-speak="${id}" title="${t("listenStory")}" aria-label="${t("listenStory")}">${ICON_SPEAK}<span>${t("listenShort")}</span></button>
      </aside>
      <div class="s-main">
        <h3>${clauses(L(s.title))}</h3>
        <p class="hook">${esc(L(s.hook))}</p>
        <div class="body">${paras(s.story).map((p) => `<p>${esc(p)}</p>`).join("")}</div>
        ${L(s.why) ? `<div class="why"><span class="lbl">${t("why")}</span><p>${esc(L(s.why))}</p></div>` : ""}
        ${L(s.pro) ? `<details class="pro"><summary><span class="lbl">${t("pro")}</span><span class="chev">+</span></summary><div class="pro-body"><p>${esc(L(s.pro))}</p></div></details>` : ""}
        ${terms.length ? `<div class="terms"><span class="terms-lbl">${t("terms")}</span>${terms.map((x, k) => `<button type="button" class="term" data-term="${id}-${k}">${esc(L(x.term))}</button>`).join("")}<p class="term-explain" hidden></p></div>` : ""}
        ${(s.sources || []).length ? `<div class="sources"><span class="lbl">${t("sources")}</span>${s.sources.map((src) => `<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer" title="${esc(src.title || "")}">${esc(src.name || host(src.url))}</a>`).join("")}</div>` : ""}
      </div>
    </article>`;
  }

  function render() {
    applyStatic();
    if (!edition) return;
    const ed = edition;
    document.title = `${L(ed.headline)} · Daybreak 破晓日报`;
    $("#npDate").textContent = fmtDate(ed.date);
    $("#topbarDate").textContent = fmtDate(ed.date);
    const n = index ? index.editions.length - index.editions.findIndex((e) => e.date === ed.date) : 0;
    $("#npIssue").textContent = n > 0 && n <= (index?.editions.length || 0) ? I18N[lang].issue(n) : "";
    $("#headline").innerHTML = clauses(L(ed.headline));
    $("#lede").textContent = L(ed.lede);
    const nStories = ed.sections.ai.length + ed.sections.world.length;
    $("#meta").innerHTML = [
      `<span><b>${nStories}</b> ${t("stories")}</span>`,
      `<span><b>${ed.quick_hits.length}</b> ${t("quickN")}</span>`,
      `<span><b>${readMinutes(ed)}</b> ${t("readMin")}</span>`,
      ed.stats ? `<span><b>${ed.stats.outlets}</b> ${t("outlets")}</span>` : "",
    ].join("");

    const tocCol = (desk, key) => ed.sections[desk].length
      ? `<div><p class="toc-desk">${t(key)}</p><ol>${ed.sections[desk].map((s, i) => `<li><a href="#${desk}-${i + 1}">${esc(L(s.title))}</a></li>`).join("")}</ol></div>`
      : "";
    $("#toc").innerHTML = `<h4>${t("toc")}</h4><div class="toc-cols">${tocCol("ai", "deskAi")}${tocCol("world", "deskWorld")}</div>`;

    for (const desk of ["ai", "world"]) {
      $(`#desk-${desk}`).hidden = !ed.sections[desk].length;
      $(`#stories-${desk}`).innerHTML = ed.sections[desk].map((s, i) => storyHTML(s, i, desk)).join("");
    }
    $("#desk-quick").hidden = !ed.quick_hits.length;
    $("#quick").innerHTML = ed.quick_hits.map((q) => {
      const src = (q.sources || [])[0];
      return `<li><div class="qhead"><span class="qt">${esc(L(q.title))}</span><span class="qs">${esc(I18N[lang].sec[q.section] || "")}</span></div>
        <p class="ql">${esc(L(q.line))}${src ? `<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">${esc(src.name || host(src.url))} ↗</a>` : ""}</p></li>`;
    }).join("");

    const gen = ed.generated_at ? new Date(ed.generated_at) : null;
    $("#fine").textContent = [
      gen ? `${t("generated")} ${gen.toLocaleString(lang === "zh" ? "zh-CN" : "en-GB", { dateStyle: "medium", timeStyle: "short" })}` : "",
      ed.model ? `${t("by")} ${ed.model}` : "",
    ].filter(Boolean).join(" · ");

    const pos = index ? index.editions.findIndex((e) => e.date === ed.date) : -1;
    $("#prevDay").disabled = pos < 0 || pos >= index.editions.length - 1;
    $("#nextDay").disabled = pos <= 0;
    renderArchive();
    reveal();
  }

  function renderArchive() {
    if (!index) return;
    $("#archiveList").innerHTML = index.editions.map((e) => `<li class="${edition && e.date === edition.date ? "cur" : ""}"><a href="#/${e.date}"><span class="ad">${esc(fmtDate(e.date))}</span><span class="ah">${esc(L(e.headline))}</span></a></li>`).join("");
  }

  function showMessage(msg) {
    $("#headline").textContent = msg;
    $("#lede").textContent = "";
    $("#meta").innerHTML = "";
    $("#toc").innerHTML = "";
    for (const id of ["#stories-ai", "#stories-world", "#quick"]) $(id).innerHTML = "";
  }

  // ------------------------------------------------------------ data
  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  async function load() {
    stopSpeech();
    try {
      if (!index) index = await getJSON("data/index.json");
    } catch {
      applyStatic();
      return showMessage(t("failed"));
    }
    const want = (location.hash.match(/\d{4}-\d{2}-\d{2}/) || [])[0] || index.editions[0]?.date;
    if (!want || !index.editions.some((e) => e.date === want)) {
      applyStatic();
      $("#npDate").textContent = want ? fmtDate(want) : "—";
      renderArchive();
      return showMessage(t("empty"));
    }
    try {
      edition = await getJSON(`data/editions/${want}.json`);
    } catch {
      applyStatic();
      return showMessage(t("failed"));
    }
    render();
    if (!/#(ai|world)-/.test(location.hash)) window.scrollTo({ top: 0 });
  }

  // ------------------------------------------------------------ reveal + progress
  let io;
  function reveal() {
    io?.disconnect();
    if (!("IntersectionObserver" in window)) return document.querySelectorAll(".story").forEach((el) => el.classList.add("in"));
    io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { rootMargin: "0px 0px -6% 0px" });
    document.querySelectorAll(".story").forEach((el) => io.observe(el));
  }
  function onScroll() {
    const h = document.documentElement;
    const p = h.scrollTop / Math.max(1, h.scrollHeight - h.clientHeight);
    $("#progress").style.width = `${Math.min(100, p * 100)}%`;
    $(".topbar").classList.toggle("scrolled", h.scrollTop > 200);
  }

  // ------------------------------------------------------------ speech
  const synth = window.speechSynthesis;
  let speakingId = null;
  function pickVoice() {
    const vs = synth?.getVoices() || [];
    const want = lang === "zh" ? /^zh(-|_)?(CN|Hans)?/i : /^en(-|_)?(GB|US)?/i;
    return vs.find((v) => want.test(v.lang) && /natural|premium|enhanced|google/i.test(v.name)) || vs.find((v) => want.test(v.lang)) || null;
  }
  function stopSpeech() {
    if (synth) synth.cancel();
    speakingId = null;
    document.querySelectorAll(".speak.on").forEach((b) => b.classList.remove("on"));
    $("#player").hidden = true;
  }
  function speak(chunks, id, label) {
    if (!synth) return alert(t("noSpeech"));
    stopSpeech();
    speakingId = id;
    const voice = pickVoice();
    $("#playerText").textContent = `${t("reading")} · ${label}`;
    $("#player").hidden = false;
    document.querySelector(`[data-speak="${id}"]`)?.classList.add("on");
    chunks.filter(Boolean).forEach((text, k, arr) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang === "zh" ? "zh-CN" : "en-GB";
      if (voice) u.voice = voice;
      u.rate = lang === "zh" ? 1.0 : 0.98;
      if (k === arr.length - 1) u.onend = () => { if (speakingId === id) stopSpeech(); };
      synth.speak(u);
    });
  }
  const storyChunks = (s) => [L(s.title), ...paras(s.story), `${t("why")}: ${L(s.why)}`];
  function findStory(id) {
    const [desk, n] = id.split("-");
    return edition?.sections[desk]?.[Number(n) - 1];
  }

  // ------------------------------------------------------------ events
  document.addEventListener("click", (e) => {
    const langBtn = e.target.closest(".lang button");
    if (langBtn) {
      lang = langBtn.dataset.lang; store.set("daybreak.lang", lang); stopSpeech();
      const y = window.scrollY;
      render();
      document.querySelectorAll(".story").forEach((el) => el.classList.add("in"));
      window.scrollTo({ top: y, behavior: "instant" });
      if (!edition) applyStatic();
      return;
    }

    const sp = e.target.closest("[data-speak]");
    if (sp) {
      const id = sp.dataset.speak;
      if (speakingId === id) return stopSpeech();
      const s = findStory(id);
      if (s) speak(storyChunks(s), id, L(s.title));
      return;
    }

    const term = e.target.closest("[data-term]");
    if (term) {
      const [desk, n, k] = term.dataset.term.split("-");
      const x = edition.sections[desk][Number(n) - 1].terms[Number(k)];
      const box = term.parentElement.querySelector(".term-explain");
      const open = term.classList.contains("on");
      term.parentElement.querySelectorAll(".term").forEach((b) => b.classList.remove("on"));
      if (open) { box.hidden = true; return; }
      term.classList.add("on");
      box.innerHTML = `<b>${esc(L(x.term))}</b> — ${esc(L(x.explain))}`;
      box.hidden = false;
      return;
    }
  });

  $("#listenAll").addEventListener("click", () => {
    if (!edition) return;
    if (speakingId === "all") return stopSpeech();
    const chunks = [L(edition.headline), L(edition.lede)];
    for (const desk of ["ai", "world"]) {
      chunks.push(t(desk === "ai" ? "deskAi" : "deskWorld"));
      for (const s of edition.sections[desk]) chunks.push(...storyChunks(s));
    }
    speak(chunks, "all", L(edition.headline));
  });
  $("#playerStop").addEventListener("click", stopSpeech);

  const sheet = $("#archive");
  $("#archiveBtn").addEventListener("click", () => { renderArchive(); sheet.hidden = false; });
  $("#closeArchive").addEventListener("click", () => { sheet.hidden = true; });
  sheet.addEventListener("click", (e) => { if (e.target === sheet || e.target.closest("#archiveList a")) sheet.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { sheet.hidden = true; } });

  function step(dir) {
    if (!index || !edition) return;
    const pos = index.editions.findIndex((x) => x.date === edition.date);
    const next = index.editions[pos + dir];
    if (next) location.hash = `#/${next.date}`;
  }
  $("#prevDay").addEventListener("click", () => step(1));
  $("#nextDay").addEventListener("click", () => step(-1));

  window.addEventListener("hashchange", () => {
    const d = (location.hash.match(/\d{4}-\d{2}-\d{2}/) || [])[0];
    if (d && (!edition || d !== edition.date)) load();
  });
  window.addEventListener("scroll", onScroll, { passive: true });
  if (synth) synth.onvoiceschanged = () => {};

  applyStatic();
  load();
})();
