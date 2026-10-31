// Trocas de trecho por htmx: avisa quando falham e deixa o foco num lugar útil.
import { notice } from "./notice.js";

const FAILED = "Não foi possível concluir. Verifique a conexão e tente de novo.";

let kept = null;

const isPost = (event) => event.detail.requestConfig?.verb === "post";

function hiddenValues(form) {
  return [...form.querySelectorAll("input[type=hidden]:not([name=csrfmiddlewaretoken])")].map((input) => input.value).join();
}

function remember(submitted) {
  const active = document.activeElement;
  const inside = active?.closest?.("form");
  const form = inside ?? submitted.closest?.("form");
  if (!form) return null;
  return {
    action: form.getAttribute("action"),
    hidden: hiddenValues(form),
    tag: inside ? active.tagName : "BUTTON",
    // Quem já digitava em outro campo enquanto a resposta vinha não pode perder o texto.
    typed: inside && form !== submitted && active.tagName === "INPUT" ? active.value : null,
  };
}

function restore(target) {
  const state = kept;
  kept = null;
  if (!state || document.activeElement !== document.body || !target.isConnected) return;
  const form = [...target.querySelectorAll("form")]
    .find((f) => f.getAttribute("action") === state.action && hiddenValues(f) === state.hidden);
  const control = form?.querySelector(state.tag === "INPUT" ? "input:not([type=hidden])" : state.tag.toLowerCase());
  if (control && state.typed !== null) control.value = state.typed;
  control?.focus({ preventScroll: true });
  if (document.activeElement === document.body) {
    target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }
}

function onBeforeSwap(event) {
  const { detail } = event;
  if (!isPost(event) || !detail.shouldSwap) return;
  if (/^\s*<(!doctype|html)/i.test(detail.serverResponse)) {
    // Os trechos nunca são página inteira: é a tela de login ou o aviso de quem hospeda o site.
    detail.shouldSwap = false;
    if (new URL(detail.xhr.responseURL).pathname.startsWith("/entrar")) window.location.reload();
    else notice(FAILED);
    return;
  }
  kept = remember(detail.requestConfig.elt);
}

function onError(event) {
  if (isPost(event)) notice(FAILED);
}

export function initSwaps() {
  document.body.addEventListener("htmx:beforeSwap", onBeforeSwap);
  document.body.addEventListener("htmx:afterSettle", (event) => restore(event.detail.target));
  document.body.addEventListener("htmx:responseError", onError);
  document.body.addEventListener("htmx:sendError", onError);
}
