import { Editor } from "@tiptap/core";
import Link from "@tiptap/extension-link";
import { Placeholder } from "@tiptap/extensions";
import StarterKit from "@tiptap/starter-kit";
import { Color, TextStyle } from "@tiptap/extension-text-style";

import { AnchoredHeading } from "./heading.js";
import { mentionExtension } from "./mention.js";
import { attachToolbar } from "./toolbar.js";

const editors = new Map();
const unreadable = new WeakSet();

// Mesma regra de safe_href em content/doc.py: outro endereço faria o servidor recusar o texto todo.
function safeHref(href) {
  if (typeof href !== "string" || /[\s\x00-\x20\x7f-\x9f]/.test(href)) return false;
  if (!/^(https?:\/\/[^/?#]|mailto:[^?#])/i.test(href)) return false;
  try {
    return Boolean(new URL(href));
  } catch {
    return false;
  }
}

function storedDoc(element) {
  const source = document.getElementById(element.dataset.doc);
  return source ? JSON.parse(source.textContent) : null;
}

// Bloco recém-criado: um documento sem nós não é válido para o editor.
function readDoc(element) {
  const doc = storedDoc(element);
  return doc?.content?.length ? doc : undefined;
}

// Texto corrido de um documento, mesmo de um que o editor não abre.
export function docText(node) {
  if (!node || typeof node !== "object") return "";
  if (typeof node.text === "string") return node.text;
  if (node.type === "mention") return node.attrs?.label ?? "";
  const parts = Array.isArray(node.content) ? node.content.map(docText) : [];
  return parts.join(["doc", "bulletList", "orderedList"].includes(node.type) ? "\n" : "");
}

// Sem salvar nada: o conteúdo mostrado pelo editor seria só o que sobrou, e sobrescreveria o texto guardado.
function showUnreadable(element, editor) {
  editor.setEditable(false, false);
  element.hidden = true;
  const note = document.createElement("div");
  note.className = "unreadable";
  note.setAttribute("role", "alert");
  const message = document.createElement("p");
  message.textContent = "Este texto não abriu no editor. Ele segue guardado, sem nenhuma alteração.";
  const text = document.createElement("p");
  text.textContent = docText(storedDoc(element));
  note.append(message, text);
  element.after(note);
  unreadable.add(editor);
}

export function isUnreadable(editor) {
  return unreadable.has(editor);
}

function readMissing(element) {
  return new Set((element.dataset.missing ?? "").split(",").filter(Boolean).map(Number));
}

export function initEditor(element) {
  if (editors.has(element)) return editors.get(element);
  let contentFailed = false;
  const editor = new Editor({
    element,
    content: readDoc(element),
    enableContentCheck: true,
    onContentError() {
      contentFailed = true;
    },
    extensions: [
      StarterKit.configure({
        heading: false,
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        link: false,
        strike: false,
        trailingNode: false,
        underline: false,
      }),
      AnchoredHeading.configure({ levels: [2, 3] }),
      Link.configure({
        defaultProtocol: "https",
        HTMLAttributes: { target: "_blank", rel: "noopener noreferrer nofollow", class: null },
        isAllowedUri: safeHref,
      }),
      TextStyle,
      Color,
      mentionExtension({ suggestUrl: element.dataset.suggestUrl, missing: readMissing(element) }),
      Placeholder.configure({ placeholder: "Escreva aqui. Use @ para citar." }),
    ],
    editorProps: {
      attributes: { role: "textbox", "aria-multiline": "true", "aria-label": element.dataset.label || "Texto" },
      // Espaço para o cursor não ficar sob a barra de formatação.
      scrollMargin: 72,
      scrollThreshold: 72,
    },
    onUpdate({ editor: changed }) {
      element.dispatchEvent(new CustomEvent("editor:change", { bubbles: true, detail: { doc: changed.getJSON() } }));
    },
  });
  if (contentFailed) showUnreadable(element, editor);
  attachToolbar(editor);
  editors.set(element, editor);
  return editor;
}

export function destroyDetachedEditors() {
  for (const [element, editor] of editors) {
    if (!element.isConnected) {
      editor.destroy();
      editors.delete(element);
    }
  }
}
