"use strict";

const $ = (id) => document.getElementById(id);
const status = {
  aberto: "Aberto", em_atendimento: "Em atendimento", aguardando_usuario: "Aguardando usuário",
  resolvido: "Resolvido", fechado: "Fechado",
};
const priority = { baixa: "Baixa", media: "Média", alta: "Alta", critica: "Crítica" };
const sla = { no_prazo: "No prazo", atrasado: "Atrasado", cumprido: "Cumprido", violado: "Violado" };
const role = { solicitante: "Solicitante", tecnico: "Técnico", administrador: "Administrador" };
const eventName = { abertura: "Abertura", atribuicao: "Atribuição", status: "Status", resolucao: "Resolução", comentario: "Comentário", anexo: "Anexo" };
const date = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
const localeNumber = new Intl.NumberFormat("pt-BR");
const state = { user: null, view: "tickets", sequence: 0, modalSequence: 0, filters: { search: "", status: "" } };
let timer;

function node(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat().filter((value) => value != null));
  return el;
}

class ApiError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

async function api(path, method = "GET", data) {
  const headers = { "X-HelpDesk-Request": "1" };
  if (data && !(data instanceof FormData)) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch("/api/" + path, {
      method, headers, body: headers["Content-Type"] ? JSON.stringify(data) : data,
      signal: AbortSignal.timeout(30000),
    });
  } catch {
    throw new ApiError("Não foi possível conectar à central. Tente novamente.", 0);
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state.user && path !== "users/login") signedOut("Sua sessão expirou. Entre novamente.");
    throw new ApiError(result.error || "A solicitação falhou. Tente novamente.", response.status);
  }
  return result;
}

function notice(message, error = false) {
  clearTimeout(timer);
  const element = $("notice");
  element.className = error ? "notice error" : "notice";
  element.textContent = message;
  element.hidden = false;
  timer = setTimeout(() => { element.hidden = true; }, 4500);
}

function signedOut(message) {
  if ($("modal").open) $("modal").close();
  state.user = null;
  state.sequence++;
  state.modalSequence++;
  state.filters = { search: "", status: "" };
  $("screen").replaceChildren();
  $("modal-body").replaceChildren();
  $("workspace").hidden = true;
  $("initial").hidden = true;
  $("login").hidden = false;
  $("login-error").textContent = message || "";
  $("login-error").hidden = !message;
  $("login-form").elements.email.focus();
}

function signedIn(user) {
  state.user = user;
  $("initial").hidden = true;
  $("login").hidden = true;
  $("workspace").hidden = false;
  $("user-name").textContent = user.nome;
  $("user-role").textContent = role[user.perfil];
  $("top-role").textContent = role[user.perfil];
  $("avatar").textContent = user.nome.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  navigate("tickets");
}

function button(text, action, className = "secondary") {
  return node("button", { type: "button", class: className, onclick: action }, text);
}

function badge(dict, value) {
  return node("span", { class: "badge " + (Object.hasOwn(dict, value) ? value : "") }, dict[value] || "—");
}

function formControl(label, name, attrs = {}, type = "input") {
  return node("label", {}, label, node(type, { name, ...attrs }));
}

function selectControl(label, name, options, initial = "") {
  const select = node("select", { name, required: true }, options.map(([key, value]) =>
    node("option", { value: key, selected: String(key) === String(initial) }, value)));
  return node("label", {}, label, select);
}

function actionForm(children, caption, submit, inline = false) {
  const error = node("p", { class: "form-error", role: "alert", hidden: true });
  const send = node("button", { type: "submit", class: "primary" }, caption);
  return node("form", { class: "stack", onsubmit: async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    send.disabled = true;
    send.textContent = "Salvando…";
    error.hidden = true;
    try {
      await submit(new FormData(form));
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      send.disabled = false;
      send.textContent = caption;
    }
  } }, inline ? node("div", { class: "inline" }, children, send) : [...children, send], error);
}

function hero(title, summary, action) {
  return node("section", { class: "hero" }, node("div", {}, node("h1", {}, title), node("p", {}, summary)), action);
}

function metric(label, value) {
  return node("section", { class: "metric" }, node("p", {}, label), node("strong", {}, value));
}

function table(columns, rows, empty) {
  if (!rows.length) return node("p", { class: "empty" }, empty);
  return node("div", { class: "table-wrap", tabindex: "0", role: "region", "aria-label": "Tabela de resultados" },
    node("table", {}, node("thead", {}, node("tr", {}, columns.map((col) => node("th", { scope: "col" }, col)))),
      node("tbody", {}, rows.map((row) => node("tr", {}, row.map((cell) => node("td", {}, cell)))))));
}

function panel(title, action, content) {
  return node("section", { class: "panel" }, node("header", { class: "panel-head" }, node("h2", {}, title), action), content);
}

function modal(title, content) {
  $("modal-title").textContent = title;
  $("modal-body").replaceChildren(content);
  if (!$("modal").open) $("modal").showModal();
}

function openModal(title, load) {
  const version = ++state.modalSequence;
  modal(title, node("p", { class: "muted", role: "status" }, "Carregando…"));
  return Promise.resolve().then(load).then((content) => {
    if (version === state.modalSequence && $("modal").open) modal(title, content);
  }).catch((error) => {
    if (version === state.modalSequence && $("modal").open) modal(title, node("p", { class: "form-error", role: "alert" }, error.message));
  });
}

const pages = {
  tickets: ["Chamados", "▤", ticketPage],
  users: ["Usuários", "♙", usersPage],
  categories: ["Categorias", "▦", categoriesPage],
  reports: ["Relatórios", "▥", reportsPage],
};

async function navigate(key, focus = true) {
  state.view = key;
  const version = ++state.sequence;
  $("navigation").replaceChildren(...Object.entries(pages)
    .filter(([name]) => name === "tickets" || state.user?.perfil === "administrador")
    .map(([name, [label, icon]]) => node("button", {
      type: "button", "aria-current": key === name ? "page" : false, onclick: () => navigate(name),
    }, node("span", { class: "nav-icon", "aria-hidden": "true" }, icon), label)));
  const screen = $("screen");
  screen.replaceChildren(node("p", { class: "muted", role: "status" }, "Carregando…"));
  try {
    const content = await pages[key][2]();
    if (version === state.sequence) {
      screen.replaceChildren(content);
      if (focus) screen.focus();
    }
  } catch (error) {
    if (version === state.sequence) screen.replaceChildren(
      node("div", { class: "stack" }, node("p", { class: "form-error", role: "alert" }, error.message),
        button("Tentar novamente", () => navigate(key))));
  }
}

async function ticketPage() {
  const user = state.user;
  const tickets = await api("tickets");
  const admin = user.perfil === "administrador";
  const allowed = user.perfil !== "tecnico";
  const description = admin ? "Acompanhe a fila de suporte e distribua o atendimento." :
    (allowed ? "Abra solicitações e acompanhe o andamento dos seus chamados." : "Consulte e atualize os chamados atribuídos a você.");
  const filters = state.filters;
  const search = formControl("Buscar chamado", "busca", { type: "search", value: filters.search, placeholder: "Título, número ou categoria" });
  const select = selectControl("Status", "status", [["", "Todos"], ...Object.entries(status)], filters.status);
  const result = node("div");
  function draw() {
    const query = filters.search.toLocaleLowerCase("pt-BR").trim();
    const filtered = tickets.filter((ticket) =>
      (!filters.status || ticket.status === filters.status) &&
      [ticket.titulo, "#" + ticket.id, ticket.categoria].some((value) => value.toLocaleLowerCase("pt-BR").includes(query)));
    const rows = filtered.map((ticket) => [
      node("div", {}, button(ticket.titulo, () => showTicket(ticket.id), "link-button ticket-title"),
        node("p", { class: "small" }, "#" + ticket.id + " · " + ticket.categoria)),
      badge(priority, ticket.prioridade), badge(status, ticket.status), badge(sla, ticket.sla),
      ticket.tecnico || "Sem atribuição", date.format(new Date(ticket.criado_em)),
    ]);
    result.replaceChildren(table(["Chamado", "Prioridade", "Status", "SLA", "Técnico", "Aberto em"], rows,
      tickets.length ? "Nenhum chamado corresponde aos filtros." : "Nenhum chamado disponível."));
  }
  search.querySelector("input").addEventListener("input", (e) => { filters.search = e.target.value; draw(); });
  select.querySelector("select").addEventListener("change", (e) => { filters.status = e.target.value; draw(); });
  draw();
  return node("div", {},
    hero("Chamados", description, allowed && button("Novo chamado", newTicket, "primary") || null),
    node("div", { class: "metrics" }, metric("Total", tickets.length),
      metric("Abertos", tickets.filter((t) => t.status === "aberto").length),
      metric("Em atendimento", tickets.filter((t) => t.status === "em_atendimento").length),
      metric("Aguardando usuário", tickets.filter((t) => t.status === "aguardando_usuario").length),
      metric("Atrasados", tickets.filter((t) => t.sla === "atrasado").length)),
    panel(admin ? "Fila de suporte" : "Meus chamados", node("div", { class: "filters" }, search, select), result));
}

function newTicket() {
  return openModal("Novo chamado", async () => {
    const categories = (await api("categories")).filter((category) => category.ativa);
    if (!categories.length) return node("p", { class: "muted" }, "Não há categorias ativas. Fale com a administração.");
    return actionForm([
      formControl("Título", "titulo", { required: true, maxlength: 150 }),
      formControl("Descrição", "descricao", { required: true, maxlength: 6000, rows: 5 }, "textarea"),
      node("div", { class: "inline" },
        selectControl("Categoria", "categoria_id", categories.map((c) => [c.id, c.nome])),
        selectControl("Prioridade", "prioridade", Object.entries(priority), "media")),
    ], "Abrir chamado", async (form) => {
      const ticket = await api("tickets", "POST", { ...Object.fromEntries(form), categoria_id: Number(form.get("categoria_id")) });
      notice("Chamado #" + ticket.id + " aberto.");
      navigate("tickets", false);
      showTicket(ticket.id);
    });
  });
}

function section(title, ...content) {
  return node("section", { class: "detail-section" }, node("h3", {}, title), content);
}

function showTicket(id) {
  return openModal("Chamado #" + id, async () => {
    const ticket = await api("tickets/" + id);
    const admin = state.user.perfil === "administrador";
    const closed = ticket.status === "fechado";
    const details = node("div", { class: "stack" },
      node("h3", {}, ticket.titulo),
      node("div", { class: "inline" }, badge(status, ticket.status), badge(priority, ticket.prioridade), badge(sla, ticket.sla)),
      node("p", { class: "small" }, ticket.categoria + " · Técnico: " + (ticket.tecnico || "Sem atribuição")),
      node("p", { class: "small" }, "Aberto em " + date.format(new Date(ticket.criado_em)) + " · Prazo " + date.format(new Date(ticket.prazo_em))),
      node("p", { class: "copy" }, ticket.descricao));
    if (ticket.resolucao) details.append(section("Resolução", node("p", { class: "copy" }, ticket.resolucao)));
    async function update(endpoint, method, data, message) {
      await api("tickets/" + id + "/" + endpoint, method, data);
      notice(message);
      showTicket(id);
      navigate("tickets", false);
    }
    if (admin && !closed && ticket.status !== "resolvido") {
      const technicians = (await api("users")).filter((user) => user.ativo && user.perfil === "tecnico");
      details.append(section("Atribuição", technicians.length
        ? actionForm([selectControl("Técnico", "tecnico_id", technicians.map((user) => [user.id, user.nome]), ticket.tecnico_id)],
          "Atribuir", (form) => update("assignment", "PATCH", { tecnico_id: Number(form.get("tecnico_id")) }, "Atribuição atualizada."), true)
        : node("p", { class: "muted" }, "Cadastre um técnico ativo em Usuários.")));
    }
    if (ticket.transicoes.length) {
      const next = selectControl("Próximo status", "status", ticket.transicoes.map((value) => [value, status[value]]));
      const resolution = formControl("Resolução", "resolucao", { maxlength: 6000 }, "textarea");
      const select = next.querySelector("select");
      const toggle = () => {
        const resolving = select.value === "resolvido";
        resolution.hidden = !resolving;
        resolution.querySelector("textarea").required = resolving;
      };
      select.addEventListener("change", toggle);
      toggle();
      details.append(section("Atualizar atendimento", actionForm([next, resolution], "Atualizar status",
        (form) => update("status", "PATCH", Object.fromEntries(form), "Status atualizado."))));
    }
    const uploads = ticket.anexos.map((file) => node("li", {},
      node("a", { href: "/api/tickets/" + id + "/attachments/" + file.id, download: file.nome }, file.nome),
      node("span", { class: "small" }, " · " + localeNumber.format(Math.ceil(file.tamanho / 1024)) + " KiB")));
    details.append(section("Anexos", uploads.length ? node("ul", {}, uploads) : node("p", { class: "muted" }, "Nenhum anexo."),
      !closed && ticket.anexos.length < 5 ? actionForm([
        formControl("Adicionar arquivo · até 5 MiB", "arquivo", { type: "file", required: true, accept: ".pdf,.png,.jpg,.jpeg,.txt,.log" }),
      ], "Enviar", (form) => update("attachments", "POST", form, "Anexo enviado."), true) : null));
    const events = ticket.historico.map((entry) => node("li", {},
      node("strong", {}, eventName[entry.tipo] || entry.tipo),
      node("p", { class: "small" }, entry.autor + " · " + date.format(new Date(entry.criado_em))),
      node("p", { class: "copy" }, entry.mensagem)));
    details.append(section("Histórico", node("ol", { class: "timeline" }, events)));
    if (!closed) details.append(section("Adicionar comentário", actionForm([
      formControl("Mensagem", "mensagem", { required: true, maxlength: 3000 }, "textarea"),
    ], "Comentar", (form) => update("comments", "POST", Object.fromEntries(form), "Comentário registrado."))));
    return details;
  });
}

async function usersPage() {
  const users = await api("users");
  return node("div", {},
    hero("Usuários", "Cadastre contas e gerencie os perfis de acesso.", button("Novo usuário", () => editUser(), "primary")),
    panel("Contas cadastradas", null, table(["Nome", "E-mail", "Perfil", "Situação", "Ações"], users.map((user) => [
      user.nome, user.email, role[user.perfil], user.ativo ? "Ativo" : "Inativo",
      user.principal && user.id !== state.user.id ? "Conta inicial" : button("Editar", () => editUser(user)),
    ]), "Nenhuma conta cadastrada.")));
}

function editUser(user) {
  state.modalSequence++;
  const protectedAccount = user?.id === state.user.id || user?.principal;
  modal(user ? "Editar usuário" : "Novo usuário", actionForm([
    formControl("Nome", "nome", { required: true, maxlength: 120, value: user?.nome }),
    formControl("E-mail", "email", { type: "email", required: true, maxlength: 180, value: user?.email }),
    selectControl("Perfil", "perfil", protectedAccount ? [["administrador", "Administrador"]] : Object.entries(role), user?.perfil),
    formControl(user ? "Nova senha (opcional, mínimo de 10 caracteres)" : "Senha (mínimo de 10 caracteres)", "senha",
      { type: "password", required: !user, minlength: 10, maxlength: 128, autocomplete: "new-password" }),
    user && !protectedAccount ? node("label", { class: "check" },
      node("input", { name: "ativo", type: "checkbox", checked: user.ativo }), "Conta ativa") : null,
  ], "Salvar usuário", async (form) => {
    const data = Object.fromEntries(form);
    if (!data.senha) delete data.senha;
    if (user) data.ativo = Boolean(protectedAccount || form.has("ativo"));
    const updated = await api(user ? "users/" + user.id : "users", user ? "PATCH" : "POST", data);
    $("modal").close();
    if (updated.id === state.user.id) {
      if (data.senha) {
        signedOut("Senha atualizada. Entre novamente.");
        return;
      }
      signedIn(updated);
    } else {
      navigate("users");
    }
    notice("Usuário salvo.");
  }));
}

async function categoriesPage() {
  const categories = await api("categories");
  return node("div", {},
    hero("Categorias", "Organize os chamados por tipo de atendimento.", button("Nova categoria", () => editCategory(), "primary")),
    panel("Catálogo", null, table(["Categoria", "Situação", "Ações"], categories.map((item) => [
      item.nome, item.ativa ? "Ativa" : "Arquivada", button("Editar", () => editCategory(item)),
    ]), "Nenhuma categoria cadastrada.")));
}

function editCategory(item) {
  state.modalSequence++;
  modal(item ? "Editar categoria" : "Nova categoria", actionForm([
    formControl("Nome", "nome", { required: true, maxlength: 80, value: item?.nome }),
    node("label", { class: "check" }, node("input", { name: "ativa", type: "checkbox", checked: item?.ativa ?? true }), "Disponível para novos chamados"),
  ], "Salvar categoria", async (form) => {
    await api(item ? "categories/" + item.id : "categories", item ? "PATCH" : "POST",
      { nome: form.get("nome"), ativa: form.has("ativa") });
    $("modal").close();
    notice("Categoria salva.");
    navigate("categories");
  }));
}

async function reportsPage() {
  const report = await api("reports");
  const duration = report.media_resolucao_horas == null ? "—" : localeNumber.format(report.media_resolucao_horas) + " h";
  return node("div", {},
    hero("Relatórios", "Consulte os indicadores operacionais da central."),
    node("div", { class: "metrics" }, metric("Chamados registrados", report.total),
      metric("Resoluções registradas", report.resolvidos), metric("Tempo médio até a resolução", duration)),
    panel("Volume por status", null, table(["Status", "Chamados"], Object.entries(status).map(([key, label]) =>
      [label, report.por_status[key]]), "")),
    panel("Chamados por técnico", null, table(["Técnico", "Chamados atribuídos"],
      report.por_tecnico.map((entry) => [entry.nome, entry.total]), "Nenhum chamado atribuído.")));
}

$("close-modal").addEventListener("click", () => $("modal").close());
$("modal").addEventListener("close", () => { state.modalSequence++; });
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const send = form.querySelector("button");
  send.disabled = true;
  send.textContent = "Entrando…";
  $("login-error").hidden = true;
  try {
    const user = await api("users/login", "POST", Object.fromEntries(new FormData(form)));
    form.reset();
    signedIn(user);
  } catch (error) {
    $("login-error").textContent = error.message;
    $("login-error").hidden = false;
  } finally {
    send.disabled = false;
    send.textContent = "Entrar";
  }
});
$("logout").addEventListener("click", async () => {
  const logout = $("logout");
  logout.disabled = true;
  try {
    await api("users/logout", "POST", {});
    signedOut();
  } catch (error) {
    notice(error.message, true);
  } finally {
    logout.disabled = false;
  }
});
api("users/me").then(signedIn).catch((error) => signedOut(error.code === 401 ? "" : error.message));
