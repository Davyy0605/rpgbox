import { Editor } from "@tiptap/core";
import Link from "@tiptap/extension-link";
import { Placeholder } from "@tiptap/extensions";
import StarterKit from "@tiptap/starter-kit";

import { AnchoredHeading } from "./heading.js";
import { mentionExtension } from "./mention.js";
import { attachToolbar } from "./toolbar.js";

const editors = new Map();

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

function readDoc(element) {
  const source = document.getElementById(element.dataset.doc);
  const doc = source ? JSON.parse(source.textContent) : null;
  // Bloco recém-criado: um documento sem nós não é válido para o editor.
  return doc?.content?.length ? doc : undefined;
}

function readMissing(element) {
  return new Set((element.dataset.missing ?? "").split(",").filter(Boolean).map(Number));
}

export function initEditor(element) {
  if (editors.has(element)) return editors.get(element);
  const editor = new Editor({
    element,
    content: readDoc(element),
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
