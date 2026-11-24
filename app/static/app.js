/*
 * Interface do Controle de Viagens.
 *
 * Toda informação vem da API (/api/...). A página não guarda dados próprios:
 * depois de criar, editar ou excluir, ela recarrega a tabela e os indicadores do banco.
 *
 * Segurança: textos vindos do banco entram na página sempre por textContent
 * (nunca innerHTML), então nada digitado pelo usuário é interpretado como HTML.
 */
"use strict";

const POR_PAGINA = 25;
const STATUS = { REALIZADA: "Realizada", NAO_REALIZADA: "Não realizada" };
const MOTIVOS = { MANUTENCAO: "Manutenção", PESSOAL: "Pessoal", TRANSITO: "Trânsito", OPERACAO: "Operação" };

const estado = {
  empresas: [],          // [{id, codigo, nome, linhas: [...]}]
  filtro: {},            // {data_inicio, data_fim, empresa_id, linha_id} (só os preenchidos)
  pagina: 1,
  total: 0,
  emEdicao: null,        // id_viagem em edição (null = criação)
  aExcluir: null,
};

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ utilidades

/** "2026-10-20" -> "20/10/2026" sem usar Date (evita deslocamento de fuso horário). */
function formatarData(iso) {
  const [ano, mes, dia] = iso.split("-");
  return `${dia}/${mes}/${ano}`;
}

function formatarPercentual(valor) {
  return valor.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
}

/** Cria um elemento com texto seguro (textContent) e classes opcionais. */
function el(tag, texto = "", classe = "") {
  const elemento = document.createElement(tag);
  if (texto !== "") elemento.textContent = texto;
  if (classe) elemento.className = classe;
  return elemento;
}

function opcao(valor, texto) {
  const o = document.createElement("option");
  o.value = valor;
  o.textContent = texto;
  return o;
}

function mostrarAviso(texto, tipo = "") {
  const aviso = $("aviso");
  aviso.textContent = texto;
  aviso.className = "aviso" + (tipo ? " " + tipo : "");
  aviso.hidden = false;
  if (tipo === "sucesso") setTimeout(() => { if (aviso.textContent === texto) aviso.hidden = true; }, 4000);
}

function esconderAviso() {
  $("aviso").hidden = true;
}

// ------------------------------------------------------------------ acesso à API

class ErroApi extends Error {
  constructor(status, detalhe) {
    super(typeof detalhe === "string" ? detalhe : `Erro ${status}`);
    this.status = status;
    this.detalhe = detalhe; // string (404) ou lista de erros de validação (422)
  }
}

let requisicoesLentas = 0;

/** fetch com tratamento de erro e aviso quando o servidor demora (Render "acordando"). */
async function api(caminho, opcoes = {}) {
  const timer = setTimeout(() => {
    requisicoesLentas++;
    mostrarAviso("O servidor está iniciando (hospedagem gratuita entra em repouso). Aguarde alguns segundos…");
  }, 3000);
  try {
    const resposta = await fetch(caminho, {
      ...opcoes,
      headers: { "Content-Type": "application/json", ...(opcoes.headers || {}) },
    });
    if (resposta.status === 204) return null;
    const corpo = await resposta.json().catch(() => null);
    if (!resposta.ok) throw new ErroApi(resposta.status, corpo && corpo.detail);
    return corpo;
  } catch (erro) {
    if (erro instanceof ErroApi) throw erro;
    throw new ErroApi(0, "Não foi possível conectar ao servidor. Verifique a conexão e tente novamente.");
  } finally {
    clearTimeout(timer);
    if (requisicoesLentas > 0) { requisicoesLentas--; esconderAviso(); }
  }
}

function paramsDoFiltro(extra = {}) {
  return new URLSearchParams({ ...estado.filtro, ...extra }).toString();
}

// ------------------------------------------------------------------ empresas e linhas

function linhasDaEmpresa(empresaId) {
  if (!empresaId) return estado.empresas.flatMap((e) => e.linhas.map((l) => ({ ...l, empresa: e })));
  const empresa = estado.empresas.find((e) => String(e.id) === String(empresaId));
  return empresa ? empresa.linhas.map((l) => ({ ...l, empresa })) : [];
}

function preencherEmpresas(select, primeira) {
  select.replaceChildren(opcao("", primeira));
  for (const e of estado.empresas) select.append(opcao(e.id, `${e.codigo} - ${e.nome}`));
}

function preencherLinhas(select, empresaId, primeira, mostrarEmpresa) {
  select.replaceChildren(opcao("", primeira));
  for (const l of linhasDaEmpresa(empresaId)) {
    const texto = `${l.codigo} - ${l.descricao}` + (mostrarEmpresa ? ` (${l.empresa.nome})` : "");
    select.append(opcao(l.id, texto));
  }
}

// ------------------------------------------------------------------ filtros

function lerFiltroDaUrl() {
  const params = new URLSearchParams(location.search);
  const filtro = {};
  for (const chave of ["data_inicio", "data_fim", "empresa_id", "linha_id"]) {
    if (params.get(chave)) filtro[chave] = params.get(chave);
  }
  return filtro;
}

function filtroParaFormulario() {
  $("filtro-inicio").value = estado.filtro.data_inicio || "";
  $("filtro-fim").value = estado.filtro.data_fim || "";
  $("filtro-empresa").value = estado.filtro.empresa_id || "";
  preencherLinhas($("filtro-linha"), estado.filtro.empresa_id, "Todas", !estado.filtro.empresa_id);
  $("filtro-linha").value = estado.filtro.linha_id || "";
}

function filtroDoFormulario() {
  const filtro = {
    data_inicio: $("filtro-inicio").value,
    data_fim: $("filtro-fim").value,
    empresa_id: $("filtro-empresa").value,
    linha_id: $("filtro-linha").value,
  };
  return Object.fromEntries(Object.entries(filtro).filter(([, v]) => v));
}

function aplicarFiltro(evento) {
  evento.preventDefault();
  const filtro = filtroDoFormulario();
  const erro = $("erro-filtros");
  if (filtro.data_inicio && filtro.data_fim && filtro.data_inicio > filtro.data_fim) {
    erro.textContent = "A data inicial não pode ser posterior à data final.";
    return;
  }
  erro.textContent = "";
  estado.filtro = filtro;
  estado.pagina = 1;
  history.replaceState(null, "", "?" + paramsDoFiltro());
  atualizarTudo();
}

function limparFiltro() {
  estado.filtro = {};
  estado.pagina = 1;
  $("erro-filtros").textContent = "";
  filtroParaFormulario();
  history.replaceState(null, "", location.pathname);
  atualizarTudo();
}

// ------------------------------------------------------------------ indicadores

function renderizarIndicadores(ind) {
  $("ind-programadas").textContent = ind.programadas;
  $("ind-realizadas").textContent = ind.realizadas;
  $("ind-nao-realizadas").textContent = ind.nao_realizadas;

  const percentual = $("ind-percentual");
  percentual.textContent = ind.sem_dados ? "Sem dados" : formatarPercentual(ind.percentual_cumprimento);
  percentual.classList.toggle("sem-dados", ind.sem_dados);

  const lista = $("motivos");
  lista.replaceChildren();
  if (ind.nao_realizadas === 0) {
    lista.append(el("li", ind.sem_dados ? "Sem dados para o filtro selecionado." : "Nenhuma viagem não realizada no filtro.", "motivos-vazio"));
    return;
  }
  for (const [codigo, nome] of Object.entries(MOTIVOS)) {
    const quantidade = ind.motivos[codigo] ?? 0;
    const proporcao = (quantidade / ind.nao_realizadas) * 100;
    const item = el("li", "", "motivo");
    const barra = el("div", "", "barra");
    const preenchida = el("div", "", "barra-preenchida");
    preenchida.style.width = proporcao + "%";
    barra.append(preenchida);
    barra.setAttribute("role", "img");
    barra.setAttribute("aria-label", `${nome}: ${quantidade} de ${ind.nao_realizadas}`);
    item.append(el("span", nome), barra, el("span", `${quantidade} (${Math.round(proporcao)}%)`, "motivo-valor"));
    lista.append(item);
  }
}

// ------------------------------------------------------------------ tabela

function renderizarTabela(dados) {
  estado.total = dados.total;
  const corpo = $("corpo-tabela");
  corpo.replaceChildren();

  if (dados.itens.length === 0) {
    const linha = el("tr");
    const celula = el("td", "Nenhuma viagem encontrada para o filtro selecionado.", "vazio");
    celula.colSpan = 9;
    linha.append(celula);
    corpo.append(linha);
  }

  for (const v of dados.itens) {
    const tr = el("tr");
    const empresa = el("td", v.empresa_codigo);
    empresa.append(el("span", v.empresa_nome, "sub"));
    const linha = el("td", v.linha_codigo);
    linha.append(el("span", v.linha_descricao, "sub"));
    const status = el("td");
    status.append(el("span", STATUS[v.status], "selo " + (v.status === "REALIZADA" ? "realizada" : "nao-realizada")));

    const acoes = el("td", "", "acoes");
    const editar = el("button", "Editar", "botao pequeno");
    editar.type = "button";
    editar.setAttribute("aria-label", `Editar ${v.id_viagem}`);
    editar.addEventListener("click", () => abrirFormulario(v));
    const excluir = el("button", "Excluir", "botao pequeno");
    excluir.type = "button";
    excluir.setAttribute("aria-label", `Excluir ${v.id_viagem}`);
    excluir.addEventListener("click", () => abrirExclusao(v));
    acoes.append(editar, excluir);

    tr.append(
      el("td", v.id_viagem),
      el("td", formatarData(v.data_viagem)),
      el("td", v.horario_programado),
      empresa,
      linha,
      el("td", v.veiculo),
      status,
      el("td", v.motivo_nao_realizacao ? MOTIVOS[v.motivo_nao_realizacao] : "—"),
      acoes,
    );
    corpo.append(tr);
  }

  const paginas = Math.max(1, Math.ceil(dados.total / POR_PAGINA));
  const inicio = dados.total === 0 ? 0 : (dados.pagina - 1) * POR_PAGINA + 1;
  const fim = (dados.pagina - 1) * POR_PAGINA + dados.itens.length;
  $("contagem").textContent = `(${inicio}–${fim} de ${dados.total})`;
  $("pagina-info").textContent = `Página ${dados.pagina} de ${paginas}`;
  $("pagina-anterior").disabled = dados.pagina <= 1;
  $("pagina-proxima").disabled = dados.pagina >= paginas;
}

// ------------------------------------------------------------------ carregamento

async function atualizarTudo() {
  document.body.classList.add("carregando");  // esmaece números antigos enquanto recarrega
  try {
    const [lista, indicadores] = await Promise.all([
      api("/api/viagens?" + paramsDoFiltro({ pagina: estado.pagina, por_pagina: POR_PAGINA })),
      api("/api/indicadores?" + paramsDoFiltro()),
    ]);
    // Se uma exclusão esvaziou a última página, volta uma página.
    if (lista.itens.length === 0 && estado.pagina > 1) {
      estado.pagina--;
      return atualizarTudo();
    }
    renderizarTabela(lista);
    renderizarIndicadores(indicadores);
  } catch (erro) {
    mostrarAviso(mensagemDeErro(erro), "erro");
  } finally {
    document.body.classList.remove("carregando");
  }
}

function mensagemDeErro(erro) {
  if (Array.isArray(erro.detalhe)) return erro.detalhe.map((d) => d.msg).join("; ");
  return erro.message;
}

// ------------------------------------------------------------------ formulário (criar / editar)

function limparErrosFormulario() {
  for (const span of document.querySelectorAll("#form-viagem [data-erro]")) span.textContent = "";
  for (const campo of document.querySelectorAll("#form-viagem [aria-invalid]")) campo.removeAttribute("aria-invalid");
  $("erro-form").textContent = "";
}

function erroNoCampo(nome, mensagem) {
  const span = document.querySelector(`#form-viagem [data-erro="${nome}"]`);
  if (!span) { $("erro-form").textContent = mensagem; return; }
  span.textContent = mensagem;
  const campo = span.parentElement.querySelector("input, select");
  if (campo) campo.setAttribute("aria-invalid", "true");
}

/** Regra status/motivo na interface: motivo só existe (e é obrigatório) para NAO_REALIZADA. */
function sincronizarMotivo() {
  const naoRealizada = $("campo-status").value === "NAO_REALIZADA";
  const motivo = $("campo-motivo");
  motivo.disabled = !naoRealizada;
  motivo.required = naoRealizada;
  if (!naoRealizada) motivo.value = "";
  $("dica-motivo").textContent = naoRealizada
    ? "Obrigatório para viagens não realizadas."
    : "Somente para viagens não realizadas.";
}

function abrirFormulario(viagem = null) {
  limparErrosFormulario();
  estado.emEdicao = viagem ? viagem.id_viagem : null;
  $("titulo-dialogo").textContent = viagem ? "Editar viagem" : "Nova viagem";
  $("form-id").hidden = !viagem;
  $("form-id").textContent = viagem ? `ID: ${viagem.id_viagem} (não editável)` : "";

  const empresaId = viagem ? viagem.empresa_id : (estado.filtro.empresa_id || "");
  $("campo-empresa").value = empresaId;
  preencherLinhas($("campo-linha"), empresaId, empresaId ? "Selecione…" : "Selecione a empresa…", false);
  $("campo-linha").disabled = !empresaId;
  $("campo-linha").value = viagem ? viagem.linha_id : "";
  $("campo-data").value = viagem ? viagem.data_viagem : "";
  $("campo-horario").value = viagem ? viagem.horario_programado : "";
  $("campo-veiculo").value = viagem ? viagem.veiculo : "";
  $("campo-status").value = viagem ? viagem.status : "REALIZADA";
  $("campo-motivo").value = viagem && viagem.motivo_nao_realizacao ? viagem.motivo_nao_realizacao : "";
  sincronizarMotivo();

  $("dialogo-viagem").showModal();
  $("campo-empresa").focus();
}

function validarFormulario(dados) {
  let valido = true;
  const exigir = (condicao, campo, mensagem) => { if (!condicao) { erroNoCampo(campo, mensagem); valido = false; } };
  exigir($("campo-empresa").value, "empresa", "Selecione a empresa.");
  exigir(dados.linha_id, "linha_id", "Selecione a linha.");
  exigir(dados.data_viagem, "data_viagem", "Informe a data.");
  exigir(/^\d{2}:\d{2}$/.test(dados.horario_programado), "horario_programado", "Informe o horário (HH:MM).");
  exigir(dados.veiculo, "veiculo", "Informe o veículo.");
  if (dados.status === "NAO_REALIZADA") {
    exigir(dados.motivo_nao_realizacao, "motivo_nao_realizacao", "Selecione o motivo da não realização.");
  }
  return valido;
}

/** Erros 422 da API -> mensagem ao lado do campo correspondente. */
function mostrarErrosDaApi(erro) {
  if (!Array.isArray(erro.detalhe)) { $("erro-form").textContent = mensagemDeErro(erro); return; }
  for (const item of erro.detalhe) {
    const campo = item.type === "status_motivo" ? "motivo_nao_realizacao" : item.loc[item.loc.length - 1];
    erroNoCampo(campo, item.msg);
  }
}

async function salvarFormulario(evento) {
  evento.preventDefault();
  limparErrosFormulario();
  const dados = {
    linha_id: Number($("campo-linha").value) || null,
    data_viagem: $("campo-data").value,
    horario_programado: $("campo-horario").value.slice(0, 5),
    veiculo: $("campo-veiculo").value.trim(),
    status: $("campo-status").value,
    motivo_nao_realizacao: $("campo-status").value === "NAO_REALIZADA" ? $("campo-motivo").value : null,
  };
  if (!validarFormulario(dados)) return;

  const botao = $("salvar-form");
  botao.disabled = true;
  try {
    const editando = estado.emEdicao;
    const salva = await api(editando ? `/api/viagens/${encodeURIComponent(editando)}` : "/api/viagens", {
      method: editando ? "PUT" : "POST",
      body: JSON.stringify(dados),
    });
    $("dialogo-viagem").close();
    await atualizarTudo();  // a confirmação só aparece com os números já atualizados
    mostrarAviso(editando ? `Viagem ${salva.id_viagem} atualizada.` : `Viagem ${salva.id_viagem} criada.`, "sucesso");
  } catch (erro) {
    if (erro.status === 404) {
      $("dialogo-viagem").close();
      mostrarAviso("Esta viagem não existe mais (pode ter sido excluída).", "erro");
      await atualizarTudo();
    } else {
      mostrarErrosDaApi(erro);
    }
  } finally {
    botao.disabled = false;
  }
}

// ------------------------------------------------------------------ exclusão

function abrirExclusao(viagem) {
  estado.aExcluir = viagem.id_viagem;
  $("texto-excluir").textContent =
    `Excluir a viagem ${viagem.id_viagem} (${formatarData(viagem.data_viagem)} às ${viagem.horario_programado}, ` +
    `linha ${viagem.linha_codigo}, veículo ${viagem.veiculo})? Esta ação não pode ser desfeita.`;
  $("erro-excluir").textContent = "";
  $("dialogo-excluir").showModal();
}

async function confirmarExclusao() {
  const id = estado.aExcluir;
  const botao = $("confirmar-excluir");
  botao.disabled = true;
  let mensagem = [`Viagem ${id} excluída.`, "sucesso"];
  try {
    await api(`/api/viagens/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch (erro) {
    if (erro.status !== 404) { $("erro-excluir").textContent = mensagemDeErro(erro); return; }
    mensagem = [`A viagem ${id} já havia sido excluída.`, "erro"];
  } finally {
    botao.disabled = false;
  }
  $("dialogo-excluir").close();
  await atualizarTudo();
  mostrarAviso(...mensagem);
}

// ------------------------------------------------------------------ inicialização

async function iniciar() {
  for (const [codigo, nome] of Object.entries(MOTIVOS)) $("campo-motivo").append(opcao(codigo, nome));

  $("form-filtros").addEventListener("submit", aplicarFiltro);
  $("limpar-filtros").addEventListener("click", limparFiltro);
  $("filtro-empresa").addEventListener("change", () => {
    const empresaId = $("filtro-empresa").value;
    preencherLinhas($("filtro-linha"), empresaId, "Todas", !empresaId);
  });

  $("nova-viagem").addEventListener("click", () => abrirFormulario());
  $("cancelar-form").addEventListener("click", () => $("dialogo-viagem").close());
  $("form-viagem").addEventListener("submit", salvarFormulario);
  $("campo-status").addEventListener("change", sincronizarMotivo);
  $("campo-empresa").addEventListener("change", () => {
    const empresaId = $("campo-empresa").value;
    preencherLinhas($("campo-linha"), empresaId, empresaId ? "Selecione…" : "Selecione a empresa…", false);
    $("campo-linha").disabled = !empresaId;
  });
  $("confirmar-excluir").addEventListener("click", confirmarExclusao);

  $("pagina-anterior").addEventListener("click", () => { estado.pagina--; atualizarTudo(); });
  $("pagina-proxima").addEventListener("click", () => { estado.pagina++; atualizarTudo(); });

  try {
    estado.empresas = await api("/api/empresas");
  } catch (erro) {
    mostrarAviso(mensagemDeErro(erro), "erro");
    return;
  }
  preencherEmpresas($("filtro-empresa"), "Todas");
  preencherEmpresas($("campo-empresa"), "Selecione…");
  estado.filtro = lerFiltroDaUrl();
  filtroParaFormulario();
  await atualizarTudo();
}

iniciar();
