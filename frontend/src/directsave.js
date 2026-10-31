// Envio direto, sem rascunho nem novas tentativas. A Tarefa 10 troca isto pelo salvamento automático.

const DELAY = 800;

function csrfToken() {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? "";
}

function post(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

// Aba vazia: o bloco só nasce quando há o que guardar.
async function ensureSaveUrl(element) {
  if (element.dataset.saveUrl) return;
  const response = await post(element.dataset.createUrl);
  if (!response.ok) throw new Error(`bloco não criado: ${response.status}`);
  const { save_url: saveUrl, version } = await response.json();
  element.dataset.saveUrl = saveUrl;
  element.dataset.version = version;
  delete element.dataset.createUrl;
}

function payload(element, doc) {
  const version = Number(element.dataset.version);
  return element.dataset.key ? { key: element.dataset.key, version, value: doc } : { version, content: doc };
}

export function attachDirectSave(element) {
  let timer = null;
  let pending = null;
  let sending = false;

  async function send() {
    if (sending || !pending) return;
    sending = true;
    const doc = pending;
    pending = null;
    try {
      await ensureSaveUrl(element);
      const response = await post(element.dataset.saveUrl, payload(element, doc));
      if (!response.ok) throw new Error(`não salvo: ${response.status}`);
      element.dataset.version = (await response.json()).version;
    } catch (error) {
      console.warn(error);
    }
    sending = false;
    send();
  }

  element.addEventListener("editor:change", (event) => {
    pending = event.detail.doc;
    clearTimeout(timer);
    timer = setTimeout(send, DELAY);
  });
}
