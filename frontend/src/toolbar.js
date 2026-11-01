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
let colorInput = null;
let clearColor = null;
// Seletor de cor aberto: no celular o editor perde o foco e o teclado fecha, então guardamos editor e seleção.
let picking = null;

function refresh() {
  if (!current) return;
  buttons.forEach(([button, , , isActive]) => button.setAttribute("aria-pressed", String(isActive(current))));
  const color = current.getAttributes("textStyle").color;
  clearColor.setAttribute("aria-pressed", String(Boolean(color)));
  if (color && /^#[0-9a-f]{6}$/i.test(color)) colorInput.value = color.toLowerCase();
}

function hide() {
  current = null;
  bar.hidden = true;
  document.body.classList.remove("editing");
}

// Fim da escolha de cor sem aplicar nada: se o editor perdeu o foco, a barra some agora.
function endPicking() {
  const editor = picking?.editor;
  picking = null;
  if (editor && current === editor && !editor.isFocused) hide();
}

// Cor escolhida: o foco volta ao texto, com a mesma seleção, e a barra continua à mão.
function donePicking() {
  const editor = picking?.editor ?? current;
  picking = null;
  if (editor && current === editor && !editor.isFocused) editor.commands.focus();
}

function createColorControls() {
  colorInput = document.createElement("input");
  colorInput.type = "color";
  colorInput.setAttribute("aria-label", "Cor");
  colorInput.addEventListener("pointerdown", () => {
    if (!current) return;
    const { from, to } = current.state.selection;
    picking = { editor: current, from, to };
  });
  colorInput.addEventListener("input", () => {
    if (!picking && !current) return;
    const editor = picking?.editor ?? current;
    const { from, to } = picking ?? current.state.selection;
    // Sem focus(): reabriria o teclado a cada ajuste. Seleção vazia só vale para o que for digitado depois.
    editor.chain().setTextSelection({ from, to }).setColor(colorInput.value).run();
  });
  colorInput.addEventListener("change", donePicking);
  clearColor = document.createElement("button");
  clearColor.type = "button";
  clearColor.textContent = "×";
  clearColor.setAttribute("aria-label", "Remover cor");
  clearColor.addEventListener("click", () => {
    if (current) current.chain().focus().unsetColor().run();
  });
  return [colorInput, clearColor];
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
  bar.append(...buttons.map(([button]) => button), ...createColorControls());
  // Toque fora da barra encerra a escolha de cor, mesmo que o seletor tenha sido cancelado.
  document.addEventListener("pointerdown", (event) => {
    if (picking && !bar.contains(event.target)) endPicking();
  }, true);
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
    if (current !== editor || picking) return;
    hide();
  };
  editor.on("blur", leave);
  editor.on("destroy", leave);
  editor.on("transaction", () => {
    if (current === editor) refresh();
  });
}
