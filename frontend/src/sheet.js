import { refreshTrail } from "./trail.js";

const DESKTOP = "(min-width: 900px)";
const DRAG_START_PX = 8;
const DRAG_CLOSE_PX = 96;
const DRAG_FLICK_PX_PER_MS = 0.6;
const SLIDE_MS = 160;

let host = null;
let opener = null;
let wanted = null;
const loaded = new Map();

const sheet = () => host.querySelector("[data-sheet]");
const depth = () => history.state?.sheet ?? 0;

function panelPageUrl(record, anchor) {
  const url = new URL(window.location.href);
  url.hash = "";
  url.searchParams.set("painel", record);
  if (anchor) url.searchParams.set("ancora", anchor);
  else url.searchParams.delete("ancora");
  return url;
}

function basePageUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete("painel");
  url.searchParams.delete("ancora");
  return url;
}

function emptySheet(panel, title, rising) {
  const shell = document.createElement("section");
  shell.className = rising ? "sheet rising" : "sheet";
  shell.dataset.sheet = "";
  shell.dataset.panelSrc = panel;
  shell.tabIndex = -1;
  shell.setAttribute("aria-label", title);
  shell.setAttribute("aria-busy", "true");
  shell.innerHTML = `<div class="sheet-grip" aria-hidden="true"></div>
    <div class="sheet-head"><h2></h2>
    <button class="plus sheet-close" type="button" data-sheet-close aria-label="Fechar">×</button></div>`;
  shell.querySelector("h2").textContent = title;
  return shell;
}

function settled() {
  sheet()?.focus({ preventScroll: true });
  refreshTrail();
}

function stopLoading() {
  wanted = null;
  htmx.trigger(host, "htmx:abort");
}

function fail() {
  const current = sheet();
  if (!current || !wanted) return;
  wanted = null;
  current.removeAttribute("aria-busy");
  current.insertAdjacentHTML("beforeend", '<p class="muted">Não foi possível abrir.</p>');
}

function show({ panel, title }) {
  stopLoading();
  const rising = !sheet();
  if (loaded.has(panel)) {
    host.innerHTML = loaded.get(panel);
    sheet().classList.toggle("rising", rising);
    settled();
    return;
  }
  // O painel sobe no mesmo instante; o conteúdo chega depois, sem segurar o toque.
  host.replaceChildren(emptySheet(panel, title, rising));
  wanted = panel;
  htmx.ajax("GET", panel, { source: host, target: host, swap: "innerHTML" }).catch(fail);
}

function hide() {
  stopLoading();
  host.replaceChildren();
  refreshTrail();
  opener?.focus?.({ preventScroll: true });
  opener = null;
}

function syncToHistory() {
  const { panel } = history.state ?? {};
  if (!panel) hide();
  else if (sheet()?.dataset.panelSrc !== panel) show(history.state);
}

function dismiss() {
  if (depth()) history.go(-depth());
}

function open(link) {
  const { panelUrl: panel, record, anchor } = link.dataset;
  if (sheet()?.dataset.panelSrc === panel) return;
  document.activeElement?.blur?.();
  const stacking = !sheet() || link.closest("[data-sheet]");
  const entry = { panel, title: link.textContent.trim(), sheet: depth() + (stacking ? 1 : 0) };
  if (stacking) history.pushState(entry, "", panelPageUrl(record, anchor));
  else history.replaceState(entry, "", panelPageUrl(record, anchor));
  if (!opener) opener = link;
  show(entry);
}

function onClick(event) {
  if (event.target.closest?.("[data-sheet-close]")) {
    dismiss();
    return;
  }
  if (event.defaultPrevented || event.button || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const link = event.target.closest?.("[data-panel-url]");
  if (!link) return;
  event.preventDefault();
  // Na tela completa, link para um título leva ao trecho; a consulta rápida fica para o registro.
  if (link.dataset.anchor && !link.closest("[data-sheet]")) window.location.href = link.href;
  else open(link);
}

function initDrag() {
  let start = null;
  let distance = 0;
  host.addEventListener("touchstart", (event) => {
    const current = sheet();
    const atTop = current && current.scrollTop <= 0;
    start = atTop && !window.matchMedia(DESKTOP).matches
      ? { y: event.touches[0].clientY, at: event.timeStamp }
      : null;
    distance = 0;
  }, { passive: true });
  host.addEventListener("touchmove", (event) => {
    if (!start) return;
    const moved = event.touches[0].clientY - start.y;
    if (!distance && moved < DRAG_START_PX) {
      if (moved < 0) start = null;
      return;
    }
    event.preventDefault();
    distance = Math.max(moved, 1);
    sheet().style.transition = "none";
    sheet().style.transform = `translateY(${distance}px)`;
  }, { passive: false });
  const finish = (event) => {
    const current = sheet();
    if (!start || !distance || !current) {
      start = null;
      return;
    }
    const speed = distance / Math.max(event.timeStamp - start.at, 1);
    start = null;
    current.style.transition = "";
    if (event.type === "touchcancel" || (distance < DRAG_CLOSE_PX && speed < DRAG_FLICK_PX_PER_MS)) {
      current.style.transform = "";
      return;
    }
    current.style.transform = "translateY(100%)";
    setTimeout(() => history.back(), SLIDE_MS);
  };
  host.addEventListener("touchend", finish);
  host.addEventListener("touchcancel", finish);
}

function adoptServerPanel() {
  const current = sheet();
  if (!current || depth()) return;
  // Link direto: sem uma entrada embaixo, voltar sairia do site em vez de fechar o painel.
  const url = window.location.href;
  history.replaceState(null, "", basePageUrl());
  history.pushState({ panel: current.dataset.panelSrc, title: current.getAttribute("aria-label"), sheet: 1 }, "", url);
}

function followBareHash() {
  // Link antigo, só com #: o título pode estar em outra aba, e só o servidor sabe qual.
  const params = new URLSearchParams(window.location.search);
  const anchor = window.location.hash.slice(1);
  if (!document.querySelector('main[data-crumb-url^="/r/"]') || !anchor) return;
  if (params.has("trecho") || params.has("aba") || document.getElementById(anchor)) return;
  params.set("trecho", anchor);
  window.location.replace(`?${params}#${anchor}`);
}

export function initSheet() {
  host = document.querySelector("#panel");
  followBareHash();
  document.addEventListener("click", onClick);
  if (!host) return;
  adoptServerPanel();
  initDrag();
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sheet() && !event.target.closest?.("input, [contenteditable]")) dismiss();
  });
  window.addEventListener("popstate", syncToHistory);
  host.addEventListener("htmx:beforeSwap", (event) => {
    const { xhr, serverResponse } = event.detail;
    if (!wanted) {
      event.detail.shouldSwap = false; // o painel foi fechado enquanto a resposta chegava
    } else if (xhr.status === 200 &&!new URL(xhr.responseURL).pathname.endsWith("/painel/")) {
      // Sessão vencida: a resposta é a tela de login, que não cabe no painel.
      window.location.reload();
      event.detail.shouldSwap = false;
    } else if (xhr.status === 200) {
      loaded.set(wanted, serverResponse);
    }
  });
  host.addEventListener("htmx:afterSwap", () => {
    wanted = null;
    settled();
  });
  host.addEventListener("htmx:responseError", fail);
  host.addEventListener("htmx:sendError", fail);
}
