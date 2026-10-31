import { attachDirectSave } from "./directsave.js";
import { destroyDetachedEditors, initEditor } from "./editor.js";
import { initPicker } from "./picker.js";

const started = new WeakSet();

function within(root, selector) {
  const found = [...root.querySelectorAll(selector)];
  return root.matches(selector) ? [root, ...found] : found;
}

function activate(root) {
  for (const element of within(root, "[data-editor]")) {
    if (started.has(element)) continue;
    started.add(element);
    initEditor(element);
    attachDirectSave(element);
  }
  within(root, "[data-embed-picker]").forEach(initPicker);
}

function scrollToAnchor() {
  // O texto só existe depois que o editor monta, e o navegador já procurou o trecho antes disso.
  const target = window.location.hash && document.getElementById(window.location.hash.slice(1));
  if (target) target.scrollIntoView();
}

function start() {
  activate(document.body);
  scrollToAnchor();
  document.body.addEventListener("htmx:afterSwap", (event) => {
    destroyDetachedEditors();
    activate(event.detail.target);
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
