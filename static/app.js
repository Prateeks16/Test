/* OTP Extractor dashboard — vanilla JS, no build step. */
(function () {
  "use strict";

  const HKEY = "otp_history";
  const API = (window.OTP_CONFIG && window.OTP_CONFIG.apiBase) || "";  // "" = same-origin
  const $ = (id) => document.getElementById(id);

  // ---- state ----
  let selectedFile = null;

  // ---- elements ----
  const drop = $("drop");
  const fileInput = $("file");
  const preview = $("preview");
  const previewImg = $("previewImg");
  const fileBox = $("fileBox");
  const fname = $("fname");
  const fsize = $("fsize");
  const extractBtn = $("extractBtn");
  const result = $("result");
  const resultLabel = $("resultLabel");
  const otpEl = $("otp");
  const copyBtn = $("copyBtn");
  const cands = $("cands");
  const chips = $("chips");
  const metaRow = $("metaRow");

  // ---- history persistence ----
  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HKEY)) || []; }
    catch (_) { return []; }
  }
  function saveHistory(list) {
    localStorage.setItem(HKEY, JSON.stringify(list.slice(0, 200)));
  }
  function addEntry(entry) {
    const list = loadHistory();
    list.unshift(entry);
    saveHistory(list);
    render();
  }

  // ---- helpers ----
  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }
  function timeAgo(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  }
  function fmtTime(ts) {
    return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  let toastTimer;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 1600);
  }

  function fileIcon(type) {
    return type === "pdf"
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/></svg>';
  }

  // ---- stats + lists rendering ----
  function render() {
    const list = loadHistory();
    const ok = list.filter((e) => e.status === "ok");
    const attempts = list.length;

    $("statTotal").textContent = ok.length;
    if (attempts === 0) {
      $("statRate").textContent = "—";
      $("statRateSub").textContent = "no attempts yet";
      $("statAvg").textContent = "—";
    } else {
      $("statRate").textContent = Math.round((ok.length / attempts) * 100) + "%";
      $("statRateSub").textContent = ok.length + " of " + attempts + " uploads";
      if (ok.length) {
        const avg = ok.reduce((a, e) => a + (e.ms || 0), 0) / ok.length;
        $("statAvg").textContent = avg < 1000 ? Math.round(avg) + " ms" : (avg / 1000).toFixed(1) + " s";
      } else {
        $("statAvg").textContent = "—";
      }
    }

    // recent (dashboard)
    const recent = $("recentBody");
    if (!list.length) {
      recent.innerHTML = emptyState("No extractions yet", "Upload a file to see it here.");
    } else {
      recent.innerHTML = list.slice(0, 5).map((e) => `
        <div class="recent-item">
          <div class="ri-l">
            ${statusPill(e.status)}
            <span class="fn" title="${esc(e.name)}">${esc(e.name)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:12px">
            <span class="mono">${e.status === "ok" ? esc(e.otp) : "—"}</span>
            <span class="ts">${timeAgo(e.ts)}</span>
          </div>
        </div>`).join("");
    }

    // history table
    const body = $("historyBody");
    if (!list.length) {
      body.innerHTML = `<tr><td colspan="5">${emptyState("No history", "Extractions you run will be listed here.")}</td></tr>`;
    } else {
      body.innerHTML = list.map((e) => `
        <tr>
          <td style="color:var(--muted)">${fmtTime(e.ts)}</td>
          <td><span class="ftype">${fileIcon(e.type)}<span title="${esc(e.name)}">${esc(e.name)}</span></span></td>
          <td class="mono">${e.status === "ok" ? esc(e.otp) : '<span style="color:var(--muted-2)">—</span>'}</td>
          <td>${statusPill(e.status, true)}</td>
          <td style="color:var(--muted)">${e.ms != null ? e.ms + " ms" : "—"}</td>
        </tr>`).join("");
    }
  }

  function statusPill(status, label) {
    const map = {
      ok: ["ok", "Success"],
      none: ["none", "No code"],
      err: ["err", "Error"],
    };
    const [cls, text] = map[status] || map.err;
    return `<span class="pill ${cls}"><span class="d"></span>${label ? text : ""}</span>`;
  }
  function emptyState(title, sub) {
    return `<div class="empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
      <div style="font-weight:600;color:var(--muted)">${title}</div>
      <div style="font-size:12.5px">${sub}</div>
    </div>`;
  }

  // ---- file selection ----
  function setFile(file) {
    selectedFile = file;
    result.style.display = "none";
    fname.textContent = file.name;
    fsize.textContent = fmtSize(file.size);
    if (file.type.startsWith("image/")) {
      previewImg.src = URL.createObjectURL(file);
      previewImg.style.display = "block";
      fileBox.style.display = "none";
    } else {
      previewImg.style.display = "none";
      fileBox.style.display = "grid";
    }
    preview.style.display = "flex";
    extractBtn.disabled = false;
  }

  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("drag"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    if (e.dataTransfer.files.length) { fileInput.files = e.dataTransfer.files; setFile(e.dataTransfer.files[0]); }
  });
  fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

  // ---- extract ----
  extractBtn.addEventListener("click", async () => {
    if (!selectedFile) return;
    const file = selectedFile;
    const type = file.name.toLowerCase().endsWith(".pdf") ? "pdf" : "image";
    extractBtn.disabled = true;
    extractBtn.innerHTML = '<span class="spinner"></span> Extracting…';
    result.style.display = "none";

    const fd = new FormData();
    fd.append("file", file);
    let data = {}, okResp = false;
    try {
      const res = await fetch(API + "/extract", { method: "POST", body: fd });
      data = await res.json();
      okResp = res.ok;
    } catch (_) {
      data = { error: "Request failed — is the server running?" };
    }

    if (okResp && data.otp) {
      showResult(true, data);
      addEntry({ name: file.name, type, status: "ok", otp: data.otp, ms: data.ms ?? null, ts: Date.now() });
    } else {
      const noCode = /no otp/i.test(data.error || "");
      showResult(false, data);
      addEntry({ name: file.name, type, status: noCode ? "none" : "err", otp: null, ms: data.ms ?? null, ts: Date.now() });
    }

    extractBtn.disabled = false;
    extractBtn.textContent = "Extract OTP";
  });

  function showResult(success, data) {
    result.className = "result " + (success ? "ok" : "err");
    if (success) {
      resultLabel.textContent = "Detected OTP";
      otpEl.textContent = data.otp;
      copyBtn.style.display = "inline-flex";

      const list = Array.isArray(data.candidates) ? data.candidates : [];
      if (list.length > 1) {
        chips.innerHTML = list.map((c) =>
          `<span class="chip ${c === data.otp ? "picked" : ""}">${esc(c)}</span>`).join("");
        cands.style.display = "block";
      } else {
        cands.style.display = "none";
      }

      const bits = [];
      if (data.ms != null) bits.push(`<span>Read in <b>${data.ms} ms</b></span>`);
      if (list.length) bits.push(`<span><b>${list.length}</b> candidate${list.length > 1 ? "s" : ""} scanned</span>`);
      if (data.rejected && data.rejected.length) bits.push(`<span><b>${data.rejected.length}</b> decoy${data.rejected.length > 1 ? "s" : ""} rejected</span>`);
      metaRow.innerHTML = bits.join("");
      metaRow.style.display = bits.length ? "flex" : "none";
    } else {
      resultLabel.textContent = "Error";
      otpEl.textContent = data.error || "Something went wrong";
      copyBtn.style.display = "none";
      cands.style.display = "none";
      metaRow.style.display = "none";
    }
    result.style.display = "block";
  }

  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(otpEl.textContent);
    toast("Copied " + otpEl.textContent);
  });

  // ---- clear history ----
  $("clearBtn").addEventListener("click", () => {
    if (!loadHistory().length) { toast("History already empty"); return; }
    localStorage.removeItem(HKEY);
    render();
    toast("History cleared");
  });

  // ---- inspector ----
  const idrop = $("idrop"), ifile = $("ifile"), inspectBtn = $("inspectBtn");
  let inspFile = null, inspImg = null;

  function setInspFile(file) {
    inspFile = file;
    inspImg = new Image();
    inspImg.src = URL.createObjectURL(file);
    inspectBtn.disabled = false;
    idrop.querySelector("strong").textContent = file.name;
  }
  idrop.addEventListener("dragover", (e) => { e.preventDefault(); idrop.classList.add("drag"); });
  idrop.addEventListener("dragleave", () => idrop.classList.remove("drag"));
  idrop.addEventListener("drop", (e) => {
    e.preventDefault(); idrop.classList.remove("drag");
    if (e.dataTransfer.files.length) { ifile.files = e.dataTransfer.files; setInspFile(e.dataTransfer.files[0]); }
  });
  ifile.addEventListener("change", () => { if (ifile.files.length) setInspFile(ifile.files[0]); });

  inspectBtn.addEventListener("click", async () => {
    if (!inspFile) return;
    inspectBtn.disabled = true;
    inspectBtn.innerHTML = '<span class="spinner"></span> Inspecting…';
    const fd = new FormData(); fd.append("file", inspFile);
    try {
      const res = await fetch(API + "/inspect", { method: "POST", body: fd });
      const data = await res.json();
      if (res.ok) renderInspector(data);
      else toast(data.error || "Inspect failed");
    } catch (_) { toast("Request failed"); }
    inspectBtn.disabled = false;
    inspectBtn.textContent = "Run inspector";
  });

  function drawWithImage(cb) {
    if (inspImg.complete && inspImg.naturalWidth) cb();
    else inspImg.onload = cb;
  }

  function renderInspector(s) {
    $("inspectOut").style.display = "block";
    drawWithImage(() => { drawOriginal(s); drawStrip(s); });

    renderPred("full", s.full, s.final.otp);
    renderPred("crop", s.cropped, s.final.otp);

    $("finalOtp").textContent = s.final.otp || "No code found";
    const v = $("verdict");
    const cropWon = s.cropped.otp && s.cropped.otp === s.final.otp && s.full.otp !== s.final.otp;
    const agree = s.full.otp && s.cropped.otp && s.full.otp === s.cropped.otp;
    if (!s.arrow) { v.className = "insp-verdict none"; v.textContent = "No green arrow detected — full-image prediction only."; }
    else if (cropWon) { v.className = "insp-verdict win"; v.textContent = "✓ Cropping recovered a code the full image got wrong."; }
    else if (agree) { v.className = "insp-verdict same"; v.textContent = "Both stages agree — high confidence."; }
    else { v.className = "insp-verdict same"; v.textContent = "Merged from both stages."; }

    $("cropDesc").textContent = s.arrow
      ? `Arrow at row y≈${Math.round(s.arrow.cy)} → band ${s.band.top}–${s.band.bottom}px`
      : "No green arrow found in this image";
    $("cropNote").innerHTML = s.arrow ? "" : '<span style="color:var(--muted-2)">Cropping not applicable</span>';
  }

  function renderPred(prefix, pred, finalOtp) {
    $(prefix + "Otp").textContent = pred.otp || "—";
    const chipsEl = $(prefix + "Chips");
    const list = pred.candidates || [];
    chipsEl.innerHTML = list.length
      ? list.map((c) => `<span class="chip ${c === pred.otp ? "picked" : ""}">${esc(c)}</span>`).join("")
      : '<span style="color:var(--muted-2);font-size:12.5px">no digits read</span>';
    const card = $(prefix === "full" ? "predFull" : "predCrop");
    card.classList.toggle("hit", !!pred.otp && pred.otp === finalOtp);
    card.classList.toggle("miss", !pred.otp || pred.otp !== finalOtp);
  }

  function drawOriginal(s) {
    const c = $("origCanvas"), maxW = 360;
    const scale = Math.min(1, maxW / s.width);
    c.width = s.width * scale; c.height = s.height * scale;
    const ctx = c.getContext("2d");
    ctx.drawImage(inspImg, 0, 0, c.width, c.height);
    if (s.band) {
      ctx.fillStyle = "rgba(79,70,229,0.12)";
      ctx.fillRect(0, s.band.top * scale, c.width, (s.band.bottom - s.band.top) * scale);
      ctx.strokeStyle = "#4f46e5"; ctx.lineWidth = 1.5;
      ctx.strokeRect(0, s.band.top * scale, c.width, (s.band.bottom - s.band.top) * scale);
    }
    if (s.arrow) {
      ctx.strokeStyle = "#15a34a"; ctx.lineWidth = 2;
      ctx.strokeRect(s.arrow.x * scale, s.arrow.y * scale, s.arrow.w * scale, s.arrow.h * scale);
    }
  }

  function drawStrip(s) {
    const c = $("cropCanvas");
    if (!s.band) { c.width = 0; c.height = 0; return; }
    const bh = s.band.bottom - s.band.top, maxW = 360;
    const scale = Math.min(1, maxW / s.width);
    c.width = s.width * scale; c.height = bh * scale;
    const ctx = c.getContext("2d");
    ctx.drawImage(inspImg, 0, s.band.top, s.width, bh, 0, 0, c.width, c.height);
  }

  // ---- nav ----
  const titles = {
    dashboard: ["Dashboard", "Drop an OTP screenshot or PDF — the code is read automatically."],
    inspect: ["Inspector", "Crop and predict as separate stages — see how they differ."],
    history: ["History", "Every extraction you've run on this device."],
    docs: ["API & Docs", "How the extractor works and how to call it directly."],
  };
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.view;
      document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.dataset.view === view));
      $("pageTitle").textContent = titles[view][0];
      $("pageSub").textContent = titles[view][1];
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  render();
})();
