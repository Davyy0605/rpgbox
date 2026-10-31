import * as pdfjs from "pdfjs-dist/build/pdf.min.mjs";

// Uma página por vez: o celular não aguenta dezenas de canvas grandes na memória.
async function initPdf(root) {
  const url = root.dataset.pdfUrl;
  pdfjs.GlobalWorkerOptions.workerSrc = root.dataset.workerUrl;
  const fallback = root.innerHTML;
  const canvas = document.createElement("canvas");
  canvas.className = "pdf-canvas";
  const label = document.createElement("span");
  label.className = "muted";
  label.setAttribute("aria-live", "polite");
  const prev = button("Anterior");
  const next = button("Próxima");
  const problem = document.createElement("p");
  problem.setAttribute("role", "alert");
  problem.hidden = true;
  problem.append("Não foi possível mostrar esta página. ");
  const openLink = document.createElement("a");
  openLink.className = "btn-link";
  openLink.href = url;
  openLink.textContent = "Abrir PDF";
  problem.append(openLink);
  const bar = document.createElement("div");
  bar.className = "pdf-bar";
  bar.append(prev, label, next);

  let pdf;
  let number = 1;
  let busy = false;
  let pending = null;

  async function show(n) {
    if (busy) {
      pending = n;
      return;
    }
    busy = true;
    try {
      const page = await pdf.getPage(n);
      const base = page.getViewport({ scale: 1 });
      const width = Math.max(root.clientWidth, 200);
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const viewport = page.getViewport({ scale: (width / base.width) * ratio });
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = "100%";
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      page.cleanup();
      number = n;
      problem.hidden = true;
    } catch {
      // A página falhou: limpa o desenho antigo, mantém a navegação e o link para abrir o arquivo.
      number = n;
      canvas.width = canvas.width;
      problem.hidden = false;
    } finally {
      busy = false;
    }
    label.textContent = `Página ${number} de ${pdf.numPages}`;
    prev.disabled = number <= 1;
    next.disabled = number >= pdf.numPages;
    if (pending !== null) {
      const again = pending;
      pending = null;
      await show(again);
    }
  }

  prev.addEventListener("click", () => show(number - 1));
  next.addEventListener("click", () => show(number + 1));

  try {
    pdf = await pdfjs.getDocument({ url }).promise;
    root.replaceChildren(canvas, problem);
    if (pdf.numPages > 1) root.append(bar);
    await show(1);
  } catch {
    root.innerHTML = fallback;
    const msg = document.createElement("p");
    msg.setAttribute("role", "alert");
    msg.textContent = "Não foi possível mostrar o PDF aqui. Use o link para abrir.";
    root.prepend(msg);
  }
}

function button(text) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn";
  b.textContent = text;
  return b;
}

document.querySelectorAll("[data-pdf-url]").forEach(initPdf);
