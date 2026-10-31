import { attachAutosave, attachFieldAutosave, draftKey } from "./autosave.js";
import { destroyDetachedEditors, initEditor, isUnreadable } from "./editor.js";
import { initPicker } from "./picker.js";

const started = new WeakSet();

function within(root, selector) {
  const found = [...root.querySelectorAll(selector)];
  return root.matches(selector) ? [root, ...found] : found;
}

function startEditor(element) {
  const editor = initEditor(element);
  if (isUnreadable(editor)) return;
  const { saveUrl, createUrl, key: fieldKey, version, orphanUrl } = element.dataset;
  attachAutosave(editor, {
    element,
    saveUrl,
    createUrl,
    fieldKey,
    version: version === undefined ? null : Number(version),
    draftKey: draftKey(saveUrl ?? createUrl, fieldKey),
    orphanKey: orphanUrl && draftKey(orphanUrl),
  });
}

function activate(root) {
  for (const element of within(root, "[data-editor]")) {
    if (started.has(element)) continue;
    started.add(element);
    startEditor(element);
  }
  for (const input of within(root, "[data-field]")) {
    if (started.has(input)) continue;
    started.add(input);
    attachFieldAutosave(input);
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
