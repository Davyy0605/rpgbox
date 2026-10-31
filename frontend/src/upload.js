const MAX_SIDE = 1600;
const QUALITY = 0.8;

function canvasBlob(canvas, type) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, QUALITY));
}

// Lê só as dimensões (já com a rotação do EXIF), sem decodificar a imagem inteira em memória.
function probe(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    const done = (value) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    img.onload = () => done({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => done(null);
    img.src = url;
  });
}

// O iOS derruba a aba se decodificarmos uma foto de celular inteira; por isso o navegador
// já devolve o bitmap reduzido. Sem suporte à opção, cai para o bitmap inteiro.
async function decodeScaled(file, width, height) {
  try {
    const wide = width >= height;
    return await createImageBitmap(file, {
      [wide ? "resizeWidth" : "resizeHeight"]: wide ? width : height,
      resizeQuality: "high",
      imageOrientation: "from-image",
    });
  } catch {
    return createImageBitmap(file, { imageOrientation: "from-image" });
  }
}

// Encolhe no navegador: o servidor recusa imagem grande demais (exceto JPEG) e o envio fica leve.
// GIF e qualquer falha seguem como vieram; o servidor decide.
export async function shrink(file) {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  const size = await probe(file);
  if (!size || Math.max(size.width, size.height) <= MAX_SIDE) return file;
  const scale = MAX_SIDE / Math.max(size.width, size.height);
  const width = Math.max(1, Math.round(size.width * scale));
  const height = Math.max(1, Math.round(size.height * scale));
  let bitmap;
  let canvas;
  try {
    bitmap = await decodeScaled(file, width, height);
    canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    context.drawImage(bitmap, 0, 0, width, height);
    let blob = await canvasBlob(canvas, "image/webp");
    if (!blob || blob.type !== "image/webp") {
      // JPEG não tem transparência: sem fundo branco, PNG transparente sairia preto.
      context.globalCompositeOperation = "destination-over";
      context.fillStyle = "#fff";
      context.fillRect(0, 0, width, height);
      blob = await canvasBlob(canvas, "image/jpeg");
    }
    if (!blob) return file;
    const ext = blob.type === "image/webp" ? ".webp" : ".jpg";
    const name = file.name.replace(/\.[^.]*$/, "") || "imagem";
    return new File([blob], name + ext, { type: blob.type });
  } catch {
    return file;
  } finally {
    bitmap?.close();
    if (canvas) canvas.width = canvas.height = 0;
  }
}

const storeKey = (form) => `upload-messages:${form.getAttribute("action")}`;

function showMessages(zone, items) {
  zone.querySelector("[role=alert]")?.remove();
  if (!items.length) return;
  const alert = document.createElement("div");
  alert.setAttribute("role", "alert");
  for (const item of items) {
    const line = document.createElement("p");
    line.textContent = item.text;
    if (item.href) {
      line.append(" ");
      const link = document.createElement("a");
      link.href = item.href;
      link.textContent = item.linkText;
      line.append(link);
    }
    alert.append(line);
  }
  zone.append(alert);
}

async function send(form, file) {
  const data = new FormData();
  for (const input of form.querySelectorAll("input[type=hidden]")) data.append(input.name, input.value);
  const prepared = await shrink(file);
  data.append("file", prepared, prepared.name);
  let response;
  try {
    response = await fetch(form.action, { method: "POST", body: data, credentials: "same-origin" });
  } catch {
    return { text: `${file.name}: sem conexão. Tente enviar de novo.` };
  }
  // O fetch segue o redirecionamento; sessão vencida termina na página de entrada, com status 200.
  if (response.redirected && new URL(response.url).pathname.startsWith("/entrar")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    return { text: `${file.name}: Sessão expirada.`, href: `/entrar?next=${next}`, linkText: "Entrar de novo", expired: true };
  }
  if (response.ok) return null;
  let message = "Não foi possível enviar o arquivo.";
  try {
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    message = page.querySelector("[role=alert]")?.textContent.trim() || message;
  } catch {
    // mantém a mensagem padrão
  }
  return { text: `${file.name}: ${message}` };
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

  // Avisos de uma rodada anterior que terminou em recarga da página.
  try {
    const saved = sessionStorage.getItem(storeKey(form));
    sessionStorage.removeItem(storeKey(form));
    if (saved) showMessages(zone, JSON.parse(saved));
  } catch {
    // sem armazenamento: nada a mostrar
  }

  const queue = [];
  let running = false;

  async function drain() {
    running = true;
    zone.setAttribute("aria-busy", "true");
    showMessages(zone, []);
    const failures = [];
    let sent = 0;
    while (queue.length) {
      const failure = await send(form, queue.shift());
      if (failure) failures.push(failure);
      else sent += 1;
    }
    zone.removeAttribute("aria-busy");
    running = false;
    if (!sent) {
      showMessages(zone, failures);
      return;
    }
    // Há arquivos novos: recarrega para mostrá-los, levando os avisos de falha junto.
    try {
      if (failures.length) sessionStorage.setItem(storeKey(form), JSON.stringify(failures));
    } catch {
      showMessages(zone, failures);
      return;
    }
    window.location.reload();
  }

  function upload(files) {
    if (!files.length) return;
    queue.push(...files);
    if (!running) drain();
  }

  input.addEventListener("change", () => {
    upload([...input.files]);
    input.value = "";
  });
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
