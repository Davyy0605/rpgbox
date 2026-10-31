// Salvamento automático: o texto fica no aparelho até o servidor confirmar, e o envio se repete sozinho.

import { DOMSerializer } from "@tiptap/pm/model";

import { docText } from "./editor.js";

const DELAY = 800;
const TIMEOUT = 90000;
const RETRIES = [3000, 10000, 30000];
// Limite do navegador para fetch com keepalive: acima disso o envio falharia na hora.
const KEEPALIVE_LIMIT = 60000;
const REMEMBERED_SENDS = 5;

const SAVING = "Salvando";
const SAVED = "Salvo";
const OFFLINE = "Sem conexão, tentando de novo";
const SESSION = "Sessão expirada. Entre de novo para salvar.";
const GONE = "Este texto não existe mais no servidor. Copie o que precisar.";
const REFUSED = "O servidor recusou o envio.";
const KEPT = "O texto segue neste aparelho.";
const AT_RISK = "Este aparelho não conseguiu guardar o texto: não feche a página antes de salvar.";

const EMPTY = { type: "doc", content: [{ type: "paragraph" }] };

export function draftKey(url, fieldKey) {
  return fieldKey ? `rascunho:${url}:${fieldKey}` : `rascunho:${url}`;
}

function readDraft(key) {
  try {
    const draft = JSON.parse(localStorage.getItem(key));
    return draft?.value === undefined || draft.value === null ? null : draft;
  } catch {
    return null;
  }
}

// false: sem espaço ou bloqueado. O texto segue na memória e continua sendo enviado, mas só ali.
function writeDraft(key, draft) {
  try {
    localStorage.setItem(key, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

function dropDraft(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Nada a fazer: o rascunho de quem não consegue gravar também não existe.
  }
}

// A chave principal e as de outras abas, que recebem um sufixo quando ela já tem dono.
function draftKeys(base) {
  try {
    return Object.keys(localStorage).filter((key) => key === base || key.startsWith(`${base}#`)).sort();
  } catch {
    return [];
  }
}

function csrfToken() {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? "";
}

async function request(url, body, leaving) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT);
  const text = JSON.stringify(body);
  // Com a página sumindo, só keepalive termina; o rascunho cobre o texto grande demais para ele.
  const keepalive = leaving && new Blob([text]).size < KEEPALIVE_LIMIT;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
      body: text,
      signal: controller.signal,
      keepalive,
    });
    const data = await response.json().catch(() => null);
    return { status: response.status, redirected: response.redirected, data };
  } finally {
    clearTimeout(timeout);
  }
}

// `field` diz como ler, comparar e mostrar o valor, seja um editor ou um campo simples.
function startSaver(field, { element, saveUrl, createUrl, version: startVersion, key: startKey, orphanKey: startOrphan }) {
  let url = saveUrl;
  let version = startVersion ?? null;
  let key = startKey;
  const orphanKey = startOrphan;
  // Cada aba só apaga ou sobrescreve o rascunho que é seu.
  const owner = Math.random().toString(36).slice(2);
  let slot = null;
  let unstored = false;
  let message = "";
  let warned = false;
  let value = null;
  let seq = 0;
  let savedSeq = 0;
  let sending = false;
  let timer = null;
  let attempts = 0;
  let halted = false;
  let inConflict = false;
  // Envios sem resposta: qualquer um deles pode ter chegado, e aí o 409 é do próprio texto.
  let unconfirmed = [];

  const status = document.createElement("p");
  status.className = "save-status";
  status.setAttribute("role", "status");
  status.hidden = true;
  element.after(status);

  function show(text, warn = false) {
    message = text;
    warned = warn;
    const atRisk = unstored && text && text !== SAVED;
    const note = atRisk ? AT_RISK : warn ? KEPT : "";
    status.textContent = note ? `${text.replace(/\.?$/, ".")} ${note}` : text;
    status.classList.toggle("warn", warn || Boolean(atRisk));
    status.hidden = !text;
  }

  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(send, ms);
  }

  function dropOwnDraft() {
    if (slot && readDraft(slot)?.owner === owner) dropDraft(slot);
    slot = null;
  }

  // O rascunho antigo só sai depois que o novo foi gravado, e o de outra aba fica onde está.
  function persist() {
    const holder = readDraft(key);
    const suffixed = `${key}#${owner}`;
    const target = slot === suffixed || (holder && holder.owner !== owner) ? suffixed : key;
    unstored = !writeDraft(target, { value, version, owner });
    if (unstored) {
      show(message, warned);
    } else {
      if (slot !== target) dropOwnDraft();
      slot = target;
    }
  }

  function retry(text, warn) {
    show(text, warn);
    schedule(RETRIES[Math.min(attempts, RETRIES.length - 1)]);
    attempts += 1;
  }

  function changed(next) {
    value = next;
    seq += 1;
    halted = false;
    persist();
    if (attempts) show(message, warned);
    else show(SAVING);
    schedule(DELAY);
  }

  function confirmed(newVersion, upTo) {
    version = newVersion;
    savedSeq = upTo;
    attempts = 0;
    unconfirmed = [];
    element.dataset.version = version;
    if (seq === savedSeq) {
      dropOwnDraft();
      unstored = false;
      show(SAVED);
    } else {
      // O que foi escrito durante o envio parte da versão nova, inclusive no rascunho.
      persist();
      schedule(DELAY);
    }
  }

  function closeConflict(panel, chosen, serverVersion, isServer) {
    if (isServer && !field.accepts(chosen)) {
      // O editor não abre a versão do servidor: abandonar a daqui é recarregar e vê-la como somente leitura.
      dropOwnDraft();
      window.location.reload();
      return;
    }
    panel.remove();
    field.lock(false);
    field.write(chosen);
    inConflict = false;
    version = serverVersion;
    attempts = 0;
    unconfirmed = [];
    element.dataset.version = version;
    changed(field.read());
    send();
  }

  function versionBox(title, shown, onUse) {
    const box = document.createElement("div");
    box.className = "conflict-version";
    box.setAttribute("role", "group");
    box.setAttribute("aria-label", title);
    const heading = document.createElement("p");
    heading.className = "muted";
    heading.textContent = title;
    const body = document.createElement("div");
    body.className = "conflict-body";
    if (field.blank(shown)) body.textContent = "(vazio)";
    else field.preview(shown, body);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn";
    button.textContent = "Usar esta";
    button.addEventListener("click", onUse);
    box.append(heading, body, button);
    return box;
  }

  // O rascunho guarda a versão antiga até a escolha: recarregar aqui traz a mesma pergunta de volta.
  function openConflict(serverValue, serverVersion) {
    inConflict = true;
    clearTimeout(timer);
    show("");
    field.lock(true);
    const mine = value;
    const panel = document.createElement("div");
    panel.className = "conflict";
    const title = document.createElement("p");
    title.textContent = "Alterado em outro aparelho";
    panel.append(
      title,
      versionBox("Neste aparelho", mine, () => closeConflict(panel, mine, serverVersion, false)),
      versionBox("Em outro aparelho", serverValue, () => closeConflict(panel, serverValue, serverVersion, true)),
    );
    status.after(panel);
  }

  function settleConflict(serverValue, serverVersion, sent, sentSeq) {
    if (field.same(sent, serverValue)) {
      confirmed(serverVersion, sentSeq);
    } else if (unconfirmed.some((old) => field.same(old, serverValue))) {
      // Um envio antigo chegou: o texto atual segue na frente dele.
      confirmed(serverVersion, savedSeq);
    } else {
      openConflict(serverValue, serverVersion);
    }
  }

  function bindBlock(data) {
    const existing = "content" in data && !field.blank(data.content);
    url = data.save_url;
    version = data.version;
    key = draftKey(url);
    element.dataset.saveUrl = url;
    element.dataset.version = version;
    delete element.dataset.createUrl;
    // Com texto no bloco, o rascunho fica na chave da aba: recarregar volta a tratá-lo como conflito.
    if (!existing) persist();
    return existing;
  }

  async function deliver(sent, leaving) {
    if (!url) {
      const created = await request(createUrl, { first: true }, leaving);
      if (created.status !== 200 || typeof created.data?.save_url !== "string") return created;
      if (bindBlock(created.data)) return { status: 409, data: created.data };
    }
    return request(url, field.body(sent, version), leaving);
  }

  function rememberUnconfirmed(sent) {
    const last = unconfirmed[unconfirmed.length - 1];
    // Repetir o mesmo texto não pode empurrar para fora um envio mais antigo que talvez tenha chegado.
    if (last === undefined || !field.same(last, sent)) unconfirmed = [...unconfirmed, sent].slice(-REMEMBERED_SENDS);
  }

  function settle(result, sent, sentSeq) {
    const data = result?.data;
    const hasVersion = Number.isInteger(data?.version);
    if (result?.redirected || result?.status === 401 || result?.status === 403) {
      // Sem sessão, o Django redireciona ao login, que responde 200 com HTML.
      retry(SESSION, true);
    } else if (!result || result.status >= 500 || [408, 425, 429].includes(result.status)
      || ((result.status === 200 || result.status === 409) && !hasVersion)) {
      // Inclui a página de espera de quem hospeda o site, que também pode vir como 200.
      rememberUnconfirmed(sent);
      retry(OFFLINE);
    } else if (result.status === 200) {
      confirmed(data.version, sentSeq);
    } else if (result.status === 409) {
      settleConflict("content" in data ? data.content : data.value, data.version, sent, sentSeq);
    } else if (seq !== sentSeq) {
      // Recusou um texto que já mudou: quem decide é o envio do texto novo.
      schedule(DELAY);
    } else {
      halted = true;
      show(result.status === 404 ? GONE : `Não foi possível salvar. ${data?.error ?? REFUSED}`, true);
    }
  }

  // `ending`: a página acabou. Um envio em andamento morre com ela, então este vai mesmo assim.
  async function send(leaving = false, ending = false) {
    clearTimeout(timer);
    if ((sending && !ending) || inConflict || seq === savedSeq) return;
    sending = true;
    const sent = value;
    const sentSeq = seq;
    if (!attempts) show(SAVING);
    const result = await deliver(sent, leaving).catch(() => null);
    sending = false;
    settle(result, sent, sentSeq);
  }

  // O Chromium dispara pagehide com a página ainda "visible".
  function onLeave(event) {
    if (halted) return;
    const ending = event.type === "pagehide";
    send(ending || document.visibilityState === "hidden", ending);
  }

  function takeDraft(stored, draft, server) {
    const orphan = Boolean(orphanKey) && stored.startsWith(orphanKey);
    writeDraft(stored, { ...draft, owner });
    slot = stored;
    if (orphan ? field.blank(server) : draft.version === version) {
      field.write(draft.value);
      changed(field.read());
      send();
    } else {
      value = draft.value;
      seq += 1;
      openConflict(server, version);
    }
  }

  // Um rascunho por vez: os outros seguem guardados e aparecem ao abrir de novo.
  function restore() {
    const server = field.read();
    for (const stored of [...draftKeys(key), ...(orphanKey ? draftKeys(orphanKey) : [])]) {
      const draft = readDraft(stored);
      if (draft && field.accepts(draft.value)) {
        if (!field.same(draft.value, server)) {
          takeDraft(stored, draft, server);
          return;
        }
        dropDraft(stored);
      }
    }
  }

  document.addEventListener("visibilitychange", onLeave);
  window.addEventListener("pagehide", onLeave);
  // Com folga: a rede que acabou de voltar ainda oscila.
  window.addEventListener("online", () => {
    if (!halted && seq !== savedSeq) schedule(DELAY);
  });
  restore();

  return { changed };
}

function asDoc(value) {
  if (typeof value === "string") {
    return value ? { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: value }] }] } : EMPTY;
  }
  return value?.content?.length ? value : EMPTY;
}

function editorField(editor, element, fieldKey) {
  const { schema } = editor;
  const node = (value) => schema.nodeFromJSON(asDoc(value));
  const same = (a, b) => {
    try {
      return node(a).eq(node(b));
    } catch {
      return false;
    }
  };
  return {
    read: () => editor.getJSON(),
    write: (value) => editor.commands.setContent(asDoc(value), { emitUpdate: false }),
    same,
    blank: (value) => same(value, EMPTY),
    accepts(value) {
      try {
        node(value).check();
        return true;
      } catch {
        return false;
      }
    },
    preview(value, box) {
      try {
        box.append(DOMSerializer.fromSchema(schema).serializeFragment(node(value).content));
      } catch {
        box.textContent = docText(asDoc(value));
      }
    },
    lock(locked) {
      // Sem o segundo argumento, setEditable dispara um "update", e o texto seria enviado.
      editor.setEditable(!locked, false);
      element.hidden = locked;
    },
    body: (value, version) => (fieldKey ? { key: fieldKey, version, value } : { version, content: value }),
  };
}

export function attachAutosave(editor, { element, saveUrl, createUrl, fieldKey, version, draftKey: key, orphanKey }) {
  if (!saveUrl && !createUrl) return;
  const saver = startSaver(editorField(editor, element, fieldKey), { element, saveUrl, createUrl, version, key, orphanKey });
  element.addEventListener("editor:change", (event) => saver.changed(event.detail.doc));
}

function inputField(input) {
  const text = (value) => (value === null || value === undefined ? "" : String(value));
  // O teclado do celular deixa um espaço no fim, e número e link seriam recusados por isso.
  const keepSpaces = input.dataset.field === "short";
  return {
    read: () => (keepSpaces ? input.value : input.value.trim()),
    write(value) {
      input.value = text(value);
    },
    same: (a, b) => text(a) === text(b),
    blank: (value) => text(value) === "",
    accepts: () => true,
    preview(value, box) {
      box.textContent = text(value);
    },
    lock(locked) {
      input.readOnly = locked;
      input.hidden = locked;
    },
    body: (value, version) => ({ key: input.dataset.key, version, value }),
  };
}

export function attachFieldAutosave(input) {
  const { saveUrl, key, version } = input.dataset;
  const field = inputField(input);
  const saver = startSaver(field, { element: input, saveUrl, version: Number(version), key: draftKey(saveUrl, key) });
  input.addEventListener("input", () => saver.changed(field.read()));
}
