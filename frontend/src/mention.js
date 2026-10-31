import Mention from "@tiptap/extension-mention";

import { ANCHOR } from "./heading.js";
import { SEARCH_DELAY, SuggestList, suggestionFetcher } from "./suggest.js";

function suggestionRender() {
  return () => {
    let list = null;
    let command = null;
    let editor = null;
    const hide = () => list?.hide();
    const update = (props) => {
      command = props.command;
      const { query, items, clientRect } = props;
      // Com espaços na busca, sem resultados é só texto comum: não atrapalha a escrita.
      const plainText = query.includes(" ") && !list.visible;
      if (props.loading && query.trim()) {
        if (!plainText) list.showLoading(query, clientRect());
      } else if (!items.length && query.includes(" ")) {
        hide();
      } else {
        list.show(items, query, clientRect());
      }
    };
    return {
      onStart(props) {
        list = new SuggestList((item) => command(item));
        editor = props.editor;
        editor.on("blur", hide);
        update(props);
      },
      onUpdate: update,
      onKeyDown({ event }) {
        if (!list.visible) return false;
        if (event.key === "Escape") {
          list.hide();
          return true;
        }
        if (event.key === "ArrowDown") {
          list.move(1);
          return true;
        }
        if (event.key === "ArrowUp") {
          list.move(-1);
          return true;
        }
        return event.key === "Enter" ? list.pickActive() : false;
      },
      onExit() {
        editor?.off("blur", hide);
        list?.destroy();
      },
    };
  };
}

export function mentionExtension({ suggestUrl, missing }) {
  const fetchItems = suggestionFetcher(suggestUrl);
  return Mention.extend({
    addAttributes() {
      return {
        record: { default: null, rendered: false, parseHTML: (el) => Number(el.dataset.record) },
        anchor: {
          default: "",
          rendered: false,
          parseHTML: (el) => (ANCHOR.test(el.dataset.anchor ?? "") ? el.dataset.anchor : ""),
        },
        label: { default: "", rendered: false, parseHTML: (el) => el.textContent },
      };
    },
    parseHTML() {
      return [{
        tag: ".mention[data-record]",
        priority: 200,
        getAttrs: (el) => (Number.isInteger(Number(el.dataset.record)) ? null : false),
      }];
    },
    renderHTML({ node }) {
      const { record, anchor, label } = node.attrs;
      const data = { class: "mention", "data-record": record, "data-anchor": anchor };
      if (missing.has(record)) return ["s", data, label];
      return ["a", {
        ...data,
        href: `/r/${record}/${anchor ? `?trecho=${anchor}#${anchor}` : ""}`,
        "data-panel-url": `/r/${record}/painel/${anchor ? `?ancora=${anchor}` : ""}`,
      }, label];
    },
    renderText({ node }) {
      return node.attrs.label;
    },
  }).configure({
    deleteTriggerWithBackspace: true,
    suggestion: {
      char: "@",
      allowSpaces: true,
      debounce: SEARCH_DELAY,
      items: ({ query }) => fetchItems(query),
      render: suggestionRender(),
      command: ({ editor, range, props }) => {
        editor.chain().focus().insertContentAt(range, [
          { type: "mention", attrs: { record: props.record, anchor: props.anchor, label: props.label } },
          { type: "text", text: " " },
        ]).run();
      },
    },
  });
}
