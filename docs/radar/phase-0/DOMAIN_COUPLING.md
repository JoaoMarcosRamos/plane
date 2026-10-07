# DOMAIN_COUPLING — Acoplamento do Plane a Project → WorkItem

> Fase 0 · Prompt 0.1 · 2026-10-03 · branch `radar-phase-0-spike`
> Análise somente leitura. Base factual: [PLANE_MAP.md](./PLANE_MAP.md). Reuso: [REUSE_MAP.md](./REUSE_MAP.md).

## 1. Pergunta da Fase 0 e hipótese

> O Plane pode servir como product shell do RADAR sem nos prender ao modelo `Project → WorkItem`?

**Hipótese (a validar no spike, não é o Go/No-Go):** sim, **desde que** o RADAR Core seja um app Django e uma app de frontend paralelos ao "Projects app", e não uma extensão de `Issue`. O acoplamento a Project/WorkItem está concentrado no domínio de issues e nos pipelines de backend (activity, notification, relations). O shell (auth, workspace, navegação, design system, editor, layouts genéricos, filtros, pickers) está desacoplado ou tem seams explícitos.

O risco principal não é técnico-estrutural. É de **padrões de backend**: o Plane não tem command layer, não tem outbox e infere o ator por thread-local. Esses padrões não podem ser herdados pelo Core (§3).

---

## 2. Vetores de acoplamento

Severidade = impacto para o RADAR se o vetor for ignorado. **Alta**: bloqueia ou contamina o Core. **Média**: exige código RADAR ou touch point. **Baixa**: overhead ou ajuste trivial.

### C1 · `ProjectBaseModel`: project obrigatório em todo o domínio de trabalho — Alta

- **Evidência:** `apps/api/plane/db/models/project.py:180`. Herdam dele `Issue`, todos os `Issue*` (Comment, Activity, Relation, Link, Attachment, Subscriber, Reaction…), `State`, `Cycle`, `Module`, `Estimate`, `Intake`. `IssueComment.issue` e `IssueActivity.issue` são FKs para `Issue`.
- **Consequência:** comments, activity, relations, subscribers do Plane não podem ser reusados para objetos RADAR no backend.
- **Mitigação:** o Core herda de `BaseModel` com FK própria para `db.Workspace`. **Não** usar `WorkspaceBaseModel`: ele carrega uma coluna `project` (nullable) que reintroduz o conceito.

### C2 · Rotas e shell centrados em `(projects)` — Média

- **Evidência:** `apps/web/app/routes/core.ts` — tudo de workspace vive sob `(projects)/layout.tsx`; entidades de trabalho sob `/:slug/projects/:projectId/…`. `useWorkspacePaths` trata qualquer path não-wiki/ai/settings como "projects".
- **Mitigação:** route group `(radar)/` irmão de `(projects)` via `routes/extended.ts` (vazio hoje, merge por arquivo), App Rail ligado, `isRadarPath`. Rotas: `/:slug/radar`, `/:slug/radar/types/:typeKey`, `/:slug/radar/objects/:objectId`.

### C3 · Permissão padrão em nível de projeto — Baixa

- **Evidência:** `apps/api/plane/app/permissions/base.py` — `allow_permission(..., level="PROJECT")` exige `kwargs["project_id"]`.
- **Mitigação:** sempre `level="WORKSPACE"` (já suportado). Políticas e aprovações do RADAR ficam no Command Layer, não em decorators de view.

### C4 · Pipeline de activity específico de Issue — Alta (para reuso) / nula (se não reusado)

- **Evidência:** `IssueActivity` (FK `issue`); `bgtasks/issue_activities_task.py` (1604 linhas, ~40 funções `track_*`/`create_*_activity` por campo fixo de Issue); `issue_activity.delay(...)` chamado em 41 pontos de `plane/app/views` e 14 em `plane/api/views/issue.py`.
- **Mitigação:** activity do RADAR é **derivada dos Domain Events** do Core (outbox). A UI reusa `ActivityBlockComponent` com `TWorkspaceBaseActivity`.

### C5 · Notifications: modelo genérico, produtor e UI específicos — Média

- **Evidência:** `Notification` tem `project` nullable, `entity_name`, `entity_identifier`, `data` JSON (genérico). Mas `bgtasks/notification_task.py` grava `entity_name="issue"` em todos os pontos, resolve subscribers via `IssueSubscriber`/menções em descrição de issue; `components/workspace-notifications/sidebar/notification-card/item.tsx` lê `notification.data.issue.id` e abre o peek de issue.
- **Mitigação:** produtor RADAR próprio (a partir de eventos). Na UI, branch por `entity_name` no card (touch point). Fora da Fase 0.

### C6 · Relações: Issue↔Issue, enum fechado, uma relação por par — Alta (para reuso)

- **Evidência:** `IssueRelation` (`db/models/issue.py`): FKs `issue` e `related_issue` para `Issue`; `relation_type` com 6 valores fixos (`blocked_by`, `relates_to`, `duplicate`, `start_before`, `finish_before`, `implemented_by`) e reverso calculado por `_REVERSE_MAPPING`; `UniqueConstraint(issue, related_issue)` → **no máximo uma relação entre o mesmo par**.
- **Consequência:** não suporta `RelationType` definido por dados, relações entre tipos diferentes, múltiplas relações tipadas entre o mesmo par, nem provenance por relação.
- **Mitigação:** `RelationType` + `Relation` próprios. O padrão de "par forward/reverse" serve de referência para backlinks (rótulo inverso por `RelationType`, ex.: `SUPPORTS` / "supported by").

### C7 · Tipos e propriedades: colunas fixas, sem EAV no CE — Alta (para reuso)

- **Evidência:** `Issue` tem campos fixos (`state`, `priority`, `start_date`, `target_date`, `estimate_point`, `assignees`, `labels`…). `IssueType` existe (workspace-level, `is_epic`, `level`) mas o CE **não tem** propriedades customizadas (sem `IssueProperty`/valores).
- **Mitigação:** `ObjectType`, `PropertyDefinition`, `PropertyValue` próprios. O motor rich-filters e os pickers de blocks se encaixam nos tipos de propriedade (`text`, `number`, `date`, `user`, `select`, `object_ref`).

### C8 · Enumerações fechadas espalhadas pelas camadas — Média

Cada integração de "novo tipo de entidade" com uma feature transversal do Plane exige adicionar um membro numa união/enum ou um `case`:

| Feature                   | Ponto fechado                                                                                                      |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Menções no editor / busca | `TSearchEntities` — `packages/types/src/search.ts:15`                                                              |
| Busca global (backend)    | dict `entity → filter_fn` — `apps/api/plane/app/views/search/base.py:278`                                          |
| Edição colaborativa       | `TDocumentTypes = "project_page"` — `apps/live/src/types/index.ts:26`; `services/page/handler.ts`                  |
| Command palette           | `TPowerKContextType` — `apps/web/components/power-k/core/types.ts:9`; `core/context-detector.ts`                   |
| Arquivos                  | `FileAsset.EntityTypeContext`, `asset_url` — `db/models/asset.py`; `get_entity_id_field` — `app/views/asset/v2.py` |
| Recentes                  | `EntityNameEnum` — `db/models/recent_visit.py`                                                                     |
| Favoritos                 | `switch` — `apps/web/hooks/use-favorite-item-details.tsx`                                                          |
| Webhooks                  | flags booleanas por entidade — `db/models/webhook.py`                                                              |

- **Mitigação:** nenhuma dessas é necessária para a Fase 0. Quando forem, cada uma é um touch point de 1–10 linhas, registrado em §4.

### C9 · Sem command layer; lógica em views; duas pilhas de API — Alta (para os princípios)

- **Evidência:** `plane/app/views/issue/base.py` (1367 linhas) contém regra de negócio, disparo de activity e serialização na view. `plane/api/views/issue.py` (API v1, API key) reimplementa os mesmos fluxos. Um agente usando a API v1 passa por código diferente do humano na web.
- **Conflito:** "Humano e agente usam o mesmo Command Layer / Domain Layer / Rules / Approvals".
- **Mitigação:** o Core expõe **commands** (ex.: `create_object`, `set_property_value`, `create_relation`) como a única via de escrita. Views DRF (humano) e o adaptador de runtime de agente chamam os mesmos commands. O Core não é exposto pela API v1.

### C10 · Ator implícito via thread-local — Alta (para provenance)

- **Evidência:** `BaseModel.save` (`db/models/base.py`) preenche `created_by`/`updated_by` com `crum.get_current_user()`. Em Celery, worker ou runtime de agente não há request → `None`. Aceita `created_by_id=` explícito.
- **Conflito:** "Provenance é obrigatório" e "Inferência de agente não pode virar fato silenciosamente".
- **Mitigação:** o Command Layer recebe um `Actor` explícito (humano | agente, id, run/session, fonte) e grava provenance em campos próprios do Core e no evento. `created_by` do Plane passa a ser só metadado de auditoria. Agente = `User` com `is_bot=True` (campo já existe) + metadados de runtime no evento.

### C11 · Eventos assíncronos sem outbox — Alta (para sincronização)

- **Evidência:** activity, notificações e webhooks disparados com `.delay()` direto da view, fora de `transaction.on_commit` (único uso de `on_commit` está em `plane/api/views/project.py`). Se a transação fizer rollback, o evento sai mesmo assim; se o broker cair, o evento se perde.
- **Conflito:** "Sincronização é feita por Domain Events + Transactional Outbox + Projection Worker" e "Graph DB é projeção, nunca segundo master".
- **Mitigação:** tabela `radar_outbox` gravada na **mesma transação** do command; worker (Celery beat ou processo dedicado) publica para projeções (activity, notification, graph). Não reutilizar o padrão `.delay()` do Plane no Core.

### C12 · Soft delete com cascata assíncrona — Média

- **Evidência:** `SoftDeleteModel.delete` (`db/mixins.py`) marca `deleted_at` e chama `soft_delete_related_objects.delay(...)` (`bgtasks/deletion_task.py`), que percorre FKs reversas e soft-deleta/anula em background, fora da transação, sem evento de domínio.
- **Consequência:** deletar um `Object` apagaria `Relation`/`PropertyValue` de forma assíncrona e invisível para a projeção → backlinks fantasmas e grafo divergente.
- **Mitigação:** delete é um command: soft-delete do objeto + relações + valores na mesma transação, com eventos no outbox. Modelos do Core sobrescrevem `delete()` (ou o command usa `QuerySet.update(deleted_at=…)`) para não acionar a cascata Celery.

### C13 · Migrations num único app `plane.db` — Média (merge com upstream)

- **Evidência:** 122 migrations em `apps/api/plane/db/migrations`; todo modelo do Plane está em `plane.db`.
- **Mitigação:** app Django próprio (`plane.radar` ou `radar_core`) com cadeia de migrations independente, dependendo da última migration de `db` existente na criação. Nunca adicionar modelos RADAR em `plane.db`.

### C14 · Carga do workspace busca dados de projeto — Baixa

- **Evidência:** `apps/web/layouts/auth-layout/workspace-wrapper.tsx:75-125` busca projetos parciais, permissões de projeto, estados do workspace, favoritos.
- **Mitigação:** tolerar na Fase 0 (funciona com zero projetos). Revisitar se o RADAR passar a ser a única app.

### C15 · Root store monolítico — Baixa

- **Evidência:** `apps/web/store/root.store.ts` compõe ~30 stores, incluindo `IssueRootStore`.
- **Mitigação:** store RADAR isolado (`RadarRootStore`) provido por contexto no layout `(radar)`, sem tocar no root store. Se precisar de user/workspace, recebe referência do root store existente.

### C16 · Editor colaborativo restrito a páginas de projeto — Média (fase posterior)

- **Evidência:** `apps/live/src/services/page/handler.ts` só instancia `ProjectPageService`; qualquer outro `documentType` lança `AppError`.
- **Mitigação:** Fase 0 usa `RichTextEditor` não colaborativo (salva HTML/JSON por PATCH). Colaboração: novo document type + service em `apps/live` (touch point médio).

---

## 3. Conflitos com os princípios do RADAR

| Princípio RADAR                                    | Como o Plane faz                                 | Decisão                                                                                                                                                 |
| -------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RADAR possui Core próprio                          | Domínio único `Project → Issue`                  | Core em app Django e app web paralelos (C1, C2, C13)                                                                                                    |
| Humano e agente usam o mesmo Command Layer         | Lógica em views; pilhas `app` e `api` duplicadas | Commands explícitos, únicos pontos de escrita (C9)                                                                                                      |
| Provenance obrigatório                             | Ator implícito por thread-local                  | `Actor` explícito + provenance por registro e por evento (C10)                                                                                          |
| Inferência de agente não vira fato silenciosamente | Sem conceito de status epistêmico                | Campo de status/origem em `PropertyValue` e `Relation` (ex.: `asserted` / `proposed` / `confirmed`), confirmação via command. A detalhar no SPIKE_PLAN. |
| PostgreSQL é source of truth                       | Postgres é o único store                         | Compatível                                                                                                                                              |
| Domain Events + Outbox + Projection Worker         | `.delay()` fora de transação; cascata async      | Outbox próprio; delete explícito (C11, C12)                                                                                                             |
| Graph DB é projeção                                | Não existe                                       | Fora da Fase 0; o outbox prepara o terreno                                                                                                              |
| Runtime atrás de adaptador                         | API v1 com API key                               | Agente chama commands via adaptador, não a API v1 (C9)                                                                                                  |

---

## 4. Touch points previstos em arquivos do Plane

Tudo o mais é arquivo novo. Lista mínima para a Fase 0 (marcados ●) e para depois (○):

|     | Arquivo                                                                          | Mudança                                      |
| --- | -------------------------------------------------------------------------------- | -------------------------------------------- |
| ●   | `apps/api/plane/settings/common.py`                                              | `INSTALLED_APPS += ["plane.radar"]`          |
| ●   | `apps/api/plane/urls.py` ou `apps/api/plane/app/urls/__init__.py`                | montar urls RADAR                            |
| ●   | `apps/web/app/routes/extended.ts`                                                | registrar `(radar)`                          |
| ●   | `apps/web/app/(all)/[workspaceSlug]/layout.tsx`                                  | `AppRailVisibilityProvider isEnabled`        |
| ●   | `apps/web/components/navigation/app-rail-hoc.tsx`                                | dock item RADAR                              |
| ●   | `apps/web/hooks/use-workspace-paths.ts`                                          | `isRadarPath` e exclusão de `isProjectsPath` |
| ○   | `packages/types/src/search.ts` + `app/views/search/base.py`                      | busca global e menções                       |
| ○   | `apps/api/plane/db/models/asset.py` + `app/views/asset/v2.py`                    | anexos de objeto                             |
| ○   | `apps/live/src/types/index.ts` + `services/page/handler.ts`                      | colaboração                                  |
| ○   | `apps/web/components/power-k/core/{types,context-detector}.ts`                   | contexto de objeto                           |
| ○   | `apps/web/components/workspace-notifications/sidebar/notification-card/item.tsx` | notificações de objeto                       |
| ○   | `apps/web/hooks/use-favorite-item-details.tsx`, `db/models/recent_visit.py`      | favoritos e recentes                         |

Seis arquivos tocados na Fase 0, todos com mudança de poucas linhas → risco baixo de conflito com upstream.

> **Atualização (Prompt 0.2B):** a app RADAR vazia precisou só dos 4 toques de frontend (+16/−4 linhas); os 2 de backend ficam para quando o RADAR Core existir. Lista real em [RUNTIME_SEAM_VALIDATION §14](./RUNTIME_SEAM_VALIDATION.md#14-plane-touch-points).

---

## 5. Pontos em aberto para o SPIKE_PLAN

1. Nome e localização do app backend (`plane/radar` dentro de `apps/api/plane` vs pacote Python separado).
2. Localização do frontend RADAR: diretórios `apps/web/{components,store,services}/radar` vs pacote `packages/radar-*`.
3. Armazenamento de `PropertyValue`: coluna JSON única vs colunas tipadas (`value_text`, `value_number`, `value_date`, `value_user`, `value_object`) — impacta filtros e índices.
4. Escopo de `ObjectType`/`RelationType`: por workspace (seed dos 5 tipos e 4 relações por workspace) vs globais.
5. Se `Project` do RADAR (tipo de objeto) e `Project` do Plane coexistem na UI: risco de confusão de nomenclatura para o usuário.
6. Validar empiricamente (no stack `docker-compose.radar.yml`) que um workspace sem nenhum projeto Plane navega sem erros até a app RADAR.


## Decisões fechadas em 0.3A (supersedem recomendações anteriores)

- **C1/C10/C12:** RadarBaseModel próprio. Não herda BaseModel, AuditModel, SoftDeleteModel, WorkspaceBaseModel ou ProjectBaseModel. Nenhuma FK RADAR para Project ou Issue. A recomendação anterior de herdar BaseModel em C1 foi invalidada pelo teste histórico de runtime, preservado em RUNTIME_SEAM_VALIDATION §13.
- **C9:** primeiro write passa por CreateObject; toda edição por UpdateObject. Actor human explícito, membership no command, transação e versão; nenhum crum autoritativo. Sem agente, eventos ou Outbox neste passo.
- **C13 / ponto aberto 1:** app `apps/api/plane/radar`, label radar, migration independente 0001; dois toques backend.
- **C15 / ponto aberto 2:** `apps/web/{components,services,store}/radar` com provider no layout (radar), sem referência ao RootStore do Plane. Uma instância por workspace.
- **Ponto aberto 4 (ObjectType):** workspace scoped, cinco tipos is_system; lazy initialization transacional/idempotente pelo command, trava Workspace, sem workspace_seed ou Project. RelationType continua para 0.3B.
- **Ponto aberto 6:** zero Projects confirmado novamente com persistência real, create/edit/refresh/deep link e auditoria no PostgreSQL.
- **C16:** content HTML diretamente no Object; RichTextEditor não colaborativo e sanitização no command.

Continuam abertos: armazenamento de PropertyValue e escopo de RelationType (0.3B), UX de Project como ObjectType versus Projects do Plane. O overhead do shell em C14 permanece; o Core não depende dele.

Métricas cumulativas: 8 arquivos upstream (6 seams de runtime + manifesto web e lockfile para testes); esta etapa adiciona 4 arquivos upstream, +9/−2 linhas. Detalhes e resultados em [CORE_VERTICAL_SLICE_REPORT](../CORE_VERTICAL_SLICE_REPORT.md).
