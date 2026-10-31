// Escolha da origem do bloco incorporado, com a mesma lista do `@`.
import { SEARCH_DELAY, SuggestList, suggestionFetcher } from "./suggest.js";

const ready = new WeakSet();

export function initPicker(form) {
  if (ready.has(form)) return;
  ready.add(form);
  const input = form.querySelector("[role=combobox]");
  const details = form.closest("details");
  const self = Number(form.dataset.self);
  const fetchItems = suggestionFetcher(form.dataset.suggestUrl);
  const list = new SuggestList((item) => {
    form.elements.record.value = item.record;
    form.elements.anchor.value = item.anchor;
    form.submit();
  });

  let timer = null;

  const setOpen = (open) => {
    input.setAttribute("aria-expanded", String(open));
    if (open) return;
    clearTimeout(timer);
    list.hide();
  };

  const search = async () => {
    const query = input.value;
    const items = (await fetchItems(query)).filter((item) => item.record !== self);
    if (query !== input.value || document.activeElement !== input) return;
    list.show(items, query, input.getBoundingClientRect());
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    if (input.value.trim()) list.showLoading(input.value, input.getBoundingClientRect());
    setOpen(true);
    timer = setTimeout(search, SEARCH_DELAY);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (list.visible) list.pickActive();
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (list.visible && event.key === "ArrowDown") {
      event.preventDefault();
      list.move(1);
    } else if (list.visible && event.key === "ArrowUp") {
      event.preventDefault();
      list.move(-1);
    }
  });
  input.addEventListener("blur", () => setOpen(false));
  details?.addEventListener("toggle", () => {
    if (details.open) input.focus();
  });
}
