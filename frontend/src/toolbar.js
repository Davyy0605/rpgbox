// Barra única da página: segue o editor em foco e fica acima do teclado do celular.

const ACTIONS = [
  ["T", "Título", (e) => e.chain().focus().toggleHeading({ level: 2 }).run(), (e) => e.isActive("heading", { level: 2 })],
  ["t", "Subtítulo", (e) => e.chain().focus().toggleHeading({ level: 3 }).run(), (e) => e.isActive("heading", { level: 3 })],
  ["N", "Negrito", (e) => e.chain().focus().toggleBold().run(), (e) => e.isActive("bold")],
  ["I", "Itálico", (e) => e.chain().focus().toggleItalic().run(), (e) => e.isActive("italic")],
  ["•", "Lista", (e) => e.chain().focus().toggleBulletList().run(), (e) => e.isActive("bulletList")],
  ["1.", "Lista numerada", (e) => e.chain().focus().toggleOrderedList().run(), (e) => e.isActive("orderedList")],
];

let bar = null;
let buttons = [];
let current = null;

function refresh() {
  if (!current) return;
  buttons.forEach(([button, , , isActive]) => button.setAttribute("aria-pressed", String(isActive(current))));
}

function followKeyboard() {
  const viewport = window.visualViewport;
  const covered = window.innerHeight - viewport.height - viewport.offsetTop;
  bar.style.bottom = `${Math.max(0, covered)}px`;
}

function createBar() {
  bar = document.createElement("div");
  bar.className = "toolbar";
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "Formatação");
  bar.hidden = true;
  buttons = ACTIONS.map(([text, label, run, isActive]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.setAttribute("aria-label", label);
    button.addEventListener("click", () => {
      if (current) run(current);
    });
    return [button, label, run, isActive];
  });
  bar.append(...buttons.map(([button]) => button));
  // Mantém o foco, e com ele o teclado, no texto.
  bar.addEventListener("mousedown", (event) => event.preventDefault());
  document.body.append(bar);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", followKeyboard);
    window.visualViewport.addEventListener("scroll", followKeyboard);
    followKeyboard();
  }
}

export function attachToolbar(editor) {
  if (!bar) createBar();
  editor.on("focus", () => {
    current = editor;
    bar.hidden = false;
    document.body.classList.add("editing");
    refresh();
  });
  const leave = () => {
    if (current !== editor) return;
    current = null;
    bar.hidden = true;
    document.body.classList.remove("editing");
  };
  editor.on("blur", leave);
  editor.on("destroy", leave);
  editor.on("transaction", () => {
    if (current === editor) refresh();
  });
}
