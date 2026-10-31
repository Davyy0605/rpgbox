// Menu "Deletar": botão direito no computador, toque longo no celular.
import { csrfToken } from "./autosave.js";
import { notice } from "./notice.js";

const HOLD_MS = 500;
const MOVE_PX = 10;
const EDGE_PX = 8;

const FAILED = "Não foi possível deletar. Verifique a conexão e tente de novo.";
const SESSION = "Sessão expirada. Entre de novo para deletar.";

let menu = null;
let button = null;
let current = null;
let returnFocus = null;
let press = null;
// Lido antes do clique: no Mac, o botão direito já seleciona a palavra embaixo do cursor.
let hadSelection = false;

function itemAt(target) {
  if (hadSelection || target.closest?.("input, textarea, select, [contenteditable]")) return null;
  return target.closest?.("[data-delete-url]") ?? null;
}

function close() {
  if (!current) return;
  current = null;
  menu.hidden = true;
  returnFocus?.focus?.({ preventScroll: true });
  returnFocus = null;
}

function open(item, x, y) {
  returnFocus = current ? returnFocus : document.activeElement;
  current = item;
  menu.hidden = false;
  const { width, height } = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(EDGE_PX, Math.min(x, window.innerWidth - width - EDGE_PX))}px`;
  menu.style.top = `${Math.max(EDGE_PX, Math.min(y, window.innerHeight - height - EDGE_PX))}px`;
  button.focus({ preventScroll: true });
}

function neighbour(item) {
  const sibling = item.nextElementSibling ?? item.previousElementSibling;
  return sibling?.matches("a, button, summary") ? sibling : sibling?.querySelector("a, button, summary");
}

function closeSheetOf(item) {
  const sheet = document.querySelector("[data-sheet]");
  const panel = sheet?.dataset.panelSrc.split("?")[0];
  if (panel && item.querySelector(`[data-panel-url="${panel}"]`)) sheet.querySelector("[data-sheet-close]").click();
}

// Só sai da tela com a confirmação do servidor: login e página de espera também respondem 200.
async function confirmed(url) {
  const response = await fetch(url, {
    method: "POST",
    headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
  });
  if (response.redirected) throw new Error(SESSION);
  const data = await response.json().catch(() => null);
  return response.ok && data?.deleted === true;
}

async function remove(item) {
  if (item.getAttribute("aria-busy") === "true") return;
  item.setAttribute("aria-busy", "true");
  let message = FAILED;
  let done = false;
  try {
    done = await confirmed(item.dataset.deleteUrl);
  } catch (error) {
    if (error.message === SESSION) message = SESSION;
  }
  if (!done) {
    item.removeAttribute("aria-busy");
    notice(message);
    return;
  }
  if (item.dataset.deleteGo) {
    // A página aberta deixou de existir; replace para o voltar não cair nela.
    window.location.replace(item.dataset.deleteGo);
    return;
  }
  closeSheetOf(item);
  const next = neighbour(item);
  item.remove();
  next?.focus({ preventScroll: true });
}

function cancelPress() {
  clearTimeout(press?.timer);
  press = null;
}

function onContextMenu(event) {
  const item = itemAt(event.target);
  if (!item) return;
  event.preventDefault();
  if (press) {
    clearTimeout(press.timer);
    press.held = true;
  }
  open(item, event.clientX, event.clientY);
}

function onTouchStart(event) {
  cancelPress();
  const item = event.touches.length === 1 ? itemAt(event.target) : null;
  if (!item) return;
  const { clientX: x, clientY: y } = event.touches[0];
  press = { x, y, held: false, timer: setTimeout(() => {
    press.held = true;
    open(item, x, y);
  }, HOLD_MS) };
}

function onTouchMove(event) {
  if (!press || press.held) return;
  const { clientX, clientY } = event.touches[0];
  if (Math.hypot(clientX - press.x, clientY - press.y) > MOVE_PX) cancelPress();
}

function onTouchEnd(event) {
  // Sem isto, soltar o dedo depois do toque longo seguiria o link embaixo.
  if (press?.held && event.cancelable) event.preventDefault();
  cancelPress();
}

function onScroll() {
  cancelPress();
  close();
}

function onPointerDown(event) {
  hadSelection = !(window.getSelection()?.isCollapsed ?? true);
  if (current && !menu.contains(event.target)) close();
}

function onKeyDown(event) {
  if (event.key !== "Escape" || !current) return;
  event.stopPropagation(); // o Esc é do menu, não do painel aberto atrás dele
  close();
}

export function initDelete() {
  menu = document.createElement("div");
  menu.className = "delete-menu";
  menu.setAttribute("role", "menu");
  menu.hidden = true;
  button = document.createElement("button");
  button.type = "button";
  button.setAttribute("role", "menuitem");
  button.textContent = "Deletar";
  button.addEventListener("click", () => {
    const item = current;
    returnFocus = null;
    close();
    remove(item);
  });
  menu.append(button);
  document.body.append(menu);
  document.addEventListener("contextmenu", onContextMenu);
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("scroll", onScroll, { capture: true, passive: true });
  document.addEventListener("touchstart", onTouchStart, { passive: true });
  document.addEventListener("touchmove", onTouchMove, { passive: true });
  document.addEventListener("touchend", onTouchEnd, { passive: false });
  document.addEventListener("touchcancel", cancelPress);
}
