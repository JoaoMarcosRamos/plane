# ARCHITECTURE — RADAR Core

Decisões consolidadas a partir de `phase-0/PLANE_MAP.md`, `REUSE_MAP.md`, `DOMAIN_COUPLING.md` e `RUNTIME_SEAM_VALIDATION.md`. PostgreSQL é a fonte de verdade; o shell do Plane fornece sessão, workspace, membership e UI.

## Estado vigente — 05/10/2026

Fase 0 encerrada com CONDITIONAL GO; Command Layer/provenance backend, runtime 1.3, Agent Config 1.4, Risk Review 1.5 e Today 1.6 entregues localmente. Próximas etapas: **1.7 — colaboração necessária ao MVP** e **1.8 — E2E/piloto**. As decisões abaixo distinguem a fundação histórica de sua evolução; o [índice técnico](README.md) reúne contratos e evidências atuais.

## ADR — RADAR Base Model

RadarBaseModel próprio; não herda Plane BaseModel, AuditModel ou SoftDeleteModel. TimeAuditModel foi inspecionado e só declara timestamps (R1); neste slice redeclaramos os dois campos para evitar o import do módulo que também importa tarefas Celery. UUID segue uuid4. ChangeTrackerMixin é puro, mas não é necessário agora. Auditoria é explícita. Managers filtram deleted_at; delete de instância e queryset são bloqueados. Exclusão futura será command transacional.

## ADR — Explicit Actor

Actor imutável na application layer: actor_type, actor_id, reason, source, correlation_id, run_id. Tipos human/agent/system/integration; na fundação 0.3A somente human era autorizado. A Fase 1 acrescentou grants e autenticação explícita de agentes/integrações. Nunca usar crum.get_current_user como fonte de provenance. Commands validam usuário ativo e membership.

## ADR — Commands from day one

ORM é detalhe interno; API, UI e futuros adaptadores convergem para commands. CreateObject e UpdateObject validam tenant/tipo/permissão e persistem em transaction.atomic. Atualizações travam a linha, preservam created_by e incrementam version. Na fundação 0.3A não havia Outbox ou Domain Events. A Fase 1 acrescentou dispatcher comum e persistência transacional de provenance, execução, eventos e outbox, sem publisher operacional.

## ADR — Backend isolation

App `apps/api/plane/radar` com migrations próprias. FKs externas somente Workspace e User; nenhuma FK para Project, Issue ou ProjectBaseModel. Dois touch points backend: INSTALLED_APPS e montagem de URLs sob API de sessão; sem Public API v1.

## ADR — ObjectType scope

ObjectType pertence ao workspace; chave única entre registros não excluídos. Tipos objective/project/decision/action/risk são dados is_system=true, não models. Inicialização lazy por command no primeiro acesso aos tipos ou criação; trava Workspace e é idempotente, independente de workspace_seed. Um membro autenticado (inclusive guest para leitura) pode inicializar; objetos exigem member/admin.

## ADR — Content e frontend

HTML no próprio Object, compatível com onChange do RichTextEditor atual. Sanitização compartilhada na aplicação, sem editor colaborativo ou anexos. RadarRootStore MobX é provido por RadarStoreProvider no layout (radar), com vida útil por workspace; não entra no root.store do Plane nem recebe stores Project/Issue. Lista usa BaseListLayout agrupada por tipo; Object Page usa API real.

## Sequência histórica da fundação

0.3A Foundation primeiro; 0.3B Properties + Relations após aceitação, ambas entregues. A visão final mantém Object / Type / Relation, Command Layer, Provenance e Human-Agent Loop.

## Validação implementada

[CORE_VERTICAL_SLICE_REPORT.md](./CORE_VERTICAL_SLICE_REPORT.md) confirma commands desde o primeiro write, criador preservado fora de request, versões serializadas sob concorrência e operação em workspace sem Projects. Na entrega 0.3A não havia eventos nem registro persistido de reason/source/correlation/run; a auditoria mínima era created_by/updated_by. A Fase 1 adicionou esses registros; autoria histórica não foi retroativamente fabricada.

## ADR — Semantic Model (0.3B)

Decisões fechadas antes da migration em [SEMANTIC_MODEL_ADR.md](./SEMANTIC_MODEL_ADR.md): PropertyValue JSONB tipado, RelationType por workspace com source/target/allowed_pairs, aresta direcionada única e backlinks derivados. Seeds seguem subconjunto normativo Core 3.2.0 (cinco tipos do spike + Person); autoria, locks e versões dos endpoints são explícitos. Invariantes de datas/score são estruturais, sem engine gerencial. Relatório de implementação/validação: [SEMANTIC_MODEL_REPORT.md](./SEMANTIC_MODEL_REPORT.md).

## ADR — Semantic UI (0.4)

Object Page renderiza definições persistidas; não possui formulário específico por ObjectType. O seletor aplica domain/codomain/allowed_pairs e membership do workspace, com validação definitiva no command. Backlinks são visualizações de Relation, não arestas duplicadas. Guest usa a permissão de workspace do shell para leitura.

Snapshots de propriedades e relações compartilham Object.version. Store realiza leituras paralelas e retry limitado quando cruzadas por writes. UI mantém os formulários montados com dados anteriores durante refresh; desabilita mutações stale e preserva os rascunhos de outros campos e title/content. Falha permite Retry sem tratar write confirmado como write fracassado. Componentes Propel e composites Plane são reutilizados sem stores de Issue/Project. Resultado: [SEMANTIC_UI_REPORT.md](./SEMANTIC_UI_REPORT.md). 0.5 e 0.6 foram concluídas posteriormente; ver [cenário](GOVERNANCE_SCENARIO_REPORT.md) e [encerramento do spike](SPIKE_REPORT.md).

## ADR — Runtime e configuração de produto (1.3/1.4)

Plane autentica sessão/membership, resolve vínculo usuário/workspace/agente e conserva domínio, grants e configuração no PostgreSQL. COS_AGENT_V2 hospeda o DeepAgentsAdapter atrás de DTOs independentes do harness, com ledger durável de requests, estados e eventos. O caminho Plane → runtime é separado do caminho CoS → Command Layer. A API de simulação e o canal Telegram permanecem contratos próprios.

AgentConfiguration tem um registro versionado por vínculo de canal Plane, quatro blocos JSON tipados e gravação por comando interno auditado. Permissions restringem o grant vigente; nunca o ampliam. Owner/admin com vínculo próprio pode editar. Contexto limitado e configuração são copiados por execução e entram no fingerprint de autoridade. Alteração bloqueia acesso/replay/resume antigo, preservando a intenção histórica, sem cancelamento remoto automático.

O executor de produto permanece somente leitura, sem tools, filesystem, memória pessoal ou subagentes. Risk Review, revisão na UI e aplicação de propostas foram entregues em 1.5. Today 1.6 projeta atenção gerencial em uma consulta somente leitura, sem chamar o runtime ou executar commands; ver [Today](TODAY.md). Contratos: [Agent Runtime](AGENT_RUNTIME.md), [Agent Config](AGENT_CONFIG.md), [Command Layer](COMMAND_LAYER.md). Evidências e gates: [prontidão após 1.6](NEXT_PHASE_READINESS.md).
