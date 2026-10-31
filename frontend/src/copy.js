const FEEDBACK_MS = 1500;

function copyWithTextarea(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  if (!copied) throw new Error("cópia recusada");
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Sem HTTPS ou sem permissão, navigator.clipboard falta ou recusa.
    copyWithTextarea(text);
  }
}

async function onClick(event) {
  const button = event.target.closest?.("[data-copy]");
  if (!button) return;
  const label = button.dataset.copyLabel ?? button.textContent;
  button.dataset.copyLabel = label;
  try {
    await copy(button.dataset.copy);
    button.textContent = "Copiado";
  } catch {
    button.textContent = "Não copiou";
  }
  clearTimeout(button.copyTimer);
  button.copyTimer = setTimeout(() => { button.textContent = label; }, FEEDBACK_MS);
}

export function initCopy() {
  document.addEventListener("click", onClick);
}
