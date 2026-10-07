# SPEC.md — Personal Chief of Staff

## 1. Visão do produto

O **Personal Chief of Staff** é um agente pessoal executado em infraestrutura própria, acessível inicialmente pelo Telegram, capaz de transformar mensagens naturais — texto e futuramente áudio — em ações estruturadas nos sistemas pessoais do usuário.

A primeira versão será focada em gerenciamento de tarefas no Notion.

O sistema deverá utilizar **LangChain Deep Agents** como motor de raciocínio e orquestração, mantendo uma separação explícita entre:

* interface com o usuário;
* aplicação;
* agente;
* ferramentas;
* integrações externas;
* persistência.

O objetivo não é construir apenas um chatbot, mas criar a fundação de um **assistente pessoal operacional**, extensível posteriormente para calendário, e-mail, documentos, pesquisas e agentes especializados.

---

# 2. Objetivo da V1

Permitir que o usuário converse com um bot privado no Telegram e realize operações relacionadas às suas tarefas pessoais no Notion.

A V1 deverá suportar principalmente:

1. criar tarefas;
2. consultar tarefas;
3. atualizar tarefas;
4. identificar projetos relacionados;
5. vincular tarefas a projetos quando possível;
6. interpretar datas e prazos descritos em linguagem natural;
7. manter contexto básico da conversa;
8. responder ao usuário informando claramente o que foi executado.

Exemplo:

**Usuário**

> Preciso revisar o material do programa de Builders amanhã.

**Sistema**

Interpreta:

```text
Intent: CREATE_TASK

title:
Revisar material do programa de Builders

due_date:
2026-08-09

project:
Programa de Builders
```

Executa a operação no Notion e responde:

> Tarefa criada para amanhã e vinculada ao projeto Programa de Builders.

---

# 3. Princípios arquiteturais

## 3.1 Agent ≠ Application

O Deep Agent não deve ter acesso irrestrito às APIs externas.

O agente deverá operar apenas através de ferramentas explicitamente disponibilizadas pela aplicação.

Exemplo correto:

```python
create_task(
    title="...",
    due_date="...",
    project_id="..."
)
```

Evitar ferramentas genéricas como:

```python
notion_api_request(...)
```

A camada de aplicação é responsável por validar os argumentos antes da execução.

---

## 3.2 Tools pequenas e determinísticas

Cada ferramenta deverá possuir responsabilidade específica.

Exemplos:

```text
create_task
search_tasks
get_task
update_task
complete_task
search_projects
get_project
```

Uma ferramenta não deverá executar múltiplas operações implicitamente.

---

## 3.3 LLM decide intenção; aplicação executa ação

Responsabilidade do agente:

```text
Entender
Planejar
Selecionar ferramenta
Fornecer parâmetros
Interpretar resultado
Responder
```

Responsabilidade da aplicação:

```text
Validar
Autorizar
Executar
Persistir
Registrar logs
```

---

## 3.4 Segurança por padrão

Toda operação deverá considerar que o LLM pode cometer erros.

Por isso:

* nenhuma credencial deverá aparecer no código;
* todas as credenciais deverão vir de variáveis de ambiente;
* apenas usuários Telegram autorizados poderão interagir com o agente;
* ferramentas deverão validar argumentos;
* operações destrutivas deverão possuir proteções adicionais;
* logs não deverão armazenar secrets nem conteúdo livre do usuário em claro;
* a allowlist de tools deverá ser aplicada imediatamente antes da execução, não apenas na lista mostrada ao modelo;
* IDs usados em mutações deverão ser UUIDs válidos e possuir proveniência/autorização verificável;
* o texto do modelo não poderá transformar uma operação não confirmada em sucesso;
* a superfície de tools embutidas do framework deverá ser declarada explicitamente em um só lugar, e nunca herdada por padrão — o shell (`execute`) permanece desabilitado e o filesystem do agente permanece virtual, sem acesso ao disco do container;
* escritas no filesystem virtual deverão exigir autorização do usuário para aquele arquivo e aquela operação, registrada pela aplicação e nunca inferida da linguagem natural nem afirmada pelo modelo;
* um arquivo enviado pelo usuário deverá ser gravado nesse mesmo filesystem virtual, sob `/anexos/`, pela própria aplicação — nunca por uma tool do modelo, e portanto sem passar pelo gate de aprovação, que existe para o que o modelo decide escrever. O conteúdo do arquivo deverá ser tratado como dado não-confiável, com o mesmo aviso aplicado a uma página buscada, e o espaço de anexos deverá ter orçamento próprio, separado do bloco de rascunho do modelo, para que nenhum dos dois despeje o outro;
* um subagente deverá receber uma allowlist própria, estritamente menor que a do Chief: o framework constrói o middleware do filho separadamente, e uma escrita externa executada ali escaparia do trace que deriva o status e a auditoria do run;
* subagentes poderão escrever somente em cópias isoladas do `StateBackend`, sob `/tmp/subagents/**`, limitadas a 16 arquivos e 256 KiB e descartadas antes do retorno; nenhuma dessas entradas deverá alcançar `agent_thread_files`;
* conteúdo de filesystem, memória, lembretes, web, Gmail e Notion MCP será dado não confiável e jamais ampliará uma allowlist ou concederá proveniência para mutação.

## 3.5 Referência oficial de orquestração

A implementação de subagentes, planejamento e aprovações humanas deverá consultar a skill oficial [`deep-agents-orchestration`](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/deep-agents-orchestration/SKILL.md), instalada no ambiente do Codex em `~/.codex/skills/deep-agents-orchestration`.

Essa referência cobre `SubAgentMiddleware`, `TodoListMiddleware` e `HumanInTheLoopMiddleware`. Ela orienta a implementação, mas não substitui as regras deste SPEC sobre tools específicas, validação, autorização, persistência e auditabilidade.

---

# 4. Escopo da V1

## Incluído

### Telegram

* recebimento de mensagens de texto;
* identificação do usuário;
* validação de usuário autorizado;
* envio de respostas;
* webhook HTTP.

### Agent

* Deep Agents;
* tool calling;
* gerenciamento de contexto;
* interpretação de linguagem natural;
* planejamento quando necessário.

### Notion

Operações mínimas:

```text
create_task
search_tasks
update_task
complete_task
search_projects
```

### Persistência

PostgreSQL deverá armazenar dados internos do agente.

Inicialmente:

* threads;
* mensagens/contexto quando necessário;
* configurações internas;
* auditoria das execuções;
* tool calls;
* erros.

---

# 5. Fora do escopo do núcleo V1

Não deverão ser implementados inicialmente:

* WhatsApp;
* interface web;
* múltiplos usuários;
* RAG complexo;
* vector database;
* Redis;
* filas distribuídas;
* Kubernetes;
* dashboard;
* observabilidade avançada;
* processamento de voz;
* automações proativas;
* scheduling avançado.

Esses recursos poderão ser adicionados posteriormente.

## Extensões implementadas nos marcos M4–M6

Após a estabilização do núcleo V1, o escopo foi deliberadamente ampliado:

* Google Calendar `primary`: listar, criar e atualizar eventos pessoais não recorrentes e calcular disponibilidade;
* Gmail: busca estruturada, leitura MIME paginada e criação de drafts plaintext, sem envio;
* três subagentes stateless (`task-agent`, `calendar-agent`, `email-agent`) com leitura por domínio, fontes compartilhadas read-only e scratch efêmero;
* o Chief continua sendo o único agente com mutações externas ou duráveis.

Calendar e Gmail são opcionais por configuração. Desabilitar seus flags remove
as tools correspondentes sem alterar schema nem apagar dados.

### API para o simulador cos-mariana

O Personal-CoS também oferece a superfície RADAR alvo do simulador
`cos-mariana`: `POST /v1/threads`, `POST /v1/threads/{thread_id}/messages`,
`GET /v1/threads/{thread_id}/messages/{message_id}` e `GET /health`.
As rotas de thread exigem `Authorization: Bearer` com `RADAR_API_KEY` e usam
`Idempotency-Key` persistida. Cada sessão sintética recebe uma thread própria,
separada das threads Telegram. O agente dessa interface não recebe tools,
subagentes nem acesso ao workspace, memória ou integrações pessoais: mensagens
simuladas produzem aconselhamento hipotético, sem ler ou alterar dados reais.
O contexto aceita o dia simulado e, quando fornecido, um timestamp ISO 8601 com
fuso horário, que também é encaminhado ao agente.
Sem chave configurada, as rotas autenticadas ficam desabilitadas.

---

# 6. Arquitetura

```text
                       INTERNET
                           │
                           ▼
                     Telegram API
                           │
                           │ webhook
                           ▼
                 ┌───────────────────┐
                 │      FastAPI      │
                 │                   │
                 │ Telegram endpoint │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Application Layer │
                 │                   │
                 │ Auth              │
                 │ Validation        │
                 │ Agent invocation  │
                 │ Logging           │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │    Deep Agent     │
                 │                   │
                 │ Reasoning         │
                 │ Planning          │
                 │ Tool selection    │
                 └─────────┬─────────┘
                           │
                   controlled tools
                           │
              ┌────────────┴─────────────┐
              ▼                          ▼
       ┌──────────────┐           ┌──────────────┐
       │ Notion Tools │           │ Future Tools │
       └──────┬───────┘           └──────────────┘
              │
              ▼
         Notion API


Application / Agent
        │
        ▼
   PostgreSQL

cos-mariana → Bearer API → Application → Agent sem tools
                                  │
                                  └→ PostgreSQL (thread + idempotency + audit)
```

Depois do M6, o bloco Deep Agent é composto assim:

```text
Chief of Staff — único escritor durável
   ├── task-agent       → pesquisas de tarefas/projetos
   ├── calendar-agent   → agenda e disponibilidade
   └── email-agent      → busca e leitura de e-mail
```

Os filhos recebem somente o relatório final como fronteira de retorno; ids
encontrados por eles não autorizam uma mutação do Chief.

---

# 7. Infraestrutura

A aplicação será executada inicialmente em VPS própria utilizando Docker.

Estrutura mínima:

```text
Docker Compose
│
├── personal-agent
│
└── postgres
```

Não será utilizado Redis inicialmente.

---

# 8. Stack

## Linguagem

Python 3.12+

## Agent framework

```text
LangChain
Deep Agents
LangGraph
```

## API

```text
FastAPI
Uvicorn
```

## Banco

```text
PostgreSQL
```

## Integrações

```text
Telegram Bot API
Notion API
Google Calendar API
Gmail API
```

## Infraestrutura

```text
Docker
Docker Compose
GitHub
VPS Linux
```

---

# 9. Estrutura do repositório

```text
personal-chief-of-staff/
│
├── app/
│   │
│   ├── main.py
│   ├── config.py
│   │
│   ├── api/
│   │   └── telegram_webhook.py
│   │
│   ├── agent/
│   │   ├── agent.py
│   │   ├── prompts.py
│   │   ├── memory.py
│   │   └── state.py
│   │
│   ├── tools/
│   │   ├── tasks.py
│   │   └── projects.py
│   │
│   ├── integrations/
│   │   ├── telegram_client.py
│   │   └── notion_client.py
│   │
│   ├── services/
│   │   ├── task_service.py
│   │   └── agent_service.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   └── models.py
│   │
│   └── security/
│       └── telegram_auth.py
│
├── tests/
│
├── scripts/
│
├── Dockerfile
├── docker-compose.yml
│
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── SPEC.md
├── PLAN.md
└── README.md
```

---

# 10. Fluxo de mensagem

## Entrada

Telegram envia:

```json
{
  "message": {
    "from": {
      "id": 123456
    },
    "text": "Crie uma tarefa para revisar o fluxo de caixa amanhã"
  }
}
```

## Autenticação

Aplicação valida:

```text
telegram_user_id == TELEGRAM_ALLOWED_USER_ID
```

Caso contrário:

```text
HTTP 200
nenhuma ação
```

O sistema não deve revelar informações sobre o usuário autorizado.

---

# 11. Fluxo do agente

```text
Mensagem
   ↓
Normalização
   ↓
Recuperação da thread
   ↓
Deep Agent
   ↓
Determinação da intenção
   ↓
Tool call
   ↓
Validação
   ↓
Execução
   ↓
Resultado
   ↓
Resposta natural
   ↓
Telegram
```

---

# 12. Tools

## create_task

Cria uma tarefa no Notion.

Input:

```python
title: str
due_date: date | None
project_id: str | None
notes: str | None
```

Retorno:

```python
{
    "ok": True,
    "outcome": "succeeded",
    "task": {...},
}
```

Todas as tools utilizam o mesmo discriminador de resultado:

```python
{"ok": True, "outcome": "succeeded", ...}
{"ok": False, "outcome": "failed", "error": "...", "message": "..."}
{"ok": False, "outcome": "unknown", ...}  # a escrita pode ter acontecido
{"ok": False, "outcome": "partial", ...}  # somente parte foi confirmada
```

Resultados `unknown` e `partial` não deverão ser repetidos automaticamente. O estado atual deverá ser reconciliado antes de uma nova tentativa.

---

## search_tasks

Pesquisa tarefas.

Input:

```python
query: str | None
status: str | None
project_id: str | None
due_before: date | None
due_after: date | None
limit: int = 20
```

---

## update_task

Atualiza propriedades permitidas.

Input:

```python
task_id: str
title: str | None
due_date: date | None
project_id: str | None
notes: str | None
```

---

## complete_task

Input:

```python
task_id: str
```

---

## search_projects

Input:

```python
query: str
limit: int = 10
```

Campos `task_id` e `project_id` aceitam somente UUIDs do Notion. Antes de ler ou escrever, o service deverá confirmar que a página pertence ao data source configurado. No agente, uma mutação por ID só poderá usar o único resultado da busca correspondente na mesma execução; múltiplos resultados exigem refinamento ou confirmação explícita.

## Google Calendar (M4)

```text
list_events
create_event
update_event
find_available_slots
```

Somente o calendário `primary` é acessível. Eventos timed exigem RFC3339 com
offset; all-day usa início e fim inclusivos na tool e fim exclusivo apenas no
payload Google. Intervalos são limitados a 31 dias. A integração não cria nem
altera recorrência, convidados, convites ou calendários secundários e não
oferece exclusão. `update_event` exige um único resultado correspondente de
`list_events` no run do Chief e utiliza ETag.

## Gmail (M5)

```text
search_email
read_email
draft_email
```

A busca aceita somente filtros estruturados; a aplicação constrói a sintaxe do
Gmail. `read_email` exige id retornado por busca no run do Chief, pagina o corpo
e não baixa anexos. `draft_email` valida headers e destinatários e cria apenas
MIME `text/plain`. Não existe `send_email`: SEND permanece estruturalmente fora
da superfície do agente.

## Resultados Google

Leituras repetem `429`/`5xx` com backoff. Escritas não fazem retry cego. Uma
resposta perdida ou uma confirmação inválida depois de uma escrita produz
`outcome="unknown"`; Calendar tenta reconciliar pelo id remoto gerado pelo
cliente, enquanto draft do Gmail não possui replay nem reconciliação insegura.

---

# 13. Identificação de projetos

Quando o usuário mencionar algo que possa representar um projeto:

```text
"Builders"
"Programa Builders"
"Builders C3"
```

o agente deverá utilizar:

```text
search_projects
```

antes de criar a tarefa.

Quando houver correspondência suficientemente clara, deverá utilizar o projeto existente.

Quando houver ambiguidade relevante, deverá perguntar ao usuário.

Exemplo:

> Encontrei dois projetos relacionados a "Builders": Programa de Builders e Builders — Pesquisa. Qual deles você quis dizer?

---

# 14. Datas

O sistema deverá interpretar expressões naturais como:

```text
amanhã
sexta
sexta-feira
semana que vem
dia 15
segunda de manhã
até o final da semana
```

O timezone padrão será:

```text
America/Bahia
```

Datas salvas no Notion deverão ser normalizadas.

---

# 15. Confirmações

A V1 deve evitar confirmações desnecessárias.

Operações comuns poderão ser executadas diretamente.

Exemplo:

> Crie uma tarefa para revisar o orçamento amanhã.

Pode ser executada diretamente.

Operações de risco devem solicitar confirmação.

Exemplos futuros:

```text
excluir tarefa
excluir projeto
enviar e-mail
alterar grande quantidade de registros
```

---

# 16. Memória

Devem existir dois conceitos distintos.

## Thread memory

Contexto da conversa atual.

Exemplo:

```text
Usuário:
Estou falando do projeto Builders.

Usuário:
Crie uma tarefa de revisar o edital amanhã.
```

O agente deve entender que a tarefa provavelmente pertence ao projeto anteriormente mencionado.

---

## Long-term memory

Não será prioridade da V1.

Quando implementada, deverá armazenar apenas informações úteis para melhorar interações futuras.

Exemplos:

```text
preferências
projetos recorrentes
pessoas
aliases
rotinas
```

Long-term memory não deve ser confundida com histórico completo de conversa.

---

# 17. Banco de dados

Estrutura inicial sugerida:

## agent_threads

```text
id
telegram_user_id
created_at
updated_at
```

## agent_runs

```text
id
thread_id
input
output
status
started_at
finished_at
```

## tool_calls

```text
id
run_id
tool_name
arguments
result
status
created_at
duration_ms
```

## errors

```text
id
run_id
error_type
message
created_at
```

Evitar armazenar secrets ou dados sensíveis desnecessários.

---

# 18. Observabilidade mínima

Cada execução deverá permitir responder:

```text
Quem chamou?
Quando?
Qual mensagem?
Qual agente executou?
Qual ferramenta foi utilizada?
Quais parâmetros?
Qual resultado?
Quanto tempo levou?
Houve erro?
```

Não será criado dashboard na V1.

Logs estruturados serão suficientes.

---

# 19. Variáveis de ambiente

`.env.example`:

```env
# Application
APP_ENV=development
APP_TIMEZONE=America/Bahia
LOG_LEVEL=INFO
APP_BIND_ADDRESS=127.0.0.1

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USER_ID=
TELEGRAM_WEBHOOK_SECRET=

# Notion
NOTION_TOKEN=
NOTION_TASK_DATA_SOURCE_ID=
NOTION_PROJECT_DATA_SOURCE_ID=

# Model
AGENT_MODEL=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=

# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=personal_agent
POSTGRES_USER=personal_agent
POSTGRES_PASSWORD=
```

Desde a versão `2025-09-03` da API do Notion, o objeto consultável é o *data source*, não o database que o contém. Por isso as variáveis usam `DATA_SOURCE_ID`; os nomes antigos (`NOTION_TASK_DATABASE_ID`, `NOTION_PROJECT_DATABASE_ID`) continuam sendo aceitos para compatibilidade.

`.env` nunca deverá ser versionado.

Anthropic e OpenAI são os providers suportados inicialmente. Os adapters correspondentes deverão ser dependências diretas e versionadas; o Compose deverá encaminhar a spec e as credenciais sem registrá-las em logs. O contexto de build deverá excluir `.env` e demais arquivos locais sensíveis.

---

# 20. Docker

O sistema deverá iniciar através de:

```bash
docker compose up -d
```

Serviços:

```yaml
services:
  agent:
    ...
    
  postgres:
    ...
```

A aplicação deve ser stateless sempre que possível.

Dados persistentes deverão residir no PostgreSQL ou em volumes explicitamente definidos.

As portas da aplicação e do PostgreSQL deverão ser publicadas em loopback por padrão. Exposição externa deverá acontecer por reverse proxy e somente para os endpoints necessários; PostgreSQL não deverá ficar acessível pela Internet.

---

# 21. Desenvolvimento local

O ambiente local deverá possuir paridade razoável com produção.

Fluxo esperado:

```text
git clone
↓
criar .env
↓
docker compose up
↓
executar testes
↓
desenvolver
```

O desenvolvedor não deverá depender da VPS para desenvolvimento normal.

---

# 22. Deployment inicial

Processo inicial:

```text
VS Code
   ↓
Git
   ↓
GitHub
   ↓
git pull na VPS
   ↓
docker compose build
   ↓
docker compose up -d
```

Não implementar CI/CD na primeira entrega.

---

# 23. Critérios de aceite da V1

A V1 estará funcional quando os seguintes testes puderem ser realizados pelo Telegram.

### Criar tarefa

```text
Crie uma tarefa para revisar meu orçamento amanhã.
```

Resultado esperado:

* tarefa criada;
* data correta;
* confirmação enviada.

### Criar tarefa vinculada a projeto

```text
No projeto Builders, crie uma tarefa para revisar o edital sexta.
```

Resultado:

* projeto encontrado;
* tarefa criada;
* relação registrada.

### Consultar

```text
O que tenho para fazer amanhã?
```

Resultado:

* agente consulta Notion;
* retorna lista correta.

### Atualizar

```text
Mude a tarefa de revisar orçamento para sexta.
```

Resultado:

* tarefa identificada;
* data atualizada.

### Concluir

```text
Concluí a tarefa de revisar orçamento.
```

Resultado:

* tarefa identificada;
* status alterado.

---

# 24. Critérios não funcionais

## Segurança

* secrets exclusivamente em variáveis de ambiente;
* usuário Telegram validado;
* nenhuma ferramenta irrestrita;
* validação antes de execução.

## Resiliência

Falhas externas não devem derrubar o serviço.

Exemplo:

```text
Notion indisponível
```

Resposta:

> Não consegui acessar o Notion agora. A tarefa não foi criada.

Nunca afirmar sucesso quando a integração retornar erro.

Retries deverão considerar idempotência. Leituras e atribuições idempotentes podem repetir falhas transitórias; criação de página e append de conteúdo não deverão ser repetidos quando a resposta se perder, pois o efeito pode já ter acontecido.

## Idempotência

Webhooks duplicados do Telegram não devem gerar tarefas duplicadas.

O `update_id` do Telegram deverá ser armazenado ou controlado.

## Logging

Todas as operações relevantes deverão possuir logs estruturados.

---

# 25. Evolução prevista

Topologia entregue no M6:

```text
Telegram
   │
   ▼
Personal Chief of Staff
   │
   ├── Task Agent
   ├── Calendar Agent
   └── Email Agent
```

Research Agent continua adiado até possuir responsabilidade, contexto e tools
próprios. Knowledge Agent e Personal Admin Agent também não são criados por
antecipação.

Integrações atuais e futuras:

```text
Atuais: Notion, Google Calendar, Gmail, Web
Futuras: Google Drive, GitHub, Home automation, outros serviços
```

---

# 26. Visão futura

O objetivo final é que o Telegram seja apenas uma das interfaces.

A arquitetura deverá caminhar para:

```text
              Interfaces

 Telegram      Web       Voice
      \          |         /
       \         |        /
        ─ Personal Agent ─
                 │
            Deep Agents
                 │
        ┌────────┼────────┐
        │        │        │
      Tasks   Calendar   Email
        │        │        │
      Notion   Google    Gmail
```

O sistema deverá evoluir progressivamente, priorizando confiabilidade sobre quantidade de funcionalidades.

---

# 27. Regra fundamental

Antes de adicionar qualquer nova tecnologia ou componente, responder:

> Qual problema concreto da experiência do usuário isso resolve?

Se não houver uma resposta clara, o componente não deverá ser adicionado.

---

# 28. Integração RADAR

O RADAR é um domínio opcional e versionado separadamente. O RADAR-CoS não
duplica sua TBox nem recebe acesso genérico ao vault: instala `radar-vault` por
commit imutável, carrega Core, regras e políticas do pacote e monta a ABox viva
em volume persistente.

```text
RADAR-CoS                            radar-vault
identidade Telegram ───────────────→ Principal
configuração e lifecycle ──────────→ runtime versionado
volume /data/radar-vault ──────────→ ABox canônica
```

Na Fase 1, `RADAR_ENABLED=false` é o padrão e nenhuma tool RADAR é publicada.
Quando habilitado, o startup só considera a integração pronta se caminho,
contexto, `person_id`, identidade Telegram e allowlist estiverem completos; a
TBox estiver autorizada; a ABox usar schema legível; a estrutura for válida; e
o processo tiver permissões para leitura, lock e auditoria. Qualquer falha deixa
o RADAR degradado sem derrubar `/health` nem as outras integrações.

O `Principal` é construído pelo service a partir do usuário Telegram permitido
e do mapeamento configurado para uma entidade `person` no mesmo contexto. O
modelo nunca fornece identidade, pessoa, contexto, grants ou autonomia. Nesta
fase os grants e operações autônomas são vazios e o runtime existe somente para
validar o contrato de startup. Na Fase 2, estado `ready` publica apenas
`radar_search_entities`, `radar_read_entity`, `radar_get_context`,
`radar_list_action_types` e `radar_validate_context`. Seus schemas não contêm
contexto, identidade, grants, autonomia, paths, revisão ou payload de operação.
O service injeta o contexto confiável e devolve DTOs limitados; buscas usam
paginação pequena com indicador de próxima página, sem paths, frontmatter
arbitrário ou histórico.

Texto retornado pela ABox é dado não confiável, não instrução. A auditoria de
`tool_calls` usa projeções por ferramenta e nunca guarda descrição, evidência,
corpo ou histórico completos; `MemoryService` recusa IDs RADAR. Scheduler e
subagentes não recebem RADAR nesta fase. Consultas somente escrevem o audit
trail próprio do RADAR, nunca os Markdown canônicos da ABox.

Na Fase 3, o Chief acrescenta cinco consultas compostas read-only: riscos por
objetivo/projeto, fila de ações atrasadas ou com revisão vencida, decisões com
evidências, compromissos por pessoa e contexto de dois saltos de reunião/caso.
A validação existente completa os seis cenários diários. Classificação de
atraso, travessia e associação são feitas no `RadarService`, não no prompt. Os
resultados continuam limitados e projetados; auditoria persiste ids, contagens,
datas e códigos, nunca texto livre da ABox.

Como correção complementar aos testes avançados do Telegram, a superfície
read-only inclui `radar_resolve_entities` (até oito referências agrupadas, sem
escolha de candidato) e `radar_get_operational_brief` (uma leitura de grafo
limitada para routine, project, objective ou case). O briefing distingue itens
abertos, decisões vigentes/substituídas, riscos, ações, compromissos pendentes,
indicadores e evidências, com contagens e truncamento explícitos. Nenhuma das
duas leituras cria proveniência de mutação.

O grafo usa até 50 passos, mas esse teto não substitui o orçamento independente
configurável de 16 chamadas de tool e duas chamadas idênticas. Cada `AgentRun`
persiste somente passos, totais, contagem RADAR, fingerprints de repetições e
causa terminal. `GraphRecursionError` é classificado como `agent_step_limit`;
mensagens de orçamento ou repetição pedem divisão segura do pedido e nunca
alegam alteração parcial.

Não existe `management-agent`: as consultas compostas reduziram cada cenário a
uma única tool do Chief e a evidência atual não mostra responsabilidade
cross-domain própria que justifique outro filho stateless. Scheduler e os três
subagentes existentes continuam sem qualquer tool RADAR. Essa decisão deve ser
reavaliada apenas com traces de uso real que mostrem pesquisas gerenciais
multi-etapas frequentes.

Fases posteriores devem seguir `integração → service → testes → tool → agente`:
primeiro leituras específicas, depois uso diário e somente então mutações com
proposta persistida, aprovação, revisão otimista e idempotência. Subagentes e
scheduler permanecem sem escrita RADAR.

Na Fase 4, `RADAR_WRITES_ENABLED=false` continua como default separado do
preflight de leitura. Somente se o runtime expuser a API pública `prepare()` e
o host ativar uma allowlist pequena, o Chief recebe tools de proposta para
`capture_issue`, `delegate` e `review`. Elas aceitam apenas argumentos de
negócio; o `RadarService` reconstrói Principal/contexto/grants confiáveis,
valida parâmetros, alvo, regras, política e revisão sem efeitos e persiste um
payload imutável em `pending_radar_operations` com TTL e `idempotency_key`.

O Telegram resolve uma proposta ativa da própria thread: “não” a rejeita sem
runtime ou modelo; “sim” faz claim single-use, reautoriza o Principal atual e
executa exclusivamente o payload salvo com a mesma chave. Conflito de revisão
é terminal e não re-prepara. Falha de persistência fica `uncertain` e só pode
ser reconciliada pelo mesmo payload/chave. A auditoria da aplicação registra
hashes de texto, ids, revisões e códigos, nunca prosa da ABox; scheduler e
subagentes não recebem as tools de proposta nem executores.

## 28.1 Contrato conversacional humano do RADAR

IDs canônicos, revisões e símbolos da ontologia são identidade de máquina. A
interface conversa por título ou nome e traduz tipo, estado, relação, operação
e motivo de atenção para rótulos curtos em português. Esses códigos só podem
aparecer quando o usuário pedir explicitamente identificadores, auditoria ou
diagnóstico técnico. A resposta final passa por uma guarda determinística que
remove também IDs em minúsculas, revisões e deep links internos.

Uma busca com vários resultados vira uma lista numerada construída pela
aplicação a partir de resumos autorizados. Cada opção mostra título e, quando
disponíveis, tipo e estado. Se duas opções ainda forem indistinguíveis, o
sistema pede responsável, prazo ou contexto; nunca usa parte do ID como
desempate. A thread pode manter apenas uma lista numérica pendente entre RADAR
e Notion, e a lista RADAR expira no mesmo TTL das propostas.

Uma mutação RADAR recebe proveniência apenas de uma busca com exatamente um
resultado, de uma escolha humana persistida pela aplicação ou, como exceção
técnica, da leitura do ID que o usuário digitou no pedido atual. Ler um item
escolhido pelo modelo depois de uma busca ambígua não concede autoridade. A
seleção valida também o papel do item — alvo, executor ou evidência.

Referências confirmadas por tools podem sustentar expressões como “essa ação”
por um período curto. Elas entram no agente como resultado de tool não
confiável, nunca como instrução de sistema, não autorizam escrita e não
substituem nova leitura de estado, prazo ou qualquer fato atual.

Perguntas de confirmação e recibos são renderizados pela aplicação a partir de
um snapshot humano persistido. Em `delegate`, confirmação registra uma
**proposta de delegação**; o compromisso só fica aceito depois do aceite da
pessoa indicada. Essa distinção não pode ser substituída por uma narrativa de
sucesso do modelo.

## 28.2 Medição, captura atribuída e idempotência de intenção

O Chief pode propor `record_measurement` somente quando a operação compatível
estiver presente no pacote instalado. O schema exposto contém indicador, valor
finito, instante e título da evidência. `evidence_source` e `evidence_text` são
derivados da mensagem Telegram autenticada e não são argumentos do modelo. A
execução atualiza apenas `current`, `measured_at` e histórico operacional do
Indicator; baseline, meta, fórmula, cadência, unidade e direção são preservados.

`capture_issue` aceita prioridade do vocabulário e Person responsável
opcionais. Esses dados são aplicados ao ManagementItem/Issue e nunca ao Case.
A seleção de responsável e indicador segue a mesma proveniência forte das
demais mutações.

Cada proposta calcula fingerprint semântico versionado depois da normalização:
ator, contexto, operação, alvo, parâmetros de negócio e SHA-256 do texto-fonte.
Match recente em proposta pendente ou executada cria somente um registro de
duplicidade não executável e uma resposta a partir do snapshot público salvo.
O comando exato `registrar como novo fato` consome uma autorização de override
uma única vez e cria outra proposta, ainda sujeita à confirmação normal. A
chave de execução continua `radar:<proposal_uuid>` e duas aprovações
concorrentes só podem obter um claim.

## 28.3 Linguagem pública e causas seguras

O prompt descreve o RADAR somente por capacidades de negócio. Toda resposta
passa também por uma barreira determinística que remove nomes no padrão
`radar_*`, registries e contagens da superfície interna, inclusive quando o
usuário pede identificadores técnicos. Esse pedido pode liberar IDs canônicos
de entidades autorizadas, mas nunca detalhes da arquitetura de tools.

Falhas entre `radar-vault` e host usam uma allowlist de códigos públicos. Texto
da exceção, path, título, frontmatter ou conteúdo da ABox não entra em resposta,
log ou resultado persistido. Leitura, escrita, recusa de domínio e limite do
agente têm aberturas distintas. O renderer aceita `*itálico*` no mesmo caminho
inline usado por HTML clássico e Rich Messages, sem interpretar multiplicação,
bullet solto, negrito ou marcador desbalanceado.

## 28.4 Gerações e operação segura da ABox

O runtime calcula uma geração barata das notas da ABox. Antes de leitura,
preparação ou execução, mudança de manifest dispara `Vault.validate()` e as
mesmas verificações de schema, pessoa e contexto do startup. Geração inválida
muda o relatório para `degraded`, bloqueia reads/writes e expõe somente
`vault_changed_invalid`, contagem de entidades conhecida e número de erros.

Obsidian Headless sincroniza exclusivamente para staging. Depois de `Fully
Synced`, com o agente parado, a CLI operacional obtém um snapshot estável,
valida-o com o pacote instalado, preserva o `.radar/` da geração ativa, cria
backup completo e só então promove por troca de diretório no mesmo filesystem.
Snapshot inválido não altera o ativo. Restore valida a cópia e preserva ABox,
audit, receipts e journals; IDs duplicados nunca são corrigidos automaticamente.
