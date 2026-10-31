const MAX_SIDE = 1600;
const QUALITY = 0.8;

function canvasBlob(canvas, type) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, QUALITY));
}

// Encolhe no navegador: o servidor recusa imagem grande demais (exceto JPEG) e o envio fica leve.
// GIF e qualquer falha seguem como vieram; o servidor decide.
export async function shrink(file) {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  try {
    const side = Math.max(bitmap.width, bitmap.height);
    if (side <= MAX_SIDE) return file;
    const scale = MAX_SIDE / side;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    let blob = await canvasBlob(canvas, "image/webp");
    if (!blob || blob.type !== "image/webp") blob = await canvasBlob(canvas, "image/jpeg");
    if (!blob) return file;
    const ext = blob.type === "image/webp" ? ".webp" : ".jpg";
    const name = file.name.replace(/\.[^.]*$/, "") || "imagem";
    return new File([blob], name + ext, { type: blob.type });
  } catch {
    return file;
  } finally {
    bitmap.close();
  }
}

function showError(zone, message) {
  let alert = zone.querySelector("[role=alert]");
  if (!alert) {
    alert = document.createElement("p");
    alert.setAttribute("role", "alert");
    zone.append(alert);
  }
  alert.textContent = message;
}

async function send(zone, form, file) {
  const data = new FormData();
  for (const input of form.querySelectorAll("input[type=hidden]")) data.append(input.name, input.value);
  const prepared = await shrink(file);
  data.append("file", prepared, prepared.name);
  let response;
  try {
    response = await fetch(form.action, { method: "POST", body: data, credentials: "same-origin" });
  } catch {
    showError(zone, "Sem conexão. Tente enviar de novo.");
    return false;
  }
  if (response.ok) return true;
  let message = "Não foi possível enviar o arquivo.";
  try {
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    message = page.querySelector("[role=alert]")?.textContent.trim() || message;
  } catch {
    // mantém a mensagem padrão
  }
  showError(zone, message);
  return false;
}

export function initUpload(zone) {
  const form = zone.closest("form");
  const input = zone.querySelector("input[type=file]");
  if (!form || !input || zone.dataset.ready) return;
  zone.dataset.ready = "1";
  const submit = form.querySelector("button[type=submit]");
  if (submit) submit.hidden = true;
  input.required = false;
  input.multiple = true;
  let busy = false;

  async function upload(files) {
    if (busy || !files.length) return;
    busy = true;
    zone.setAttribute("aria-busy", "true");
    zone.querySelector("[role=alert]")?.remove();
    let ok = true;
    for (const file of files) ok = (await send(zone, form, file)) && ok;
    zone.removeAttribute("aria-busy");
    busy = false;
    input.value = "";
    if (ok) window.location.reload();
  }

  input.addEventListener("change", () => upload([...input.files]));
  form.addEventListener("dragover", (event) => {
    event.preventDefault();
    form.classList.add("over");
  });
  form.addEventListener("dragleave", () => form.classList.remove("over"));
  form.addEventListener("drop", (event) => {
    event.preventDefault();
    form.classList.remove("over");
    upload([...event.dataTransfer.files]);
  });
  document.addEventListener("paste", (event) => {
    if (!zone.isConnected || event.target.closest?.("input, textarea, [contenteditable]")) return;
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) {
      event.preventDefault();
      upload(files);
    }
  });
}
