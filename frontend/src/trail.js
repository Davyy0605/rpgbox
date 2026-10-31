const SEPARATOR = " › ";
const MAX_LEVELS = 3;

let nav = null;
let plainCrumbs = "";

function storageKey() {
  return `rpgbox-trail-${document.body.dataset.campaign ?? ""}`;
}

// O armazenamento pode vir corrompido: só valem rótulo e caminho interno, nunca link para fora.
function isItem(item) {
  return typeof item?.label === "string" && typeof item?.url === "string" && /^\/(?![/\\])/.test(item.url);
}

function read() {
  try {
    const items = JSON.parse(sessionStorage.getItem(storageKey()));
    return Array.isArray(items) ? items.filter(isItem) : [];
  } catch {
    return [];
  }
}

function write(items) {
  try {
    sessionStorage.setItem(storageKey(), JSON.stringify(items));
  } catch {
    // Sem armazenamento, o caminho vale só para esta página.
  }
}

function visit(items, label, url) {
  const known = items.findIndex((item) => item.url === url);
  const kept = known === -1 ? items : items.slice(0, known);
  return [...kept, { label, url }];
}

function render(items) {
  if (items.length < 2) {
    nav.innerHTML = plainCrumbs;
    return;
  }
  nav.replaceChildren();
  const shown = items.slice(-MAX_LEVELS);
  if (shown.length < items.length) nav.append(`…${SEPARATOR}`);
  shown.forEach((item, index) => {
    if (index > 0) nav.append(SEPARATOR);
    const current = index === shown.length - 1;
    const part = document.createElement(current ? "span" : "a");
    part.textContent = item.label;
    if (current) part.setAttribute("aria-current", "page");
    else part.href = item.url;
    nav.append(part);
  });
  nav.scrollLeft = nav.scrollWidth;
}

// O painel aberto vem antes da página: é o lugar onde o mestre está.
export function refreshTrail() {
  const here = document.querySelector("[data-sheet][data-crumb]") ?? document.querySelector("main[data-crumb]");
  if (!nav || !here) return;
  const items = visit(read(), here.dataset.crumb, here.dataset.crumbUrl);
  write(items);
  render(items);
}

export function initTrail() {
  nav = document.querySelector("[data-trail]");
  plainCrumbs = nav?.innerHTML ?? "";
  try {
    refreshTrail();
  } catch (error) {
    // O caminho é acessório: um erro aqui não pode impedir o painel de iniciar.
    console.error(error);
  }
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) refreshTrail();
  });
}
