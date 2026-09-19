const API = "/api/v1";
const ASSET_VERSION = "20260727-pagamenti";
const $ = (id) => document.getElementById(id);
const openModal = (id) => $(id).classList.add("is-active");
const closeModal = (id) => $(id).classList.remove("is-active");
const token = () => sessionStorage.getItem("token");
const user = () => JSON.parse(sessionStorage.getItem("user") || "null");

function esc(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function escAttr(value) {
  return String(value == null ? "" : value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtDate(value, options = { dateStyle: "short", timeStyle: "short" }) {
  if (!value) return "-";
  try {
    return new Intl.DateTimeFormat("it-IT", options).format(new Date(value));
  } catch (_) {
    return String(value);
  }
}

function monthLabel(value) {
  return new Intl.DateTimeFormat("it-IT", { month: "short", year: "2-digit" })
    .format(new Date(`${value}-01T12:00:00`));
}

function euro(value, gratuito = false) {
  const amount = Number(value || 0) / 100;
  if (gratuito && amount === 0) return "Gratuito";
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(amount);
}

function tipoDietaLabel(tipo) {
  return tipo === "S" ? "Settimanale" : "Giornaliero";
}

// Card condivise

function homeKpiHtml(title, value, note = "", icon = "", tone = "has-text-primary") {
  const iconHtml = icon ? `<span class="icon ${tone}"><i class="fa-solid ${icon}"></i></span>` : "";
  const noteHtml = note ? `<p class="is-size-7 has-text-grey mt-2">${esc(note)}</p>` : "";
  return `<div class="column is-3-desktop is-6-tablet">
    <div class="box home-kpi">
      <div class="level is-mobile mb-2">
        <div class="level-left"><p class="is-size-7 has-text-weight-bold has-text-grey">${esc(title)}</p></div>
        <div class="level-right">${iconHtml}</div>
      </div>
      <p class="home-kpi-value">${value}</p>
      ${noteHtml}
    </div>
  </div>`;
}


// Pagamenti
const PAGAMENTO_PAGE_SIZE = 4;
const PagamentoState = { cfg: null, panel: null, selected: null, page: {} };

function pagamentoSections(viewer) {
  const labels = viewer === "nutrizionista"
    ? ["Da incassare", "Nessun pagamento da incassare."]
    : ["Da pagare", "Non hai pagamenti da effettuare."];
  return [
    ["aperti", labels[0], labels[1]],
    ["pagati", "Pagamenti effettuati", "Nessun pagamento registrato."],
  ];
}

function pagamentoActiveSections() {
  return PagamentoState.cfg?.sections || pagamentoSections(PagamentoState.cfg?.viewer);
}

function pagamentoSectionHtml([key, title]) {
  return `<section class="box pagamento-section">
    <div class="level is-mobile mb-3">
      <div class="level-left"><div><h3 class="title is-5 mb-1">${esc(title)}</h3><p id="pagamento-${key}-summary" class="is-size-7 has-text-grey"></p></div></div>
    </div>
    <div id="pagamento-${key}-list"></div>
    <div class="level is-mobile mt-3">
      <div class="level-left"><button id="pagamento-${key}-prev" class="button is-small is-light" onclick="pagamentoPage('${key}', -1)">← Precedenti</button></div>
      <div class="level-item" id="pagamento-${key}-page"></div>
      <div class="level-right"><button id="pagamento-${key}-next" class="button is-small is-light" onclick="pagamentoPage('${key}', 1)">Successive →</button></div>
    </div>
  </section>`;
}

function pagamentoModalHtml(viewer) {
  return viewer === "nutrizionista" ? `
    <div class="modal" id="pagamento-payment-modal">
      <div class="modal-background" onclick="pagamentoClosePayment()"></div>
      <div class="modal-card">
        <header class="modal-card-head"><p class="modal-card-title">Registra pagamento</p><button class="delete" onclick="pagamentoClosePayment()"></button></header>
        <section class="modal-card-body">
          <p id="pagamento-payment-title" class="has-text-weight-semibold mb-4"></p>
          <div class="level is-mobile"><span>Prezzo prestazione</span><strong id="pagamento-payment-base"></strong></div>
          <div class="field"><label class="label" for="pagamento-payment-discount">Sconto (€)</label><input id="pagamento-payment-discount" class="input" type="number" min="0" step="0.01" value="0"></div>
          <p class="help">Il totale da pagare viene calcolato e mostrato dal server alla conferma.</p>
        </section>
        <footer class="modal-card-foot"><button class="button is-primary" onclick="pagamentoPay()">Conferma pagamento</button><button class="button" onclick="pagamentoClosePayment()">Annulla</button></footer>
      </div>
    </div>` : "";
}

function pagamentiHtml({ viewer, sections = pagamentoSections(viewer), compact = false }) {
  const content = sections.map((section) => compact
    ? pagamentoSectionHtml(section)
    : `<div class="column is-half-tablet">${pagamentoSectionHtml(section)}</div>`).join("");
  return `${compact ? content : `<div class="columns is-multiline">${content}</div>`}${pagamentoModalHtml(viewer)}`;
}

function pagamentoCard(item) {
  const paid = Boolean(item.pagato_at);
  const overdueDays = item.giorni_scaduto;
  const badge = paid
    ? `Pagato ${fmtDate(item.pagato_at, { dateStyle: "medium" })}`
    : overdueDays ? `In sospeso da ${overdueDays} ${overdueDays === 1 ? "giorno" : "giorni"}` : "Oggi";
  const actor = PagamentoState.cfg.viewer === "nutrizionista"
    ? `<span class="tag">Paziente: ${esc(item.paziente_nome)}</span>`
    : "";
  const discount = item.sconto_cent > 0 ? `<span class="tag is-success is-light">Sconto ${euro(item.sconto_cent)}</span>` : "";
  const action = PagamentoState.cfg.viewer === "nutrizionista" && !paid
    ? `<button class="button is-small is-primary" onclick="pagamentoOpenPayment(${item.appuntamento_id})">Segna come pagato</button>` : "";
  const pendingClass = overdueDays ? " pagamento-card-pending" : "";
  return `<article class="box mb-3${pendingClass}">
    <div class="level is-mobile mb-2"><div class="level-left"><strong>${esc(item.appuntamento_tipo_nome)}</strong></div><div class="level-right"><span class="tag is-light">${esc(badge)}</span></div></div>
    <p class="mb-2">${fmtDate(item.appuntamento_data_ora_inizio, { dateStyle: "medium", timeStyle: "short" })}</p>
    <div class="tags mb-3">${actor}${discount}</div>
    <div class="level is-mobile mb-0"><div class="level-left">${item.sconto_cent > 0 ? `<span class="has-text-grey"><s>${euro(item.prezzo_cent)}</s></span>` : ""}</div><div class="level-right"><strong class="is-size-5">${euro(item.totale_cent)}</strong></div></div>
    ${action ? `<div class="buttons mt-3 mb-0">${action}</div>` : ""}
  </article>`;
}

function pagamentoRender(key) {
  const config = pagamentoActiveSections().find((section) => section[0] === key);
  if (!config) return;
  const section = PagamentoState.panel?.[key] || { items: [], count: 0, totale_cent: 0 };
  const pages = Math.max(1, Math.ceil(section.items.length / PAGAMENTO_PAGE_SIZE));
  PagamentoState.page[key] = Math.min(PagamentoState.page[key] || 0, pages - 1);
  const start = PagamentoState.page[key] * PAGAMENTO_PAGE_SIZE;
  const items = section.items.slice(start, start + PAGAMENTO_PAGE_SIZE);
  $(`pagamento-${key}-list`).innerHTML = items.length
    ? items.map(pagamentoCard).join("")
    : `<div class="notification is-light mb-0">${esc(config[2])}</div>`;
  $(`pagamento-${key}-summary`).textContent = section.count ? `${section.count} · Totale ${euro(section.totale_cent)}` : "";
  $(`pagamento-${key}-page`).textContent = section.items.length ? `${PagamentoState.page[key] + 1} / ${pages}` : "";
  $(`pagamento-${key}-prev`).disabled = PagamentoState.page[key] === 0;
  $(`pagamento-${key}-next`).disabled = PagamentoState.page[key] >= pages - 1;
}

window.pagamentoPage = function pagamentoPage(key, direction) {
  const pages = Math.max(1, Math.ceil((PagamentoState.panel?.[key]?.items.length || 0) / PAGAMENTO_PAGE_SIZE));
  PagamentoState.page[key] = Math.max(0, Math.min((PagamentoState.page[key] || 0) + direction, pages - 1));
  pagamentoRender(key);
};

function pagamentoRenderAll() {
  pagamentoActiveSections().forEach(([key]) => pagamentoRender(key));
}

async function pagamentoRefresh() {
  PagamentoState.panel = await request(PagamentoState.cfg.panelUrl);
  pagamentoRenderAll();
  return PagamentoState.panel;
}

async function montaPagamenti({
  rootId = "pagamenti-root",
  viewer,
  panelUrl,
  panel,
  sections = pagamentoSections(viewer),
  onChanged,
  compact = false,
}) {
  $(rootId).innerHTML = pagamentiHtml({ viewer, sections, compact });
  PagamentoState.cfg = { viewer, panelUrl, sections, onChanged };
  PagamentoState.selected = null;
  PagamentoState.page = Object.fromEntries(sections.map(([key]) => [key, 0]));
  if (panel) {
    PagamentoState.panel = panel;
    pagamentoRenderAll();
    return panel;
  }
  return pagamentoRefresh();
}

window.pagamentoOpenPayment = function pagamentoOpenPayment(appuntamentoId) {
  const item = pagamentoActiveSections()
    .flatMap(([key]) => PagamentoState.panel?.[key]?.items || [])
    .find((entry) => entry.appuntamento_id === appuntamentoId);
  if (!item) return;
  PagamentoState.selected = item;
  $("pagamento-payment-title").textContent = `${item.paziente_nome} · ${item.appuntamento_tipo_nome}`;
  $("pagamento-payment-base").textContent = euro(item.prezzo_cent);
  $("pagamento-payment-discount").value = (item.sconto_cent || 0) / 100;
  openModal("pagamento-payment-modal");
};

window.pagamentoClosePayment = function pagamentoClosePayment() {
  PagamentoState.selected = null;
  closeModal("pagamento-payment-modal");
};

window.pagamentoPay = async function pagamentoPay() {
  if (!PagamentoState.selected) return;
  const discountCent = Math.round(Number($("pagamento-payment-discount").value || 0) * 100);
  if (discountCent < 0 || discountCent > PagamentoState.selected.prezzo_cent) return message("Lo sconto non è valido.");
  try {
    const pagamento = await request(`/pagamenti/${PagamentoState.selected.appuntamento_id}/registra`, { method: "POST", body: JSON.stringify({ sconto_cent: discountCent }) });
    pagamentoClosePayment();
    if (PagamentoState.cfg.onChanged) await PagamentoState.cfg.onChanged();
    else await pagamentoRefresh();
    message(`Pagamento registrato: ${euro(pagamento.totale_cent)}.`, "is-success");
  } catch (err) {
    message(err.message || "Registrazione del pagamento non riuscita");
  }
};


const PROFILE_URL = { A: "/web/admin/", N: "/web/nutrizionista/", P: "/web/paziente/" };
const profileUrl = (role) => PROFILE_URL[role] || "/web/login.html";

// chiamate API con aggiunta automatica del Token Bearer
async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;

  const response = await fetch(API + path, { ...options, headers });

  if (response.status === 401 && path !== "/auth/login") {
    sessionStorage.clear();
    location.replace("/web/login.html");
    throw new Error("Sessione scaduta");
  }

  const data = response.status === 204 ? null : await response.json().catch(() => ({}));

  if (!response.ok) {
    const err = new Error(data.detail || "Operazione non riuscita");
    err.status = response.status;
    err.data = data;
    throw err;
  }
  return data;
}

// Mostra un messaggio nel box #message della pagina/sezione corrente
function message(text, type = "is-danger") {
  const box = $("message");
  if (!box) return;
  box.className = `notification ${type}`;
  box.textContent = text;
  box.hidden = false;
}

function renderCopyLink(container, url, title = "Link per impostare la password") {
  if (!container) return;
  container.innerHTML = `<p class="mb-2"><strong>${esc(title)}</strong></p>
    <div class="field has-addons mb-0">
      <div class="control is-expanded"><input class="input" readonly></div>
      <div class="control"><button class="button is-link" type="button">Copia link</button></div>
    </div>`;
  const input = container.querySelector("input");
  const button = container.querySelector("button");
  input.value = url;
  button.onclick = async () => {
    try { await navigator.clipboard.writeText(url); }
    catch (_) { input.select(); document.execCommand("copy"); }
    button.textContent = "Copiato";
  };
  container.hidden = false;
}

function linkMessage(url, title) {
  const box = $("message");
  if (!box) return;
  box.className = "notification is-success";
  renderCopyLink(box, url, title);
}

// Autenticazione

async function requireAuth(role) {
  if (!token()) {
    location.replace("/web/login.html");
    return null;
  }

  let current;
  try {
    current = await request("/auth/me"); // conferma la validità reale della sessione sul server
  } catch (_) {
    return null; // request() ha già pulito la sessione e reindirizzato al login
  }

  if (role && current.ruolo !== role) {
    sessionStorage.clear();
    location.replace("/web/login.html");
    return null;
  }

  sessionStorage.setItem("user", JSON.stringify(current));
  return current;
}

// Termina la sessione corrente sul server e riporta al login
async function logout() {
  try {
    await request("/auth/logout", { method: "POST" });
  } catch (_) {
    // ignora errori di rete sul logout
  }
  sessionStorage.clear();
  location.replace("/web/login.html");
}

// Come logout(), ma revoca tutte le sessioni attive dell'utente su tutti i dispositivi
async function logoutAll() {
  if (!confirm("Disconnettere tutti i dispositivi? Dovrai effettuare nuovamente il login ovunque.")) return;
  try {
    await request("/auth/logout-all", { method: "POST" });
  } catch (_) {
    // ignora errori di rete
  }
  sessionStorage.clear();
  location.replace("/web/login.html");
}

function initSettingsSection() {
  $("settings-password-form").onsubmit = async (event) => {
    event.preventDefault();
    if ($("settings-new-password").value !== $("settings-confirm-password").value) {
      return message("Le password non coincidono");
    }
    try {
      await request("/me/password", {
        method: "PUT",
        body: JSON.stringify({
          password_attuale: $("settings-current-password").value,
          nuova_password: $("settings-new-password").value,
          conferma_nuova_password: $("settings-confirm-password").value,
        }),
      });
      sessionStorage.clear();
      location.replace("/web/login.html");
    } catch (error) {
      message(error.message);
    }
  };
}

// Routing
const SECTION_DEFS = {
  nutrizionisti: { label: "Nutrizionisti", icon: "fa-user-doctor" },
  pazienti: { label: "Pazienti", icon: "fa-users" },
  configurazione: { label: "Configurazione", icon: "fa-sliders" },
  profilo: { label: "Il mio profilo", icon: "fa-id-card" },
  dieta: { label: "Dieta", icon: "fa-utensils" },
  "template-diete": { label: "Configurazione template diete", icon: "fa-clipboard-list" },
  prenotazioni: { label: "Calendario", icon: "fa-calendar-days" },
  home: { label: "Home", icon: "fa-house" },
  pagamenti: { label: "Pagamenti", icon: "fa-file-invoice" },
  "configura-appuntamenti": { label: "Configura appuntamenti", icon: "fa-sliders" },
  progressi: { label: "Progressi", icon: "fa-chart-line" },
  disponibilita: { label: "Disponibilità", icon: "fa-clock" },
  impostazioni: { label: "Impostazioni", icon: "fa-gear" },
};

const SECTIONS_BY_ROLE = {
  A: ["nutrizionisti", "pazienti", "configurazione", "impostazioni"],
  N: ["home", "pazienti", "pagamenti", "disponibilita", "configura-appuntamenti", "template-diete", "impostazioni"],
  P: ["home", "profilo", "dieta", "prenotazioni", "progressi", "pagamenti", "impostazioni"],
};

function sectionsForRole(role) {
  return (SECTIONS_BY_ROLE[role] || []).map((id) => ({ id, ...SECTION_DEFS[id] }));
}

let currentRole = null;

function renderTabs(activeId) {
  const tabs = $("tabs");
  const ul = document.createElement("ul");

  for (const { id, label, icon } of sectionsForRole(currentRole)) {
    const li = document.createElement("li");
    if (id === activeId) li.className = "is-active";

    const a = document.createElement("a");
    a.innerHTML = `<span class="icon"><i class="fa-solid ${icon}"></i></span><span>${label}</span>`;
    a.onclick = () => showSection(id);

    li.append(a);
    ul.append(li);
  }

  tabs.replaceChildren(ul);
}

async function showSection(id) {
  renderTabs(id);

  const content = $("content");
  const sectionUrl = id === "impostazioni" ? "/web/account%20e%20sicurezza/sicurezza.html" : `sezioni/${id}.html`;
  const response = await fetch(`${sectionUrl}?v=${ASSET_VERSION}`, { cache: "no-store" });
  content.innerHTML = response.ok ? await response.text() : "<p>Sezione non trovata.</p>";

  content.querySelectorAll("script").forEach((old) => {
    const s = document.createElement("script");
    if (old.src) s.src = old.src;
    else s.textContent = old.textContent;
    old.replaceWith(s);
  });
}

async function initTabsPage(role, title) {
  document.title = title;
  $("page-title").textContent = title;
  currentRole = role;
  const current = await requireAuth(role);
  if (!current) return;
  const initialSection = role === "A" ? "nutrizionisti" : "home";
  showSection(initialSection);
}

// ezione condivisa Misurazioni
const McState = { weightChart: null, fatChart: null, plicheChart: null, storicoPage: 0, storicoUrlBase: null };

// Avanzamento condiviso tra Home paziente e Misurazioni
function misurazioniProgressHtml(prefix, sectionClass = "") {
  return `<progress id="${prefix}-progress-bar" class="progress is-primary ${sectionClass}" value="0" max="100">0%</progress>`;
}

function renderMisurazioniProgress(prefix, data) {
  const progress = data.avanzamento;
  const percentage = progress?.percentuale == null
    ? 0
    : Math.max(0, Math.min(100, progress.percentuale));

  $(`${prefix}-progress-bar`).value = percentage;
}

// 'mostraStorico' aggiunge la tabella "Ultime misurazioni" solo per il nutrizionista
function misurazioniCorporeeHtml(mostraStorico) {
  return `
    <div id="mc-cards" class="columns is-multiline mb-2"></div>

    ${misurazioniProgressHtml("mc")}

    <div class="columns is-variable is-4">
      <div class="column is-6"><div class="box"><h4 class="title is-6">Andamento peso</h4><canvas id="mc-weight-chart" height="120"></canvas></div></div>
      <div class="column is-6"><div class="box"><h4 class="title is-6">Andamento massa grassa</h4><canvas id="mc-fat-chart" height="120"></canvas></div></div>
    </div>

    <div class="box"><h4 class="title is-6">Storico pliche cutanee</h4><canvas id="mc-pliche-chart" height="90"></canvas></div>

    ${mostraStorico ? `
    <div class="box">
      <div class="level mb-3">
        <div class="level-left"><h4 class="title is-6 mb-0">Ultime misurazioni</h4></div>
        <div class="level-right"><div class="buttons has-addons mb-0">
          <button class="button is-small" onclick="mcPagina(-1)">← Precedenti</button>
          <button class="button is-small" onclick="mcPagina(1)">Successive →</button>
        </div></div>
      </div>
      <div class="table-container"><table class="table is-fullwidth is-striped">
        <thead><tr><th>Data</th><th>Peso</th><th>Grassa</th><th>BMI</th><th>Pliche e circonferenze</th><th>Note</th></tr></thead>
        <tbody id="mc-storico-body"></tbody>
      </table></div>
    </div>` : ""}
  `;
}

function mcCard(titolo, valore, icon) {
  return homeKpiHtml(titolo, valore ?? "-", "", icon);
}

function mcSerie(data, metrica) {
  return (data?.serie || []).find((item) => item.metrica === metrica)?.punti || [];
}

function mcChart(canvasId, existing, serie, label, { maintainAspectRatio = true } = {}) {
  if (existing) existing.destroy();
  return new Chart($(canvasId), {
    type: "line",
    data: { labels: (serie || []).map((p) => p.data), datasets: [{ label, data: (serie || []).map((p) => p.valore), tension: .25 }] },
    options: { maintainAspectRatio, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } },
  });
}

function mcDettagliRiga(m) {
  const pliche = [["Tricipitale", m.plica_tricipitale_mm], ["Bicipitale", m.plica_bicipitale_mm], ["Sottoscapolare", m.plica_sottoscapolare_mm], ["Sovrailiaca", m.plica_sovrailiaca_mm], ["Ombelicale", m.plica_ombelicale_mm], ["Pettorale", m.plica_pettorale_mm], ["Coscia", m.plica_coscia_mm]];
  const circs = [["Vita", m.circ_vita_cm], ["Fianchi", m.circ_fianchi_cm], ["Bicipite", m.circ_bicipite_cm], ["Coscia", m.circ_coscia_cm], ["Torace", m.circ_torace_cm], ["Addome", m.circ_addome_cm]];
  const tags = (items, unit) => items.filter(([, v]) => v != null).map(([k, v]) => `<span class="tag is-light mb-1">${esc(k)}: ${v} ${unit}</span>`).join(" ");
  return `<div class="mb-1"><strong class="is-size-7">Pliche</strong><br>${tags(pliche, "mm") || '<span class="has-text-grey is-size-7">Nessuna</span>'}</div><div><strong class="is-size-7">Circonferenze</strong><br>${tags(circs, "cm") || '<span class="has-text-grey is-size-7">Nessuna</span>'}</div>`;
}

async function mcCaricaStorico() {
  const skip = McState.storicoPage * 10;
  const rows = await request(`${McState.storicoUrlBase}?skip=${skip}&limit=10&order=desc`);
  $("mc-storico-body").innerHTML = rows.length
    ? rows.map((m) => `<tr><td>${m.data ?? "-"}</td><td>${m.peso_kg ?? "-"} kg</td><td>${m.massa_grassa_perc ?? "-"}%</td><td>${m.bmi ?? "-"}</td><td>${mcDettagliRiga(m)}</td><td>${m.note_nutrizionista ? `<strong>Interna:</strong> ${esc(m.note_nutrizionista)}` : "-"}${m.note_paziente ? `<br><strong>Paziente:</strong> ${esc(m.note_paziente)}` : ""}</td></tr>`).join("")
    : '<tr><td colspan="6" class="has-text-grey">Nessuna misurazione.</td></tr>';
}

window.mcPagina = async function mcPagina(delta) {
  McState.storicoPage = Math.max(0, McState.storicoPage + delta);
  await mcCaricaStorico();
};

// Carica progressi e serie storiche
async function caricaMisurazioniCorporee({ progressiUrl, storicoUrlBase, mostraStorico }) {
  const d = await request(progressiUrl);

  $("mc-cards").innerHTML = [
    mcCard("Peso iniziale", d.partenza ? `${d.partenza.peso_kg} kg` : null, "fa-flag-checkered"),
    mcCard("Peso attuale", d.attuale ? `${d.attuale.peso_kg} kg` : null, "fa-weight-scale"),
    mcCard("Peso obiettivo", d.peso_obiettivo_kg ? `${d.peso_obiettivo_kg} kg` : null, "fa-bullseye"),
    mcCard("Misurazioni", d.avanzamento?.numero_misurazioni ?? null, "fa-ruler"),
  ].join("");

  renderMisurazioniProgress("mc", d);

  McState.weightChart = mcChart("mc-weight-chart", McState.weightChart, mcSerie(d, "peso"), "Peso kg");
  McState.fatChart = mcChart("mc-fat-chart", McState.fatChart, mcSerie(d, "massa_grassa"), "Massa grassa %");

  const pliche = (d.serie || []).filter((serie) => serie.metrica.startsWith("plica_"));
  const labels = [...new Set(pliche.flatMap((serie) => serie.punti.map((p) => p.data)))].sort();

  if (McState.plicheChart) McState.plicheChart.destroy();
  McState.plicheChart = new Chart($("mc-pliche-chart"), {
    type: "line",
    data: {
      labels,
      datasets: pliche.map((serie) => {
        const valori = new Map(serie.punti.map((p) => [p.data, p.valore]));
        return { label: serie.metrica.replace("plica_", ""), data: labels.map((data) => valori.get(data) ?? null), tension: .2 };
      }),
    },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: false } } },
  });

  if (mostraStorico) {
    McState.storicoUrlBase = storicoUrlBase;
    McState.storicoPage = 0;
    await mcCaricaStorico();
  }
}

// Sezione condivisa Appuntamenti
const ApptState = {
  cfg: null,
  panel: null,
  page: { prossimi: 0, daConfermare: 0, storicoRichieste: 0, storicoEffettuati: 0, daChiudere: 0, assenzeDisdette: 0 },
  bookingTypes: [],
  selectedType: null,
  selectedSlot: null,
  weekStart: null,
  slotsByDay: {},
};

function apptDateTimeIt(value) {
  return fmtDate(value, { dateStyle: "medium", timeStyle: "short" });
}

function apptLocalIsoDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function apptMondayOf(date) {
  const value = new Date(date);
  value.setHours(0, 0, 0, 0);
  const day = value.getDay() || 7;
  value.setDate(value.getDate() - day + 1);
  return value;
}

// Il backend restituisce l’elenco delle azioni consentite
function appointmentActionsHtml(item) {
  const actionHtml = {
    accetta: () => `<button class="button is-small is-success" onclick="apptAction(${item.id}, 'accetta', false)">Accetta</button>`,
    rifiuta: () => `<button class="button is-small is-danger is-light" onclick="apptAction(${item.id}, 'rifiuta', true)">Rifiuta</button>`,
    annulla: () => `<button class="button is-small is-warning is-light" onclick="apptCancel(${item.id})">Annulla</button>`,
    eseguito: () => `<button class="button is-small is-info" onclick="apptAction(${item.id}, 'eseguito', false)">Eseguito</button>`,
    "mancata-presenza": () => `<button class="button is-small is-danger" onclick="apptAction(${item.id}, 'mancata-presenza', true)">Mancata presenza</button>`,
  };
  return (item.azioni_consentite || [])
    .map((azione) => actionHtml[azione]?.() || "")
    .join(" ");
}

function appointmentCard(item, viewer) {
  const actions = appointmentActionsHtml(item);
  const endTime = item.data_ora_fine ? new Date(item.data_ora_fine).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : "-";
  const titolo = item.tipo?.nome || "Appuntamento";
  const durata = item.tipo?.durata_minuti;
  const prezzo = item.tipo?.prezzo_cent;
  return `<article class="box mb-3">
    <div class="level is-mobile mb-2">
      <div class="level-left"><strong>${esc(titolo)}</strong></div>
      <div class="level-right"><span class="tag is-light">${esc(item.stato_label)}</span></div>
    </div>
    <p class="mb-2">${apptDateTimeIt(item.data_ora_inizio)} – ${endTime}</p>
    <div class="tags mb-2">
      ${viewer === "nutrizionista" ? `<span class="tag">Paziente: ${esc(item.paziente_nome || "-")}</span>` : ""}
      ${durata != null ? `<span class="tag">${durata} min</span>` : ""}
      ${prezzo != null ? `<span class="tag">${euro(prezzo, true)}</span>` : ""}
    </div>
    ${item.motivo ? `<div class="notification is-light py-3"><strong>Motivo:</strong> ${esc(item.motivo)}</div>` : ""}
    ${viewer === "nutrizionista" && item.note_nutrizionista ? `<p><strong>Note professionista:</strong> ${esc(item.note_nutrizionista)}</p>` : ""}
    ${actions ? `<div class="buttons mt-3 mb-0">${actions}</div>` : ""}
  </article>`;
}

const APPT_PAGINA_DIMENSIONE = 5;
const APPT_SEZIONI = {
  prossimi: {
    key: "prossimi_appuntamenti",
    title: "Prossimi appuntamenti",
    listId: "appt-prossimi",
    pageId: "appt-prossimi-page",
    emptyText: "Nessun appuntamento programmato.",
  },
  daConfermare: {
    key: "richieste_da_confermare",
    title: "Richieste da confermare",
    listId: "appt-daConfermare",
    pageId: "appt-daConfermare-page",
    emptyText: "Nessuna richiesta da confermare.",
  },
  storicoRichieste: {
    key: "storico_richieste",
    title: "Storico richieste",
    listId: "appt-storicoRichieste",
    pageId: "appt-storicoRichieste-page",
    emptyText: "Nessuna richiesta nello storico.",
  },
  storicoEffettuati: {
    key: "storico_appuntamenti_effettuati",
    title: "Storico appuntamenti effettuati",
    listId: "appt-storicoEffettuati",
    pageId: "appt-storicoEffettuati-page",
    emptyText: "Nessun appuntamento effettuato.",
  },
  daChiudere: {
    key: "appuntamenti_da_chiudere",
    title: "Appuntamenti da chiudere",
    listId: "appt-daChiudere",
    pageId: "appt-daChiudere-page",
    emptyText: "Nessun appuntamento concluso da classificare.",
  },
  assenzeDisdette: {
    key: "storico_assenze_disdette",
    title: "Disdette tardive e mancate presenze",
    listId: "appt-assenzeDisdette",
    pageId: "appt-assenzeDisdette-page",
    emptyText: "Nessuna disdetta tardiva o mancata presenza.",
  },
};

function appointmentSectionHtml(chiave, { title = "", sectionClass = "" } = {}) {
  const config = APPT_SEZIONI[chiave];
  if (!config) return "";
  return `<section class="box ${sectionClass}">
    <h3 class="title is-5">${esc(title || config.title)}</h3>
    <div id="${config.listId}"></div>
    <div class="level is-mobile mt-3">
      <div class="level-left"><button id="appt-${chiave}-prev" class="button is-small is-light" onclick="apptPaginaPrecedente('${chiave}')">← Precedenti</button></div>
      <div class="level-item" id="${config.pageId}"></div>
      <div class="level-right"><button id="appt-${chiave}-next" class="button is-small is-light" onclick="apptPaginaSuccessiva('${chiave}')">Successivi →</button></div>
    </div>
  </section>`;
}

function appuntamentiHtml({ mostraWizard = true, mostraSezioniNutrizionista = false } = {}) {
  return `
    ${mostraWizard ? `
    <section class="box mb-5" aria-labelledby="appt-new-request-title">
      <h3 id="appt-new-request-title" class="title is-4">Nuova richiesta</h3>

      <div id="appt-step-types">
        <h4 class="title is-6">Scegli la tipologia</h4>
        <div id="appt-types" class="columns is-multiline"></div>
      </div>

      <div id="appt-step-slots" hidden>
        <h4 class="title is-6">Scegli giorno e orario</h4>
        <div class="level is-mobile mb-4">
          <div class="level-left"><button class="button is-small is-light" type="button" onclick="apptResetType()">← Cambia tipologia</button></div>
        </div>
        <div class="level is-mobile mb-4">
          <div class="level-left"><button id="appt-week-prev" class="button is-small is-light" type="button" onclick="apptChangeWeek(-7)">← Precedente</button></div>
          <div class="level-right"><button class="button is-small is-light" type="button" onclick="apptChangeWeek(7)">Successiva →</button></div>
        </div>
        <div id="appt-week"></div>
      </div>

      <div id="appt-step-summary" hidden>
        <div class="columns">
          <div class="column is-7"><div id="appt-selection" class="content"></div></div>
          <div class="column is-5">
            <div class="buttons">
              <button class="button is-success" type="button" onclick="apptSubmit()">Invia richiesta</button>
              <button class="button is-light" type="button" onclick="apptBackToSlots()">Cambia orario</button>
            </div>
          </div>
        </div>
      </div>
    </section>` : ""}

    <div class="columns">
      <div class="column is-half">${appointmentSectionHtml("prossimi")}</div>
      <div class="column is-half">${appointmentSectionHtml("daConfermare")}</div>
    </div>

    <div class="columns">
      <div class="column is-half">${appointmentSectionHtml("storicoRichieste")}</div>
      <div class="column is-half">${appointmentSectionHtml("storicoEffettuati")}</div>
    </div>

    ${mostraSezioniNutrizionista ? `<div class="columns"><div class="column is-half">${appointmentSectionHtml("daChiudere")}</div><div class="column is-half">${appointmentSectionHtml("assenzeDisdette")}</div></div>` : ""}
  `;
}

function apptRenderSezione(chiave) {
  const config = APPT_SEZIONI[chiave];
  const list = config && $(config.listId);
  const page = config && $(config.pageId);
  if (!config || !list || !page) return;

  const items = (ApptState.panel && ApptState.panel[config.key]) || [];
  const totalePagine = Math.max(1, Math.ceil(items.length / APPT_PAGINA_DIMENSIONE));
  if (ApptState.page[chiave] >= totalePagine) ApptState.page[chiave] = totalePagine - 1;
  const inizio = ApptState.page[chiave] * APPT_PAGINA_DIMENSIONE;
  const paginaItems = items.slice(inizio, inizio + APPT_PAGINA_DIMENSIONE);

  list.innerHTML = paginaItems.length
    ? paginaItems.map((item) => appointmentCard(item, ApptState.cfg.viewer)).join("")
    : `<div class="notification is-light mb-0">${esc(config.emptyText)}</div>`;
  page.textContent = items.length ? `${ApptState.page[chiave] + 1} / ${totalePagine}` : "";
  const prev = $(`appt-${chiave}-prev`);
  const next = $(`appt-${chiave}-next`);
  if (prev) prev.disabled = ApptState.page[chiave] === 0;
  if (next) next.disabled = ApptState.page[chiave] >= totalePagine - 1;
}

window.apptPaginaPrecedente = function apptPaginaPrecedente(chiave) {
  if (ApptState.page[chiave] > 0) ApptState.page[chiave] -= 1;
  apptRenderSezione(chiave);
};

window.apptPaginaSuccessiva = function apptPaginaSuccessiva(chiave) {
  const items = (ApptState.panel && ApptState.panel[APPT_SEZIONI[chiave].key]) || [];
  const totalePagine = Math.max(1, Math.ceil(items.length / APPT_PAGINA_DIMENSIONE));
  if (ApptState.page[chiave] < totalePagine - 1) ApptState.page[chiave] += 1;
  apptRenderSezione(chiave);
};

function apptRenderPanel(panel) {
  ApptState.panel = panel || {};
  Object.keys(APPT_SEZIONI).forEach(apptRenderSezione);
}

async function apptRefreshPanel() {
  apptRenderPanel(await request(ApptState.cfg.panelUrl));
}

window.apptAction = async function apptAction(id, action, needsReason) {
  let body;
  if (needsReason) {
    const reason = prompt("Inserisci la motivazione obbligatoria:");
    if (!reason || !reason.trim()) return;
    body = JSON.stringify({ motivo: reason.trim() });
  }
  try {
    await request(`${ApptState.cfg.actionUrlBase}/${id}/${action}`, { method: "PATCH", ...(body ? { body } : {}) });
    if (ApptState.cfg.onChanged) await ApptState.cfg.onChanged();
    else await apptRefreshPanel();
  } catch (err) {
    message(err.message || "Operazione non riuscita");
  }
};

window.apptCancel = async function apptCancel(id) {
  const item = Object.values(ApptState.panel || {}).flat().find((entry) => entry.id === id);
  const warning = item?.testo_avviso_annullamento || "";
  if (warning && !confirm(warning)) return;
  const reason = prompt("Inserisci la motivazione obbligatoria:");
  if (!reason || !reason.trim()) return;
  try {
    await request(`${ApptState.cfg.actionUrlBase}/${id}/annulla`, { method: "PATCH", body: JSON.stringify({ motivo: reason.trim() }) });
    if (ApptState.cfg.onChanged) await ApptState.cfg.onChanged();
    else await apptRefreshPanel();
  } catch (err) {
    message(err.message || "Annullamento non riuscito");
  }
};

// Wizard nuova richiesta di appuntamento

function apptShowStep(step) {
  $("appt-step-types").hidden = step !== "types";
  $("appt-step-slots").hidden = step !== "slots";
  $("appt-step-summary").hidden = step !== "summary";
}

function apptRenderTypes() {
  $("appt-types").innerHTML = ApptState.bookingTypes.length
    ? ApptState.bookingTypes.map((type) => `<div class="column is-one-third-desktop is-half-tablet">
        <button type="button" class="button is-link is-light is-fullwidth" onclick="apptSelectType(${type.id})">
          ${esc(type.nome)} · ${type.durata} min · ${euro(type.prezzo_base_cent, true)}
        </button>
      </div>`).join("")
    : '<div class="column"><div class="notification is-light">Nessuna tipologia prenotabile</div></div>';
}

window.apptSelectType = async function apptSelectType(id) {
  ApptState.selectedType = ApptState.bookingTypes.find((type) => type.id === id);
  ApptState.selectedSlot = null;
  ApptState.weekStart = ApptState.weekStart || apptMondayOf(new Date());
  apptShowStep("slots");
  await apptLoadWeek();
};

window.apptResetType = function apptResetType() {
  ApptState.selectedType = null;
  ApptState.selectedSlot = null;
  apptShowStep("types");
};

window.apptChangeWeek = async function apptChangeWeek(days) {
  ApptState.weekStart.setDate(ApptState.weekStart.getDate() + days);
  await apptLoadWeek();
};

async function apptLoadWeek() {
  if (!ApptState.selectedType) return;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  $("appt-week-prev").disabled = ApptState.weekStart <= apptMondayOf(today);

  try {
    const slots = await request(`${ApptState.cfg.slotUrl}?tipo_appuntamento_id=${ApptState.selectedType.id}&data_da=${apptLocalIsoDate(ApptState.weekStart)}`);
    ApptState.slotsByDay = {};
    slots.forEach((slot) => {
      const key = apptLocalIsoDate(new Date(slot.data_ora_inizio));
      (ApptState.slotsByDay[key] ||= []).push(slot);
    });

    $("appt-week").innerHTML = Array.from({ length: 7 }, (_, index) => {
      const day = new Date(ApptState.weekStart);
      day.setDate(day.getDate() + index);
      const key = apptLocalIsoDate(day);
      const daySlots = ApptState.slotsByDay[key] || [];
      const buttons = daySlots.length
        ? daySlots.map((slot, slotIndex) => `<button class="button is-small is-info is-light" onclick="apptChooseSlot('${key}', ${slotIndex})">${new Date(slot.data_ora_inizio).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}</button>`).join("")
        : '<span class="has-text-grey is-size-7">No disponibilità!</span>';
      const weekday = new Intl.DateTimeFormat("it-IT", { weekday: "long" }).format(day);
      const date = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long" }).format(day);
      return `<div class="box py-3 mb-3"><div class="columns is-mobile is-vcentered"><div class="column is-3-tablet is-4-mobile"><strong class="is-capitalized">${weekday}</strong><br><span class="is-size-7 has-text-grey">${date}</span></div><div class="column"><div class="buttons are-small mb-0">${buttons}</div></div></div></div>`;
    }).join("");
  } catch (err) {
    message(err.message || "Impossibile caricare gli slot");
  }
}

window.apptChooseSlot = function apptChooseSlot(dayKey, index) {
  ApptState.selectedSlot = ApptState.slotsByDay[dayKey][index];
  apptShowStep("summary");
  const endTime = new Date(ApptState.selectedSlot.data_ora_fine).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  $("appt-selection").innerHTML = `<h5>${esc(ApptState.selectedType.nome)}</h5>
    <p><strong>Data e ora:</strong> ${apptDateTimeIt(ApptState.selectedSlot.data_ora_inizio)} – ${endTime}</p>
    <p><strong>Durata:</strong> ${ApptState.selectedType.durata} minuti</p>
    <p><strong>Prezzo:</strong> ${euro(ApptState.selectedType.prezzo_base_cent, true)}</p>`;
};

window.apptBackToSlots = function apptBackToSlots() {
  ApptState.selectedSlot = null;
  apptShowStep("slots");
};

window.apptSubmit = async function apptSubmit() {
  if (!ApptState.selectedType || !ApptState.selectedSlot) return;
  try {
    await request(ApptState.cfg.createUrl, {
      method: "POST",
      body: JSON.stringify({
        ...(ApptState.cfg.extraCreatePayload ? ApptState.cfg.extraCreatePayload() : {}),
        tipo_appuntamento_id: ApptState.selectedType.id,
        data_ora_inizio: ApptState.selectedSlot.data_ora_inizio,
      }),
    });
    apptResetType();
    await apptRefreshPanel();
    if (ApptState.cfg.onSubmitted) ApptState.cfg.onSubmitted();
  } catch (err) {
    message(err.message || "Invio della richiesta non riuscito");
  }
};

// Inizializza pannello secondo la configurazione data:
//  - viewer: "paziente" o "nutrizionista"
//  - panelUrl, actionUrlBase: endpoint del pannello e delle azioni (accetta/rifiuta/annulla/...)
//  - tipiUrl, slotUrl, createUrl: endpoint del wizard (omessi se mostraWizard=false)
//  - extraCreatePayload: funzione che ritorna campi aggiuntivi per la creazione (es. paziente_id)
//  - onSubmitted: callback dopo l'invio riuscito di una richiesta
async function caricaAppuntamenti(cfg) {
  ApptState.cfg = cfg;
  ApptState.page = { prossimi: 0, daConfermare: 0, storicoRichieste: 0, storicoEffettuati: 0, daChiudere: 0, assenzeDisdette: 0 };
  ApptState.bookingTypes = [];
  ApptState.selectedType = null;
  ApptState.selectedSlot = null;
  ApptState.weekStart = null;


  if (cfg.tipiUrl) {
    const [panel, types] = await Promise.all([request(cfg.panelUrl), request(cfg.tipiUrl)]);
    apptRenderPanel(panel);
    ApptState.bookingTypes = types;
    apptRenderTypes();
    ApptState.weekStart = apptMondayOf(new Date());
  } else {
    apptRenderPanel(await request(cfg.panelUrl));
  }
}

// DietEditor, editor condiviso da template e diete assegnate
window.DietEditor = (function DietEditorFactory() {
  const DAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];

  function textValue(value, { trim = true, emptyToNull = false, emptyAs = "" } = {}) {
    if (value == null) return emptyToNull ? null : emptyAs;
    const result = trim ? String(value).trim() : String(value);
    return emptyToNull && result === "" ? null : result;
  }

  function emptyFood(descrizione = "") {
    return { descrizione };
  }

  function emptyOption() {
    return { alimenti: [emptyFood()] };
  }

  function mapPasti(pasti, tipo, preserveForEdit = false) {
    return (pasti || []).map((pasto) => ({
      giorno_settimana: tipo === "S" ? Number(pasto.giorno_settimana ?? 0) : null,
      nome: textValue(pasto.nome, { trim: !preserveForEdit }),
      note: textValue(pasto.note, { trim: !preserveForEdit, emptyToNull: !preserveForEdit }),
      opzioni: (pasto.opzioni || []).map((opzione) => ({
        alimenti: (opzione.alimenti || []).map((alimento) => ({
          descrizione: textValue(alimento.descrizione, { trim: !preserveForEdit }),
        })),
      })),
    }));
  }

  function validatePasti(tipo, pasti) {
    if (!pasti.length) return "Inserisci almeno un pasto.";
    if (tipo === "S") {
      const presenti = new Set(pasti.map((pasto) => Number(pasto.giorno_settimana)));
      const mancanti = DAYS.filter((_, giorno) => !presenti.has(giorno));
      if (mancanti.length) return `Inserisci almeno un pasto in: ${mancanti.join(", ")}.`;
    }
    for (const pasto of pasti) {
      if (!textValue(pasto.nome)) return "Ogni pasto deve avere un nome.";
      if (!(pasto.opzioni || []).length) return `Il pasto ${pasto.nome || "-"} deve avere almeno un'opzione.`;
      for (const opzione of pasto.opzioni) {
        if (!(opzione.alimenti || []).length) return `Ogni opzione del pasto ${pasto.nome || "-"} deve avere almeno un alimento.`;
        if (opzione.alimenti.some((alimento) => !textValue(alimento.descrizione))) {
          return "Ogni alimento deve avere una descrizione.";
        }
      }
    }
    return "";
  }

  class DietEditor {
    constructor({ containerId, kind, mode = "create", data = null, templates = [] }) {
      this.container = $(containerId);
      if (!this.container) throw new Error(`Contenitore editor dieta non trovato: ${containerId}`);
      this.kind = kind;
      this.mode = mode;
      this.readOnly = mode === "read";
      this.templates = templates;
      this.selectedDay = 0;
      this.templateId = "";
      this.state = DietEditor.normalise(data, kind);
      this._bindEvents();
    }

    static normalise(data, kind) {
      const tipo = data?.tipo || "G";
      return {
        id: data?.id || null,
        nome: data?.nome || "",
        tipo,
        note: data?.note || "",
        note_nutrizionista: kind === "assigned" ? (data?.note_nutrizionista || "") : "",
        considerazioni_finali: kind === "assigned" ? (data?.considerazioni_finali || "") : "",
        stato: data?.stato || null,
        pasti: mapPasti(data?.pasti || [], tipo, true),
      };
    }

    static buildPayload(data, kind = "template") {
      const normalised = DietEditor.normalise(data, kind);
      const payload = {
        nome: textValue(normalised.nome),
        tipo: normalised.tipo,
        note: textValue(normalised.note, { emptyToNull: true }),
        pasti: mapPasti(normalised.pasti, normalised.tipo),
      };
      if (kind === "assigned") {
        payload.note_nutrizionista = textValue(normalised.note_nutrizionista, { emptyToNull: true });
      }
      return payload;
    }

    _bindEvents() {
      this.container.oninput = (event) => {
        const input = event.target.closest("[data-diet-path]");
        if (!input) return;
        this._setPath(input.dataset.dietPath, input.value);
      };

      this.container.onchange = async (event) => {
        const typeSelect = event.target.closest("[data-diet-type]");
        if (typeSelect) {
          this.setType(typeSelect.value);
          return;
        }
        const templateSelect = event.target.closest("[data-diet-template]");
        if (templateSelect) {
          await this.applyTemplate(templateSelect.value);
        }
      };

      this.container.onclick = (event) => {
        const action = event.target.closest("[data-diet-action]");
        if (!action) return;
        event.preventDefault();
        if (this.readOnly && action.dataset.dietAction !== "day") return;
        const meal = Number(action.dataset.meal);
        const option = Number(action.dataset.option);
        const food = Number(action.dataset.food);
        switch (action.dataset.dietAction) {
          case "day": this.selectedDay = Number(action.dataset.day); break;
          case "add-meal": this.state.pasti.push({ giorno_settimana: this.state.tipo === "S" ? this.selectedDay : null, nome: "", note: "", opzioni: [emptyOption()] }); break;
          case "remove-meal": this.state.pasti.splice(meal, 1); break;
          case "add-option": this.state.pasti[meal].opzioni.push(emptyOption()); break;
          case "remove-option": this.state.pasti[meal].opzioni.splice(option, 1); break;
          case "add-food": this.state.pasti[meal].opzioni[option].alimenti.push(emptyFood()); break;
          case "remove-food": this.state.pasti[meal].opzioni[option].alimenti.splice(food, 1); break;
          default: return;
        }
        this.render(2);
      };
    }

    _setPath(path, value) {
      const parts = path.split(".").map((part) => /^\d+$/.test(part) ? Number(part) : part);
      let current = this.state;
      for (let index = 0; index < parts.length - 1; index += 1) current = current[parts[index]];
      current[parts.at(-1)] = value;
    }

    setType(value) {
      if (!["G", "S"].includes(value)) return;
      this.state.tipo = value;
      this.selectedDay = 0;
      this.state.pasti.forEach((pasto) => {
        pasto.giorno_settimana = value === "S" ? (pasto.giorno_settimana ?? 0) : null;
      });
      this.render(1);
    }

    async applyTemplate(templateId) {
      this.templateId = templateId;
      if (!templateId) return;
      try {
        const template = await request(`/diete/templates/${templateId}`);
        this.state.nome = template.nome || "";
        this.state.tipo = template.tipo;
        this.state.note = template.note || "";
        this.state.pasti = mapPasti(template.pasti, template.tipo, true);
        this.selectedDay = 0;
        this.render(1);
      } catch (error) {
        message(error.message || "Impossibile caricare il template");
      }
    }

    validateStep(step) {
      if (step === 1) {
        if (!textValue(this.state.nome)) return this.kind === "template" ? "Il nome template è obbligatorio." : "Il nome dieta è obbligatorio.";
        if (!["G", "S"].includes(this.state.tipo)) return "Il tipo di dieta è obbligatorio.";
      }
      if (step === 2) return validatePasti(this.state.tipo, this.state.pasti);
      return "";
    }

    validateAll() {
      return this.validateStep(1) || this.validateStep(2);
    }

    payload(extra = {}) {
      return { ...DietEditor.buildPayload(this.state, this.kind), ...extra };
    }

    render(step) {
      this.container.innerHTML = step === 1
        ? this._renderDetails()
        : step === 2
          ? this._renderMeals()
          : this._renderFinal();
    }

    _renderDetails() {
      const disabled = this.readOnly ? " disabled" : "";
      const templatePrefill = this.kind === "assigned" && this.mode === "create" && this.templates.length
        ? `<div class="field"><label class="label">Precompila da template (facoltativo)</label><div class="select is-fullwidth"><select data-diet-template><option value="">Nessun template</option>${this.templates.map((template) => `<option value="${template.id}" ${String(this.templateId) === String(template.id) ? "selected" : ""}>${esc(template.nome)} · ${tipoDietaLabel(template.tipo)}</option>`).join("")}</select></div><p class="help">Il contenuto viene copiato: ogni campo resta modificabile e non viene salvato alcun collegamento.</p></div>`
        : "";
      const noteField = this.kind === "template"
        ? `<div class="field"><label class="label">Descrizione template</label><textarea class="textarea" rows="3" data-diet-path="note"${disabled}>${esc(this.state.note)}</textarea></div>`
        : "";
      return `<div>
        <h3 class="title is-5">${this.kind === "template" ? "Dati template" : "Dati dieta"}</h3>
        <p class="has-text-grey mb-4">${this.readOnly ? "Consultazione della dieta archiviata." : this.kind === "template" ? "Configura il modello riutilizzabile." : "Configura liberamente la dieta, anche dopo una precompilazione."}</p>
        ${templatePrefill}
        <div class="field"><label class="label">Nome *</label><input class="input" value="${escAttr(this.state.nome)}" data-diet-path="nome" placeholder="Es. Dieta settimanale"${disabled}></div>
        <div class="field"><label class="label">Tipo</label><div class="select is-fullwidth"><select data-diet-type${disabled}><option value="G" ${this.state.tipo === "G" ? "selected" : ""}>Giornaliera</option><option value="S" ${this.state.tipo === "S" ? "selected" : ""}>Settimanale</option></select></div></div>
        ${noteField}
      </div>`;
    }

    _renderMeals() {
      const tabs = this.state.tipo === "S"
        ? `<div class="tabs is-boxed is-small mb-4"><ul>${DAYS.map((day, index) => `<li class="${this.selectedDay === index ? "is-active" : ""}"><a data-diet-action="day" data-day="${index}">${day}</a></li>`).join("")}</ul></div>`
        : '<div class="notification is-light py-3">Giornata tipo</div>';
      const meals = this.state.pasti
        .map((meal, index) => ({ meal, index }))
        .filter(({ meal }) => this.state.tipo === "G" || Number(meal.giorno_settimana) === this.selectedDay);
      const label = this.state.tipo === "S" ? `Aggiungi pasto a ${DAYS[this.selectedDay]}` : "Aggiungi pasto";
      const addButton = this.readOnly ? "" : `<button class="button is-primary is-light" data-diet-action="add-meal"><span class="icon"><i class="fa-solid fa-plus"></i></span><span>${label}</span></button>`;
      return `<div><h3 class="title is-5">Pasti e opzioni</h3><p class="has-text-grey mb-4">Ogni pasto contiene una o più opzioni complete.</p>${tabs}${meals.length ? meals.map(({ meal, index }) => this._renderMeal(meal, index)).join("") : '<div class="notification is-light">Nessun pasto inserito.</div>'}${addButton}</div>`;
    }

    _renderMeal(meal, mealIndex) {
      const disabled = this.readOnly ? " disabled" : "";
      const actions = this.readOnly ? "" : `<div class="buttons"><button class="button is-small is-info is-light" data-diet-action="add-option" data-meal="${mealIndex}">Aggiungi opzione</button><button class="button is-small is-danger is-light" data-diet-action="remove-meal" data-meal="${mealIndex}">Rimuovi pasto</button></div>`;
      return `<div class="box mb-4">
        <div class="field"><label class="label">Nome pasto</label><input class="input" value="${escAttr(meal.nome)}" data-diet-path="pasti.${mealIndex}.nome" placeholder="Es. Colazione, pranzo, spuntino"${disabled}></div>
        <div class="field"><label class="label">Note pasto visibili al paziente</label><textarea class="textarea" rows="2" data-diet-path="pasti.${mealIndex}.note"${disabled}>${esc(meal.note)}</textarea></div>
        ${(meal.opzioni || []).map((option, optionIndex) => this._renderOption(option, mealIndex, optionIndex)).join("")}
        ${actions}
      </div>`;
    }

    _renderOption(option, mealIndex, optionIndex) {
      const separator = optionIndex > 0 ? '<p class="has-text-centered my-2"><span class="tag is-warning is-light">OPPURE</span></p>' : "";
      const disabled = this.readOnly ? " disabled" : "";
      const removeOption = this.readOnly ? "" : `<button class="button is-small is-danger is-light" data-diet-action="remove-option" data-meal="${mealIndex}" data-option="${optionIndex}">×</button>`;
      const foods = (option.alimenti || []).map((food, foodIndex) => {
        const removeFood = this.readOnly ? "" : `<div class="control"><button class="button is-small is-danger is-light" data-diet-action="remove-food" data-meal="${mealIndex}" data-option="${optionIndex}" data-food="${foodIndex}">×</button></div>`;
        return `<div class="field has-addons mb-2"><div class="control is-expanded"><input class="input is-small" value="${escAttr(food.descrizione)}" data-diet-path="pasti.${mealIndex}.opzioni.${optionIndex}.alimenti.${foodIndex}.descrizione" placeholder="Descrizione alimento e porzione"${disabled}></div>${removeFood}</div>`;
      }).join("");
      const addFood = this.readOnly ? "" : `<button class="button is-small is-light" data-diet-action="add-food" data-meal="${mealIndex}" data-option="${optionIndex}">Aggiungi alimento</button>`;
      return `${separator}<div class="box p-3 mb-2"><div class="level mb-2"><div class="level-left"><p class="is-size-7 has-text-weight-semibold">Opzione ${optionIndex + 1}</p></div><div class="level-right">${removeOption}</div></div>${foods}${addFood}</div>`;
    }

    _renderFinal() {
      if (this.kind !== "assigned") return "";
      const disabled = this.readOnly ? " disabled" : "";
      const status = this.readOnly ? "Archiviata" : this.mode === "edit" ? "Attiva" : "Attiva da oggi";
      const finalNotes = this.readOnly ? `<div class="field"><label class="label">Considerazioni finali private</label><textarea class="textarea" rows="3" disabled>${esc(this.state.considerazioni_finali)}</textarea></div>` : "";
      return `<div><h3 class="title is-5">Configurazioni finali</h3><div class="columns"><div class="column"><label class="label">Stato</label><input class="input" disabled value="${status}"></div><div class="column"><label class="label">Tipo</label><input class="input" disabled value="${tipoDietaLabel(this.state.tipo)}"></div></div><div class="field"><label class="label">Note generali visibili al paziente</label><textarea class="textarea" rows="3" data-diet-path="note"${disabled}>${esc(this.state.note)}</textarea></div><div class="field"><label class="label">Note operative private nutrizionista</label><textarea class="textarea" rows="3" data-diet-path="note_nutrizionista"${disabled}>${esc(this.state.note_nutrizionista)}</textarea>${this.readOnly ? "" : '<p class="help">Le considerazioni finali, facoltative, vengono gestite dopo l’archiviazione.</p>'}</div>${finalNotes}</div>`;
    }  }

  DietEditor.DAYS = DAYS;
  DietEditor.textValue = textValue;
  DietEditor.mapPasti = mapPasti;
  DietEditor.validatePasti = validatePasti;
  return DietEditor;
})();
