import Heading from "@tiptap/extension-heading";
import { Plugin } from "@tiptap/pm/state";

// Mesma regra de content/doc.py. O Google Docs usa ids como "h.abc", que o servidor recusaria.
export const ANCHOR = /^[A-Za-z0-9_-]{1,64}$/;

// Títulos fora dos níveis 2 e 3 viram o nível mais próximo em vez de perder o título ao colar.
const PASTED_LEVELS = { h1: 2, h2: 2, h3: 3, h4: 3, h5: 3, h6: 3 };

function newAnchor() {
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  return `h-${[...bytes].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
}

function headingsOf(doc, type) {
  const found = [];
  doc.descendants((node, pos) => {
    if (node.type === type) found.push({ pos, anchor: node.attrs.anchor });
  });
  return found;
}

// Onde cada âncora que já existia foi parar: esse título mantém a âncora, e a cópia ganha outra.
function ownersAfter(transactions, oldDoc, type) {
  const owners = new Map();
  for (const { pos, anchor } of headingsOf(oldDoc, type)) {
    if (!anchor || owners.has(anchor)) continue;
    owners.set(anchor, transactions.reduce((p, tr) => tr.mapping.map(p, 1), pos));
  }
  return owners;
}

export const AnchoredHeading = Heading.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      anchor: {
        default: null,
        parseHTML: (el) => (ANCHOR.test(el.id) ? el.id : null),
        renderHTML: ({ anchor }) => (anchor ? { id: anchor } : {}),
      },
    };
  },

  parseHTML() {
    return Object.entries(PASTED_LEVELS).map(([tag, level]) => ({ tag, attrs: { level } }));
  },

  addProseMirrorPlugins() {
    const type = this.type;
    return [
      ...(this.parent?.() ?? []),
      new Plugin({
        appendTransaction(transactions, oldState, newState) {
          if (!transactions.some((tr) => tr.docChanged)) return null;
          const owners = ownersAfter(transactions, oldState.doc, type);
          const found = headingsOf(newState.doc, type);
          const isOwner = (h) => h.anchor && owners.get(h.anchor) === h.pos;
          const taken = new Set(found.filter(isOwner).map((h) => h.anchor));
          const tr = newState.tr;
          for (const heading of found) {
            if (isOwner(heading)) continue;
            if (heading.anchor && !taken.has(heading.anchor)) {
              taken.add(heading.anchor);
            } else {
              tr.setNodeAttribute(heading.pos, "anchor", newAnchor());
            }
          }
          return tr.docChanged ? tr : null;
        },
      }),
    ];
  },
});
