const SHOWN_MS = 6000;

let box = null;
let timer = null;

// Aviso curto de que uma ação sem recarga não deu certo.
export function notice(text) {
  if (!box) {
    box = document.createElement("div");
    box.className = "notice";
    box.setAttribute("role", "alert");
    document.body.append(box);
  }
  box.textContent = text;
  box.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => {
    box.hidden = true;
  }, SHOWN_MS);
}
