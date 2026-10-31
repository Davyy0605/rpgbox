const fold = (text) => text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();

function initToggle() {
  const box = document.querySelector("[data-topsearch]");
  const toggle = box?.querySelector("[data-search-toggle]");
  if (!box) return;
  const setOpen = (open) => {
    box.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };
  toggle.addEventListener("click", () => {
    setOpen(true);
    box.querySelector("[data-search-input]").focus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });
  document.addEventListener("pointerdown", (event) => {
    if (!box.contains(event.target)) setOpen(false);
  });
}

function focusSearch(event) {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k") return;
  const input = document.querySelector("[data-search-input]");
  if (!input) return;
  event.preventDefault();
  document.querySelector("[data-search-toggle]")?.click();
  input.focus();
  input.select();
}

function initListFilter() {
  const form = document.querySelector("[data-list-filter]");
  if (!form) return;
  const input = form.querySelector("input");
  const empty = document.querySelector("[data-filter-empty]");
  const rows = [...document.querySelectorAll("li > a[data-panel-url]")].map((link) => ({
    row: link.parentElement,
    name: fold(link.textContent),
  }));
  const apply = () => {
    const wanted = fold(input.value.trim());
    let shown = 0;
    for (const { row, name } of rows) {
      row.hidden = !name.includes(wanted);
      if (!row.hidden) shown += 1;
    }
    empty.hidden = !wanted || shown > 0;
  };
  input.addEventListener("input", apply);
  form.addEventListener("submit", (event) => event.preventDefault());
  // Ao voltar, o navegador devolve o texto do campo sem avisar.
  apply();
}

export function initSearch() {
  initToggle();
  initListFilter();
  document.addEventListener("keydown", focusSearch);
}
