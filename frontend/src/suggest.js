// Lista de sugestões usada pelo `@` e pela escolha de origem do bloco incorporado.

export const SEARCH_DELAY = 200;

export function suggestionFetcher(url) {
  let controller = null;
  return async (query) => {
    controller?.abort();
    if (!query.trim()) return [];
    controller = new AbortController();
    try {
      const response = await fetch(`${url}?q=${encodeURIComponent(query)}`, { signal: controller.signal });
      return response.ok ? await response.json() : [];
    } catch {
      return [];
    }
  };
}

function visibleBottom() {
  const toolbar = document.querySelector(".toolbar:not([hidden])");
  if (toolbar) return toolbar.getBoundingClientRect().top;
  const viewport = window.visualViewport;
  return viewport ? viewport.offsetTop + viewport.height : window.innerHeight;
}

export class SuggestList {
  constructor(onPick) {
    this.onPick = onPick;
    this.items = [];
    this.active = 0;
    this.loading = false;
    this.el = document.createElement("ul");
    this.el.className = "suggest";
    this.el.setAttribute("role", "listbox");
    this.el.setAttribute("aria-label", "Sugestões");
    this.el.hidden = true;
    // Sem isto o toque tira o foco do texto antes de escolher.
    this.el.addEventListener("mousedown", (event) => event.preventDefault());
    document.body.append(this.el);
  }

  get visible() {
    return !this.el.hidden;
  }

  show(items, query, rect) {
    this.loading = false;
    this.items = items;
    this.active = 0;
    this.render(query);
    this.el.hidden = false;
    this.place(rect);
  }

  // Sem resposta ainda: mantém o que está na tela, para a lista não piscar a cada tecla.
  showLoading(query, rect) {
    this.loading = true;
    if (!this.items.length) this.render(query);
    this.el.hidden = false;
    this.place(rect);
  }

  render(query) {
    const rows = this.items.map((item, index) => {
      const row = document.createElement("li");
      row.setAttribute("role", "option");
      row.setAttribute("aria-selected", String(index === this.active));
      row.textContent = item.label;
      row.addEventListener("click", () => this.onPick(item));
      return row;
    });
    if (!rows.length) {
      const hint = document.createElement("li");
      hint.setAttribute("role", "presentation");
      hint.className = "muted";
      hint.textContent = !query.trim() ? "Digite para buscar." : this.loading ? "Buscando…" : "Nada encontrado.";
      rows.push(hint);
    }
    this.el.replaceChildren(...rows);
  }

  place(rect) {
    const bottom = visibleBottom();
    const top = window.visualViewport?.offsetTop ?? 0;
    const below = bottom - rect.bottom - 8;
    const above = rect.top - top - 8;
    const needed = Math.min(this.el.scrollHeight, 220);
    const style = this.el.style;
    if (below >= needed || below >= above) {
      style.top = `${rect.bottom + 4}px`;
      style.bottom = "auto";
      style.maxHeight = `${below}px`;
    } else {
      style.top = "auto";
      style.bottom = `${window.innerHeight - rect.top + 4}px`;
      style.maxHeight = `${above}px`;
    }
  }

  move(delta) {
    if (!this.items.length) return;
    this.active = (this.active + delta + this.items.length) % this.items.length;
    [...this.el.children].forEach((row, index) => {
      row.setAttribute("aria-selected", String(index === this.active));
      if (index === this.active) row.scrollIntoView({ block: "nearest" });
    });
  }

  // Devolve true quando o Enter fica com a lista. Durante a busca ele é só ignorado:
  // a opção na tela pode ser antiga, e soltá-lo para o editor quebraria o parágrafo.
  pickActive() {
    if (this.loading) return true;
    const item = this.items[this.active];
    if (!item) return false;
    this.onPick(item);
    return true;
  }

  hide() {
    this.el.hidden = true;
  }

  destroy() {
    this.el.remove();
  }
}
