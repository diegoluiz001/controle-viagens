# Controle de Viagens

Sistema web para registrar viagens programadas de uma empresa de transporte urbano (fictícia),
acompanhar quais foram realizadas e analisar os motivos das não realizadas.

| | |
|---|---|
| **Aplicação** | https://controle-viagens-slt8.onrender.com |
| **Documentação interativa da API** | https://controle-viagens-slt8.onrender.com/docs |
| **Verificação de saúde** | https://controle-viagens-slt8.onrender.com/health |

> **Primeiro acesso lento?** A hospedagem gratuita (Render) coloca a aplicação em repouso após
> 15 minutos sem uso. O primeiro acesso depois disso pode levar de 30 a 60 segundos; a interface
> mostra um aviso enquanto isso. Os dados **não** se perdem: ficam no PostgreSQL (Neon).

**Stack:** Python 3.14 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL (Neon) · HTML/CSS/JavaScript puro · pytest

---

## Sumário

1. [Funcionalidades](#1-funcionalidades)
2. [Arquitetura](#2-arquitetura)
3. [Banco de dados](#3-banco-de-dados)
4. [Como executar localmente](#4-como-executar-localmente)
5. [Importação do CSV](#5-importação-do-csv)
6. [Restaurar a carga inicial](#6-restaurar-a-carga-inicial)
7. [Testes automatizados](#7-testes-automatizados)
8. [API REST](#8-api-rest)
9. [Decisões técnicas](#9-decisões-técnicas)
10. [Hospedagem](#10-hospedagem)
11. [Segurança e limitações](#11-segurança-e-limitações)
12. [Uso de IA](#12-uso-de-ia)

---

## 1. Funcionalidades

- **Listagem** de viagens com paginação (25 por página), mostrando empresa, linha, veículo, status e motivo.
- **Filtros combináveis** por período (datas inclusivas), empresa e linha. A lista de linhas se ajusta à empresa escolhida, e os filtros ficam no endereço da página (o link pode ser compartilhado).
- **Inclusão, edição e exclusão** de viagens. O `id_viagem` é gerado pelo sistema (`VG0181`, `VG0182`...) e não pode ser alterado.
- **Regra status/motivo** aplicada na interface, na API e no banco:
  - `NAO_REALIZADA` exige um dos motivos `MANUTENCAO`, `PESSOAL`, `TRANSITO` ou `OPERACAO`;
  - `REALIZADA` não pode ter motivo.
- **Dashboard** recalculado com **os mesmos filtros da listagem**: programadas, realizadas, não realizadas, percentual de cumprimento e distribuição das não realizadas pelos quatro motivos. Sem viagens no filtro, as contagens são zero e o percentual aparece como **"Sem dados"**.
- **Importação reproduzível** dos 180 registros do CSV, que pode ser executada várias vezes sem duplicar.

---

## 2. Arquitetura

```
 Navegador ── HTML/CSS/JS (app/static) ──┐
                                         │  mesma origem: a página chama /api/...
                                         ▼
                              FastAPI (app/main.py)
                ┌────────────────────────┼─────────────────────────┐
           rotas (app/routers)  →  serviços (app/services)  →  modelos (app/models.py)
           HTTP, status codes      regras, filtros, consultas     tabelas (SQLAlchemy)
                                         │
                                         ▼
                               PostgreSQL (Neon)  ← migrations (Alembic)
                                         ▲
                     scripts/import_csv.py e scripts/reset_db.py (linha de comando)
```

- **Rotas** só traduzem HTTP: recebem parâmetros, chamam o serviço e devolvem o código de status.
- **Serviços** concentram a lógica. O filtro (`condicoes_filtro`) é escrito **uma única vez** e usado
  pela listagem e pelos indicadores. Por isso os dois sempre mostram o mesmo recorte.
- **Schemas (Pydantic)** definem o formato de entrada e saída e validam as regras, com mensagens próprias.
- A **interface** é servida pela própria aplicação, no mesmo endereço da API (sem CORS e sem etapa de build).

```
controle-viagens/
├── app/
│   ├── main.py              # cria a aplicação, registra rotas, serve a interface
│   ├── config.py            # lê DATABASE_URL (variável de ambiente ou .env)
│   ├── database.py          # conexão e sessão por requisição
│   ├── enums.py             # status e motivos permitidos
│   ├── models.py            # tabelas empresa, linha e viagem
│   ├── schemas.py           # validação de entrada/saída e regra status/motivo
│   ├── routers/             # health, empresas, viagens, indicadores
│   ├── services/            # importacao, viagens (filtros/CRUD), indicadores
│   └── static/              # interface: index.html, styles.css, app.js
├── alembic/versions/        # migrations (criação do schema)
├── data/base_viagens_teste.csv
├── scripts/                 # import_csv.py e reset_db.py
├── tests/                   # 106 testes (pytest)
├── render.yaml              # configuração da hospedagem (infraestrutura como código)
└── requirements.txt / requirements-dev.txt
```

---

## 3. Banco de dados

```
empresa (1) ──< linha (N) (1) ──< viagem (N)
```

| Tabela | Colunas principais | Regras no banco |
|---|---|---|
| `empresa` | `codigo` VARCHAR(3), `nome` | `codigo` único e com exatamente 3 dígitos (`'001'` é texto: os zeros à esquerda são preservados) |
| `linha` | `empresa_id`, `codigo`, `descricao` | código único **por empresa** (`UNIQUE(empresa_id, codigo)`); FK com `RESTRICT` |
| `viagem` | `id_viagem` VARCHAR(20), `linha_id`, `data_viagem` DATE, `horario_programado` TIME, `veiculo`, `status`, `motivo_nao_realizacao`, `created_at`, `updated_at` | `id_viagem` único no formato `VG` + 4 ou mais dígitos; status e motivo restritos aos valores permitidos; **CHECK de coerência status/motivo**; FK com `RESTRICT` |

Detalhes:
- **Chaves:** cada tabela tem um `id` numérico interno (chave primária). O `id_viagem` é o identificador de negócio, que vem do arquivo de origem.
- **Geração do `id_viagem`:** usa uma sequence própria (`viagem_codigo_seq`). Ela é atômica, então duas criações simultâneas nunca recebem o mesmo número, e **um número já usado nunca é reaproveitado**, mesmo após exclusão.
- **`updated_at`:** é atualizado por um **trigger** no banco, valendo para qualquer alteração, inclusive as feitas fora da aplicação.
- **Índices:** em `viagem.data_viagem` (filtro de período) e `viagem.linha_id` (filtros de linha e empresa).
- **Script de criação:** a migration [`alembic/versions/0001_schema_inicial.py`](alembic/versions/0001_schema_inicial.py) cria tudo. Para ver o SQL equivalente sem executar: `alembic upgrade head --sql`.

---

## 4. Como executar localmente

**Pré-requisitos:** Python 3.14 e um banco PostgreSQL. O projeto usa o Neon, mas qualquer PostgreSQL 14+ serve.

```bash
git clone https://github.com/diegoluiz001/controle-viagens.git
cd controle-viagens
python3.14 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # depois edite o .env com a URL do seu banco
```

No `.env`, `DATABASE_URL` é o banco da aplicação. A URL pode ser colada no formato do Neon
(`postgresql://...`), porque a aplicação ajusta o driver sozinha. No Neon, use a conexão **sem pooling**
(o host não deve conter `-pooler`).

```bash
alembic upgrade head                 # cria as tabelas
python -m scripts.import_csv         # carrega os 180 registros
uvicorn app.main:app --reload        # sobe a aplicação
```

Abra http://127.0.0.1:8000. A documentação da API fica em http://127.0.0.1:8000/docs.

---

## 5. Importação do CSV

```bash
python -m scripts.import_csv                          # usa data/base_viagens_teste.csv
python -m scripts.import_csv --arquivo outro.csv      # outro arquivo, mesmo formato
```

Saída da primeira execução:
```
Banco de destino: ep-xxxx-yyyy
Arquivo:          data/base_viagens_teste.csv

Registros lidos no arquivo: 180
Viagens importadas:         180
Viagens já existentes:      0
Empresas novas:             3
Linhas novas:               9
Próximo id_viagem:          VG0181
```
Executando de novo, sem duplicar: `Viagens importadas: 0` e `Viagens já existentes: 180`.

Como funciona:
1. **Lê e valida o arquivo inteiro antes de gravar.** Considera UTF-8 com BOM e separador `;` e confere cabeçalho, datas, horários, códigos com 3 dígitos, status e motivo, `id_viagem` repetido e nomes de empresa ou linha conflitantes. Se houver qualquer problema, lista os erros **com o número da linha** e **nada é gravado**.
2. **Grava numa única transação** (tudo ou nada), com `INSERT ... ON CONFLICT DO NOTHING` sobre o `id_viagem`. Viagens já existentes são ignoradas, nunca sobrescritas, então edições feitas pela interface são preservadas. Uma viagem excluída volta na próxima importação.
3. **Ajusta a sequence** para que o próximo `id_viagem` criado pela aplicação seja maior que o maior já existente.

---

## 6. Restaurar a carga inicial

Se a base de demonstração for alterada e for preciso voltar aos 180 registros originais:

```bash
python -m scripts.reset_db --confirmar <identificador-do-banco>
```

- O script **apaga todas as viagens, linhas e empresas e reimporta o CSV numa única transação**. Se algo falhar, nada é apagado.
- **`--confirmar` é obrigatório e precisa ser o identificador do banco configurado.** No Neon, é o endpoint `ep-...`, a primeira parte do host da `DATABASE_URL`. Se não coincidir, o script recusa e não altera nada. Isso evita rodar no banco errado.
- O arquivo é validado **antes** de qualquer exclusão.
- Saída esperada: `Viagens após o reset: 180` e `Próximo id_viagem: VG0181`.

**Restaurar a produção** a partir de uma máquina com o projeto instalado, sem gravar a senha em arquivo nem no histórico do terminal:
```bash
( read -rsp "URL do banco de produção: " DATABASE_URL && export DATABASE_URL && echo && python -m scripts.reset_db --confirmar <endpoint-de-producao> )
```

> A restauração **não** fica disponível pela API, de propósito: uma rota pública capaz de apagar a base
> inteira poderia ser usada por qualquer pessoa com o link.

---

## 7. Testes automatizados

```bash
pytest                                     # todos os testes (106)
pytest tests/test_regra_status_motivo.py   # teste obrigatório (1)
pytest tests/test_indicadores.py           # teste obrigatório (2)
```

| Arquivo | Testes | O que cobre |
|---|---|---|
| [`test_regra_status_motivo.py`](tests/test_regra_status_motivo.py) | 16 | **Obrigatório (1):** regra status/motivo no Pydantic e na API (criação e edição); quando a regra é violada, nada é gravado e nenhum `id_viagem` é consumido |
| [`test_indicadores.py`](tests/test_indicadores.py) | 26 | **Obrigatório (2):** indicadores em 7 combinações de filtro comparados com um **gabarito independente** recalculado do CSV; mesmos filtros da listagem; "Sem dados"; arredondamento; alterações refletidas |
| [`test_api_viagens.py`](tests/test_api_viagens.py) | 21 | CRUD, filtros (período inclusivo nas duas pontas, empresa, linha, combinados), paginação, 404/422, `id_viagem` sequencial e não reaproveitado |
| [`test_importacao.py`](tests/test_importacao.py) | 12 | Leitura do CSV, validação com erros por linha, idempotência, sequence, reset e proteção do reset |
| [`test_banco_constraints.py`](tests/test_banco_constraints.py) | 18 | Constraints do banco agindo como última barreira (CHECK, UNIQUE, FK, trigger) |
| [`test_interface.py`](tests/test_interface.py) | 7 | Entrega da página e dos arquivos estáticos; ausência de `innerHTML` (proteção contra XSS); `noindex` |
| [`test_health.py`](tests/test_health.py) | 6 | `/health` e leitura da configuração |

### Banco de teste

Os testes que usam banco **apagam dados**. Por isso, rodam num banco **separado**, configurado em
`TEST_DATABASE_URL` no `.env`, e só depois de três verificações:
1. `TEST_DATABASE_URL` precisa estar preenchida;
2. o host precisa ser **diferente** do host de `DATABASE_URL`;
3. o banco precisa ter a marca de teste, gravada uma única vez com:
   ```sql
   COMMENT ON DATABASE neondb IS 'ambiente=test';
   ```

Se qualquer verificação falhar, a execução é interrompida antes de alterar qualquer coisa. Sem
`TEST_DATABASE_URL`, os testes de banco são **pulados** e os demais rodam normalmente. A migration é
aplicada automaticamente no banco de teste.

> A suíte completa leva alguns minutos com um banco na nuvem, porque cada teste recarrega os 180 registros.

---

## 8. API REST

Base: `https://controle-viagens-slt8.onrender.com` (ou `http://127.0.0.1:8000` localmente).
Todas as respostas são JSON. A documentação interativa, onde dá para testar cada rota, fica em `/docs`.

| Método | Rota | Descrição | Sucesso | Erros |
|---|---|---|---|---|
| GET | `/api/viagens` | Lista com filtros e paginação | 200 | 422 |
| GET | `/api/viagens/{id_viagem}` | Consulta uma viagem | 200 | 404 |
| POST | `/api/viagens` | Cria (o `id_viagem` é gerado) | 201 | 422 |
| PUT | `/api/viagens/{id_viagem}` | Edita todos os campos (exceto o `id_viagem`) | 200 | 404, 422 |
| DELETE | `/api/viagens/{id_viagem}` | Exclui | 204 | 404 |
| GET | `/api/indicadores` | Indicadores com os mesmos filtros da listagem | 200 | 422 |
| GET | `/api/empresas` | Empresas e suas linhas (alimenta filtros e formulário) | 200 | |
| GET | `/health` | Aplicação e banco no ar | 200 | 503 |

**Filtros** (opcionais e combináveis, iguais em `/api/viagens` e `/api/indicadores`):
`data_inicio`, `data_fim` (AAAA-MM-DD, inclusivas), `empresa_id`, `linha_id`.
**Paginação:** `pagina` (padrão 1) e `por_pagina` (padrão 50, máximo 500).

### Listar com filtros
```bash
curl "https://controle-viagens-slt8.onrender.com/api/viagens?data_inicio=2026-10-21&data_fim=2026-10-23&empresa_id=2&por_pagina=1"
```
```json
{
  "total": 18,
  "pagina": 1,
  "por_pagina": 1,
  "itens": [
    {
      "id_viagem": "VG0025",
      "data_viagem": "2026-10-21",
      "horario_programado": "06:18",
      "veiculo": "LIT-1102",
      "status": "REALIZADA",
      "motivo_nao_realizacao": null,
      "empresa_id": 2,
      "empresa_codigo": "002",
      "empresa_nome": "Expresso Litoral",
      "linha_id": 4,
      "linha_codigo": "201",
      "linha_descricao": "Terminal - Praia",
      "created_at": "2026-11-24T14:13:50.265970Z",
      "updated_at": "2026-11-24T14:13:50.265970Z"
    }
  ]
}
```

### Consultar uma viagem
```bash
curl https://controle-viagens-slt8.onrender.com/api/viagens/VG0001
```
Resposta 200 com o mesmo formato de um item da lista. Um ID inexistente responde 404:
```json
{"detail": "viagem VG9999 não encontrada"}
```

### Criar
```bash
curl -X POST https://controle-viagens-slt8.onrender.com/api/viagens \
  -H "Content-Type: application/json" \
  -d '{"linha_id": 1, "data_viagem": "2026-11-02", "horario_programado": "07:45",
       "veiculo": "AUR-9999", "status": "NAO_REALIZADA", "motivo_nao_realizacao": "TRANSITO"}'
```
Resposta **201**:
```json
{
  "id_viagem": "VG0181",
  "data_viagem": "2026-11-02",
  "horario_programado": "07:45",
  "veiculo": "AUR-9999",
  "status": "NAO_REALIZADA",
  "motivo_nao_realizacao": "TRANSITO",
  "empresa_id": 1, "empresa_codigo": "001", "empresa_nome": "Viação Aurora",
  "linha_id": 1, "linha_codigo": "101", "linha_descricao": "Centro - Norte",
  "created_at": "2026-11-24T13:00:30.280404Z",
  "updated_at": "2026-11-24T13:00:30.280404Z"
}
```

Campos do corpo (criação e edição): `linha_id`, `data_viagem` (AAAA-MM-DD), `horario_programado`
(HH:MM, sem fuso), `veiculo` (1 a 30 caracteres), `status` e `motivo_nao_realizacao` (`null` ou `""`
quando REALIZADA). Campos desconhecidos são recusados, inclusive `id_viagem`.

### Erro de validação (regra status/motivo)
```bash
curl -X POST https://controle-viagens-slt8.onrender.com/api/viagens \
  -H "Content-Type: application/json" \
  -d '{"linha_id": 1, "data_viagem": "2026-11-02", "horario_programado": "07:45",
       "veiculo": "AUR-9999", "status": "NAO_REALIZADA"}'
```
Resposta **422** (nada é gravado):
```json
{
  "detail": [
    {
      "type": "status_motivo",
      "loc": ["body"],
      "msg": "viagem NAO_REALIZADA exige motivo_nao_realizacao (MANUTENCAO, PESSOAL, TRANSITO ou OPERACAO)"
    }
  ]
}
```
Outros `type` próprios: `periodo_invalido` (data inicial maior que a final), `horario_formato` e
`linha_inexistente`. Os demais erros de formato seguem o padrão do FastAPI.

### Editar
```bash
curl -X PUT https://controle-viagens-slt8.onrender.com/api/viagens/VG0181 \
  -H "Content-Type: application/json" \
  -d '{"linha_id": 5, "data_viagem": "2026-11-02", "horario_programado": "08:00",
       "veiculo": "AUR-9999", "status": "REALIZADA", "motivo_nao_realizacao": null}'
```
Resposta 200 com a viagem atualizada. O `id_viagem` e o `created_at` não mudam, e o `updated_at` avança.

### Excluir
```bash
curl -X DELETE https://controle-viagens-slt8.onrender.com/api/viagens/VG0181
```
Resposta **204** (sem corpo). Excluir de novo responde 404.

### Indicadores
```bash
curl "https://controle-viagens-slt8.onrender.com/api/indicadores?data_inicio=2026-10-21&data_fim=2026-10-23"
```
```json
{
  "programadas": 54,
  "realizadas": 36,
  "nao_realizadas": 18,
  "percentual_cumprimento": 66.67,
  "sem_dados": false,
  "motivos": {"MANUTENCAO": 4, "PESSOAL": 6, "TRANSITO": 5, "OPERACAO": 3}
}
```
Sem viagens no filtro, por exemplo `?data_inicio=2027-01-01&data_fim=2027-01-31`:
```json
{
  "programadas": 0,
  "realizadas": 0,
  "nao_realizadas": 0,
  "percentual_cumprimento": null,
  "sem_dados": true,
  "motivos": {"MANUTENCAO": 0, "PESSOAL": 0, "TRANSITO": 0, "OPERACAO": 0}
}
```
`percentual_cumprimento` = (realizadas / programadas) × 100, com 2 casas decimais. É `null` quando não
há viagens: a interface exibe "Sem dados" em vez de dividir por zero.

### Empresas e linhas
```bash
curl https://controle-viagens-slt8.onrender.com/api/empresas
```
```json
[
  {"id": 1, "codigo": "001", "nome": "Viação Aurora", "linhas": [
    {"id": 1, "codigo": "101", "descricao": "Centro - Norte"},
    {"id": 2, "codigo": "102", "descricao": "Centro - Parque"},
    {"id": 3, "codigo": "103", "descricao": "Rodoviária - Industrial"}
  ]}
]
```
A resposta real traz as três empresas.

---

## 9. Decisões técnicas

| Decisão | Motivo |
|---|---|
| **CSV** como fonte da importação (e não o XLSX) | Os dois arquivos foram comparados e são idênticos. O CSV dispensa bibliotecas extras e o desafio pede para importar só um deles. |
| **Códigos como texto** (`VARCHAR`) | Preserva os zeros à esquerda (`001`). Como número, viraria `1`. |
| **VARCHAR + CHECK** em vez de `ENUM` nativo do PostgreSQL | Adicionar um novo motivo é uma migration simples, que altera o CHECK. Alterar um `ENUM` é mais restrito. |
| **Regra status/motivo em três camadas** (interface, API, banco) | A interface evita o erro, a API dá uma mensagem clara e o banco garante a integridade mesmo com acesso direto. |
| **`id_viagem` gerado por sequence** e formatado como `VG0001` | Atômico (sem colisão em criações simultâneas) e nunca reaproveitado. A formatação fica no Python porque `lpad` cortaria números acima de 9999. |
| **Um único filtro** para listagem e indicadores | Garante por construção que o dashboard mostra o mesmo recorte da tabela. |
| **Indicadores numa só consulta** (`COUNT(*) FILTER (WHERE ...)`) | O banco conta tudo de uma vez, sem trafegar as viagens. As colunas de motivo saem da enumeração, então um motivo novo aparece sozinho. |
| **Percentual com `Decimal` e arredondamento "meio para cima"** | O `round()` do Python arredonda para o par (0,625 → 0,62) e o `float` tem imprecisão binária. O usuário espera 0,63, como no Excel. |
| **"Sem dados" = `null` + `sem_dados: true`** | A API devolve o dado e a interface decide a apresentação. "0%" seria enganoso, porque significaria que nenhuma viagem foi cumprida. |
| **Importação idempotente** (`ON CONFLICT DO NOTHING`) numa transação | Pode ser repetida sem duplicar e sem sobrescrever edições. Um erro no meio não deixa a base pela metade. |
| **Reset só por linha de comando**, com confirmação do banco | Operação destrutiva fora da superfície pública e protegida contra execução no banco errado. |
| **Interface em HTML/CSS/JS puro**, servida pelo FastAPI | Sem etapa de build e sem CORS (mesma origem), simples de hospedar e explicar. |
| **Textos inseridos com `textContent`**, nunca `innerHTML` | Impede XSS: um texto como `<script>` aparece como texto, sem ser executado. |
| **Datas formatadas sem `new Date()`** | `new Date("2026-10-20")` é interpretado em UTC e mostraria 19/10 no Brasil. |
| **Migrations com Alembic** e nomes de constraints padronizados | Schema versionado e reproduzível, com nomes previsíveis para alterações futuras. |
| **Banco de teste separado e protegido** | Os testes apagam dados; as três verificações impedem que isso aconteça no banco errado. |

---

## 10. Hospedagem

| Parte | Serviço | Observação |
|---|---|---|
| Aplicação | **Render** (plano gratuito, região Virginia) | Configurada por [`render.yaml`](render.yaml). Cada push na branch `main` gera um novo deploy. Entra em repouso após 15 min sem uso. |
| Banco | **Neon** PostgreSQL (plano gratuito, AWS us-east-1) | Dados persistentes. Branches separados para produção, desenvolvimento e testes. |

- **Comando de start:** `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`. A migration roda a cada início e não faz nada se o schema já estiver atualizado.
- **A importação não roda no start, de propósito.** O serviço reinicia sempre que sai do repouso, e importar a cada reinício traria de volta viagens excluídas durante a avaliação. A carga inicial em produção foi feita **uma única vez**, com `scripts/import_csv.py`.
- **`DATABASE_URL`** é configurada como segredo no painel do Render e nunca vai para o repositório.
- **Versão do Python** fixada em [`.python-version`](.python-version) (3.14.4), a mesma usada nos testes.

---

## 11. Segurança e limitações

**Acesso:** a demonstração **não exige login**. Os dados são fictícios e o desafio pede acesso sem
cadastro do avaliador. Assim, qualquer pessoa com o link pode consultar e alterar viagens. Se a base for
alterada, a [restauração](#6-restaurar-a-carga-inicial) volta ao estado original em segundos.

**O que está protegido:**
- Credenciais fora do código: `.env` no `.gitignore` e segredo no Render.
- Nenhum acesso direto ao banco: o público só passa pela API, que valida tudo.
- Reset fora da API.
- Mensagens de erro públicas não expõem detalhes internos.
- Proteção contra XSS na interface.
- `noindex` e `robots.txt` pedem aos buscadores para não indexar (isso reduz a exposição, mas não é controle de acesso).

**Num sistema real, eu acrescentaria:** autenticação com perfis (consulta e edição), limite de
requisições, registro de auditoria (quem alterou o quê e quando), exclusão lógica em vez de física,
monitoramento e backups agendados.

---

## 12. Uso de IA

- **ChatGPT (OpenAI):** usado só no início, para ler o enunciado (PDF), organizar os requisitos e
  redigir o pedido inicial passado ao Claude Code. Nenhum código do projeto foi gerado por ele.
- **Claude Code** (modelo Claude Opus 5.5, da Anthropic): usado no restante do desenvolvimento, em
  análise dos requisitos, proposta de arquitetura, geração de código e testes, depuração e revisão.

Todas as decisões técnicas foram discutidas e aprovadas por mim, cada etapa foi revisada e testada antes
do commit, e as contas, credenciais e publicação foram configuradas por mim.

---

Desenvolvido por **Diego Luiz**.
