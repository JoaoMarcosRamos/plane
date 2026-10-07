# RUNTIME_SEAM_VALIDATION — RADAR App vazia sobre o shell do Plane

> Fase 0 · Prompt 0.2B · 2026-10-03 · branch `radar-phase-0-spike` (base `8fa56b19d7`)
> Ambiente: stack isolado `plane-radar` (API :8001, Postgres :5434) + `apps/web` deste worktree em :3000, Chrome.
> Documentos anteriores: [PLANE_MAP.md](./PLANE_MAP.md) · [REUSE_MAP.md](./REUSE_MAP.md) · [DOMAIN_COUPLING.md](./DOMAIN_COUPLING.md)
> Evidências visuais: [`runtime-screenshots/`](./runtime-screenshots/)

---

## 1. Executive Summary

**Veredito: PASS WITH CAVEATS.**

O RADAR roda como uma app paralela a Projects, dentro do shell do Plane, sem passar por `Project → WorkItem`:

- Funciona num workspace com **0 projetos**, sem exceção, sem redirect e sem nenhuma chamada com `projectId`.
- Herda autenticação, workspace, membership, top navigation, App Rail, tema e toasts.
- O código RADAR não referencia nenhum store, hook, param ou contexto de Project/Issue.
- Todos os componentes genéricos testados funcionaram sem adaptação: List, Kanban, RichTextEditor, MemberSelect, DateSelect, Select, Dialog, Drawer, Toast e Tabs.
- **4 arquivos do Plane** foram tocados (+16/−4 linhas).

Ressalvas (detalhes nas seções 11–15):

1. O `RootStore` global (inclusive `IssueRootStore`) é instanciado para qualquer rota, e reage ao router mesmo dentro do RADAR.
2. O workspace wrapper faz 4 requests de projeto ao abrir o RADAR (overhead, não bloqueia).
3. Ligar o App Rail muda também o chrome da app Projects.
4. O Drawer da propel com `side="end"` abre à esquerda (Tailwind 4.1.17 × propel 0.7.3), defeito pré-existente.
5. O `BaseModel` do Plane foi reclassificado como **R4** para o Core.

---

## 2. Route Isolation

**Resultado: PASS. `(radar)` é irmão real de `(projects)` e `(settings)`.**

Decisão A2: **Opção A**, registrar só via `apps/web/app/routes/extended.ts`.

- É o seam que o próprio Plane usa para a edição EE.
- Upstream o arquivo é um array vazio de uma linha, então o risco de conflito é mínimo.
- As rotas ficam num arquivo novo, `app/routes/radar.ts`; o `extended.ts` só faz `[...radarRoutes]`.

`mergeRoutes` funde entradas pelo `file`. Por isso `radar.ts` repete os layouts `./(all)/layout.tsx` → `./(all)/[workspaceSlug]/layout.tsx` e injeta `(radar)/layout.tsx` como filho. Árvore resolvida pelo próprio React Router (`npx react-router routes`):

```
<Route file="./(all)/layout.tsx">
  <Route file="./(all)/[workspaceSlug]/layout.tsx">        ← aparece 1 única vez
    <Route file="./(all)/[workspaceSlug]/(projects)/layout.tsx"> …
    <Route file="./(all)/[workspaceSlug]/(settings)/layout.tsx"> …
    <Route file="./(all)/[workspaceSlug]/(radar)/layout.tsx">
      <Route path=":workspaceSlug/radar"              file=".../(radar)/radar/page.tsx" />
      <Route path=":workspaceSlug/radar/spike"        file=".../(radar)/radar/spike/page.tsx" />
      <Route path=":workspaceSlug/radar/spike/object" file=".../(radar)/radar/spike/object/page.tsx" />
      <Route path=":workspaceSlug/radar/:section"     file=".../(radar)/radar/[section]/page.tsx" />
```

**O que `(radar)` herda** (de `[workspaceSlug]/layout.tsx` e acima):

- `AuthenticationWrapper` e `WorkspaceAuthWrapper` (membership);
- `AppRailVisibilityProvider`, `WorkspaceContentWrapper` (`TopNavigationRoot` + `AppRailRoot`) e `GlobalModals`;
- de `app/layout.tsx` e `provider.tsx`: `StoreProvider`, i18n, `PlaneToastProvider`, SWR, tema;
- de `app/layout.tsx`: o middleware de trailing slash.

**O que `(radar)` não monta:**

- `ProjectsAppPowerKProvider`, e com ele `GlobalShortcutsProvider`, `WorkspaceLevelModals`, `ProjectLevelModals` e `WorkItemLevelModals`;
- `ProjectAppSidebar` e `ExtendedAppSidebar`.

**Dependências indiretas encontradas (A1):**

| Dependência                                                           | Origem                                                         | Efeito no RADAR                                                                                                                                                                                           |
| --------------------------------------------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RootStore` completo (inclui `IssueRootStore`, `ProjectRootStore`)    | `StoreProvider` em `app/provider.tsx`, acima de todas as rotas | Instanciado sempre. O RADAR não lê, mas não há como não montar sem refatorar o root.                                                                                                                      |
| `IssueRootStore` tem `autorun` sobre `router.workspaceSlug`           | `store/issue/root.store.ts:202`                                | Dispara em todo hard load de rota de workspace, inclusive `/radar`. Gera o warning MobX strict-mode (pré-existente, ver §12).                                                                             |
| `TopNavPowerK` usa `useIssueDetail` e `ProjectsAppPowerKCommandsList` | `components/navigation/top-nav-power-k.tsx`                    | A busca inline do top nav abre no RADAR, mas sem lista de comandos. Cmd+K não faz nada no RADAR (em Projects abre o palette). Isolamento correto; o RADAR precisará do próprio provider sobre o registry. |
| `TopNavigationRoot` importa `StarUsOnGitHubLink` de `(projects)/`     | `components/navigation/top-navigation-root.tsx`                | Import cruzado de route group. Inofensivo.                                                                                                                                                                |
| `WorkspaceAuthWrapper` busca dados de projeto                         | `layouts/auth-layout/workspace-wrapper.tsx`                    | Ver §12.                                                                                                                                                                                                  |

---

## 3. Zero Project Workspace

**Resultado: PASS.**

Setup (todo no stack isolado; nenhum projeto criado para "fazer o RADAR funcionar"):

| Workspace        | Como foi criado                                                            | Projetos vivos                    | `radar-tester` |
| ---------------- | -------------------------------------------------------------------------- | --------------------------------- | -------------- |
| `radar-projects` | UI (onboarding)                                                            | 1 (demo seed)                     | membro (admin) |
| `radar-zero`     | UI, depois o projeto do seed foi apagado via `DELETE /projects/:id/` (204) | **0** (`/projects/` retorna `[]`) | membro (admin) |
| `radar-other`    | ORM, dono `radar-outsider`                                                 | 0                                 | **não membro** |

Observação: todo workspace criado pela API dispara `workspace_seed.delay()` e ganha um projeto demo. Workspace "nascido sem projeto" só existe via ORM ou apagando o seed.

Em `/radar-zero/radar/` (hard load e refresh):

- nenhuma exceção da app RADAR;
- nenhum redirect para criação de projeto;
- nenhum contexto de projeto requerido;
- nenhuma request com `projectId` e nenhuma request de issue.

Todas as 14 requests retornaram 200 (§12). Screenshot: `runtime-screenshots/01-radar-home-zero-projects.jpg`.

---

## 4. App Rail

**Resultado: PASS.**

- Ligado com `isEnabled` em `AppRailVisibilityProvider` (1 prop em `[workspaceSlug]/layout.tsx`).
- Dock items: **Projects** (`/:slug/`) e **RADAR** (`/:slug/radar/`, ícone `RadarIcon` do lucide-react, já dependência do web), mais Settings.
- O destaque do item ativo funciona nos dois sentidos, porque `isProjectsPath` agora exclui `isRadarPath` (`hooks/use-workspace-paths.ts`, mesmo padrão já usado para `wiki` e `pi-chat`).
- Navegação Projects → RADAR → Projects é client-side: um marcador em `window` sobreviveu às duas trocas. Sem erro no console e sem estado corrompido; a sidebar de Projects volta com o projeto listado.
- **Efeito colateral:** o rail aparece também na app Projects, onde antes não existia. É mudança visível de UX no upstream, aceitável para o fork.

---

## 5. Sidebar

**Resultado: PASS.**

`components/radar/sidebar.tsx` (`RadarAppSidebar`) reusa:

- `ResizableSidebar`, `SidebarWrapper` (título "RADAR") e `SidebarNavItem`;
- o estado de collapse/peek/largura do `useAppTheme`, compartilhado com Projects.

Itens: Today, Objects, Decisions, Risks → `/:slug/radar/:section` (placeholders); separador; Spike Components → `/:slug/radar/spike`. O rodapé herdado mostra o badge de edição (`WorkspaceEditionBadge`).

A sidebar não lê nenhum store de projeto. O botão "customize navigation" do `SidebarWrapper` só aparece quando `title === "Projects"`, então não aparece no RADAR (comportamento correto, sem tocar no arquivo).

---

## 6. Generic List

**Resultado: PASS. É genérico de verdade.** Screenshot `02-spike-generic-list.jpg`.

`BaseListLayout` (`components/base-layouts/list`) usado sem alteração, com 6 objetos fake agrupados por tipo:

| Comportamento               | Resultado                                                                        |
| --------------------------- | -------------------------------------------------------------------------------- |
| Renderização / agrupamento  | OK, 5 grupos (Objective…Risk) com contagem                                       |
| Collapse em modo "external" | OK, `list.onToggleGroup(objective)` registrado no log                            |
| `renderItem`                | OK, recebe `{id, …}`; o RADAR busca o objeto pelo próprio mapa (sem cast)        |
| Seleção                     | OK, mas **não é feature do layout**: implementada no `renderItem` (estado local) |
| Grupos vazios               | Ocultos por padrão (`showEmptyGroups=false`)                                     |

O tipo `IBaseLayoutsBaseItem = {id: string; [key: string]: unknown}` não conhece nada de issue.

---

## 7. Generic Kanban

**Resultado: PASS.** Screenshot `03-spike-generic-kanban.jpg`.

`BaseKanbanLayout` usado sem alteração, agrupado por status fake (Planned / Active / Done):

| Comportamento                    | Resultado                                                                                                                                    |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Renderização / colunas           | OK                                                                                                                                           |
| Drag & drop entre colunas        | OK, `kanban.onDrop(action-negotiate-licenses, null, planned → active)`; o card mudou de coluna; a coluna vazia mostra o empty state do Plane |
| Dependências extras              | Nenhuma (pragmatic-dnd já presente; sem provider)                                                                                            |
| Seleção compartilhada com a List | OK (estado do caller)                                                                                                                        |

Limites do componente:

- O drop só funciona **entre grupos**; `destinationId` é sempre `null`, então não há reordenação dentro da coluna.
- Não há seleção nem multi-seleção embutidas.
- `loadMoreItems` existe na assinatura, mas o grupo o ignora (`_loadMoreItems`).

---

## 8. Rich Text Editor

**Resultado: PASS.**

Wrapper `components/editor/rich-text` (`RichTextEditor`), não colaborativo, montado com `workspaceSlug` + `workspaceId` e **sem `projectId`**. O conteúdo fica em estado local.

| Verificação                       | Resultado                                                                                                                                                                        |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Carrega                           | OK                                                                                                                                                                               |
| Bubble toolbar (seleção)          | OK: Text, Link, Color, **B**/I/U/S, alinhamento; Bold aplicado                                                                                                                   |
| Slash commands                    | OK, lista de blocos; "Bulleted list" inserido                                                                                                                                    |
| Menção `@`                        | OK, `GET /api/workspaces/radar-zero/entity-search/?count=5&query_type=user_mention&query=Jo`, **sem `project_id`**, resolve via `WorkspaceMember`; chip `@radar-tester` inserido |
| `onChange`                        | OK, HTML atualizado (637 chars)                                                                                                                                                  |
| Upload                            | Desligado: `disabledExtensions={["image"]}`; `uploadFile`/`duplicateFile` rejeitam                                                                                               |
| Collaborative / Yjs / `apps/live` | Não usado                                                                                                                                                                        |

Também reaproveitado na mock Object Page (bloco "Context").

---

## 9. Member Picker

**Resultado: PASS.**

`components/dropdowns/member/member-select.tsx` sem `projectId` oferece o **roster do workspace**: `radar-tester (You)` + linha "clear".

- Em `radar-zero` não existe nenhum `ProjectMember`, então a origem só pode ser o `WorkspaceMember`.
- Nenhuma request ao abrir: usa `members/` já carregado pelo wrapper.
- O bot do seed não aparece.

Seleção registrada (`owner(<uuid>)`).

---

## 10. Date Picker / Modals / Drawers

| Componente  | Fonte                                             | Resultado                                                                                                                                                                                                                                                                                                                            |
| ----------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Date picker | `@plane/blocks/property-select` `DateSelect`      | PASS: calendário out/2026, seleção → `date(2026-10-13)`                                                                                                                                                                                                                                                                              |
| Select      | `@plane/blocks/select`                            | PASS: tipo trocado para "Risk" dentro do Dialog                                                                                                                                                                                                                                                                                      |
| Dialog      | propel `Dialog*`                                  | PASS: "Create Object" abre, foco no título, submit fecha e dispara toast (`04-spike-create-object-dialog.jpg`)                                                                                                                                                                                                                       |
| Drawer      | propel `Drawer` + `DrawerPanel variant="overlay"` | PASS com defeito visual: abre/fecha (duplo clique, Esc) e mostra dados (`05-spike-drawer.jpg`). Com `side="end"` abre **à esquerda**: a classe `inset-e-2` da propel não é gerada pelo Tailwind **4.1.17** pinado no repo (computado `left: 0`, nenhuma regra CSS). Pré-existente; nenhum consumidor de `Drawer` em `apps/web` hoje. |
| Toast       | `@plane/blocks/toast` `setToast`                  | PASS: info, success e error                                                                                                                                                                                                                                                                                                          |
| Tabs        | propel `Tabs`/`Tab`                               | PASS: alterna List ↔ Kanban mantendo estado                                                                                                                                                                                                                                                                                          |

---

## 11. Store Isolation

**Decisão para esta etapa:** nenhum store RADAR. Tudo é estado local de componente, suficiente para mocks.

O que o código RADAR usa (verificado por grep, 0 ocorrências de `useProject|useIssue|projectId|issueId|workItem|power-k` em `components/radar`, `(radar)/` e `routes/radar.ts`):

| Hook/store                        | Usado por                          | Natureza      |
| --------------------------------- | ---------------------------------- | ------------- |
| `useAppTheme`                     | sidebar (collapse/peek)            | shell         |
| `useWorkspace().currentWorkspace` | home, notes editor (`workspaceId`) | shell         |
| `useUser().data`                  | home, mock object (owner default)  | shell         |
| `useMember` (indireto)            | `MemberSelect`, `RichTextEditor`   | compartilhado |
| `WorkspaceService.searchEntity`   | menções no editor                  | compartilhado |

**`RadarRootStore`, viabilidade:** confirmada. As dependências reais se resumem a user, workspace, members e theme. Proposta para a Fase 1:

- MobX store próprio, criado em `(radar)/layout.tsx` e exposto por um React context `RadarStoreProvider`;
- recebe por construtor só `rootStore.user`, `rootStore.workspaceRoot` e `rootStore.memberRoot`;
- não é registrado em `store/root.store.ts`, o que mantém zero touch point.

O que **não** dá para evitar sem refatorar o Plane: a instanciação do `RootStore` inteiro (com `IssueRootStore`) pelo `StoreProvider` e o `autorun` do `IssueRootStore` sobre o router. Custo: memória e um warning; não há acoplamento funcional.

---

## 12. Network Overhead

### D1. Hard load de `/radar-zero/radar/` (14 requests à API, todas 200)

| #   | Request                                                 | Classe                                                                               |
| --- | ------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 1   | `GET /api/instances/`                                   | REQUIRED                                                                             |
| 2   | `GET /api/users/me/`                                    | REQUIRED                                                                             |
| 3   | `GET /api/users/me/profile/`                            | REQUIRED                                                                             |
| 4   | `GET /api/users/me/settings/`                           | REQUIRED                                                                             |
| 5   | `GET /api/users/me/workspaces/`                         | REQUIRED                                                                             |
| 6   | `GET /api/workspaces/:slug/workspace-members/me/`       | REQUIRED (membership)                                                                |
| 7   | `GET /api/workspaces/:slug/members/`                    | SHARED BUT ACCEPTABLE (member picker, menções)                                       |
| 8   | `GET /api/workspaces/:slug/users/notifications/unread/` | SHARED BUT ACCEPTABLE (inbox do top nav)                                             |
| 9   | `GET /api/workspaces/:slug/user-favorites/?all=true`    | SHARED BUT ACCEPTABLE (modelo genérico por `entity_type`)                            |
| 10  | `GET /api/workspaces/:slug/sidebar-preferences/`        | SHARED BUT ACCEPTABLE (preferências da sidebar de Projects; inútil no RADAR, barato) |
| 11  | `GET /api/users/me/workspaces/:slug/project-roles/`     | PROJECT-SPECIFIC OVERHEAD                                                            |
| 12  | `GET /api/workspaces/:slug/projects/`                   | PROJECT-SPECIFIC OVERHEAD (retorna `[]`)                                             |
| 13  | `GET /api/workspaces/:slug/states/`                     | PROJECT-SPECIFIC OVERHEAD                                                            |
| 14  | `GET /api/workspaces/:slug/user-properties/`            | PROJECT-SPECIFIC OVERHEAD (navigation prefs de projeto)                              |

**UNEXPECTED / PROBLEMATIC:** nenhuma. A app RADAR em si não fez nenhuma request no load; as 14 vêm do shell. Durante o uso do playground a única request extra foi a `entity-search` da menção.

Comparação: o hard load da home de Projects (`/radar-zero/`) faz as mesmas 14, mais `home-preferences`, `quick-links`, `recent-visits` e `stickies`.

Não-membro (`/radar-other/radar/`): `states/`, `sidebar-preferences/` e `user-properties/` disparam antes da checagem de membership (o SWR só depende do slug) e recebem **403**. A API protege corretamente; o disparo é pré-existente.

### D2. Console

| Mensagem                                                                                     | Onde                                                 | Classificação                                                        |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------- |
| `Hydration failed…` em `HydrateFallback`                                                     | Todo hard load (RADAR, home de Projects, work items) | Pré-existente do shell, não RADAR                                    |
| `[MobX] … IssueRootStore@31.workspaceSlug` / `BaseWorkspaceRootStore@9.loader` (strict-mode) | Todo hard load de rota de workspace                  | Pré-existente; mostra o `autorun` do `IssueRootStore` ativo no RADAR |
| `<button> cannot be a descendant of <button>` em `ProjectAppSidebar`                         | Só em Projects                                       | Pré-existente, ausente no RADAR                                      |
| `Auto scrolling has been attached to an element that appears not to be scrollable`           | Home de Projects                                     | Pré-existente, ausente no RADAR                                      |
| Warnings / erros durante toda a interação no `/radar/spike`                                  | —                                                    | **Zero** (captura confirmada ativa com um `console.warn` de sonda)   |
| Failed requests, missing context, provider errors                                            | —                                                    | **Nenhum** no RADAR                                                  |

Dev-only: o primeiro clique para `/radar/spike` não navegou de imediato. O React Router só confirma a navegação depois que o módulo da rota carrega, e o Vite estava compilando a frio o editor (Tiptap). Depois de aquecido, todas as navegações foram imediatas.

### D3. Reuso de componentes em `/radar/spike` e na mock Object Page

| Componente                                             | Source path                                                                                          | Sem alteração? | Adapter?                                                              | Dep. Project?                       | Dep. Issue?          |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------- | ----------------------------------- | -------------------- |
| `BaseListLayout`                                       | `apps/web/components/base-layouts/list`                                                              | Sim            | Não (só `renderItem`)                                                 | Não                                 | Não                  |
| `BaseKanbanLayout`                                     | `apps/web/components/base-layouts/kanban`                                                            | Sim            | Não                                                                   | Não                                 | Não                  |
| `RichTextEditor`                                       | `apps/web/components/editor/rich-text`                                                               | Sim            | Wrapper fino `RadarSpikeNotesEditor` (workspace, menções, upload off) | Não (`projectId` opcional)          | Não¹                 |
| `MemberSelect`                                         | `apps/web/components/dropdowns/member/member-select.tsx`                                             | Sim            | Não                                                                   | Não (omitido = roster do workspace) | Não                  |
| `DateSelect`                                           | `packages/blocks/src/property-select/date-select.tsx`                                                | Sim            | Não                                                                   | Não                                 | Não                  |
| `Select`                                               | `packages/blocks/src/select`                                                                         | Sim            | Não                                                                   | Não                                 | Não                  |
| `Dialog*`                                              | `@makeplane/propel/components/dialog`                                                                | Sim            | Não                                                                   | Não                                 | Não                  |
| `Drawer*`/`DrawerPanel`                                | `@makeplane/propel/components/drawer`                                                                | Sim            | Não                                                                   | Não                                 | Não (bug de CSS §10) |
| `setToast`                                             | `packages/blocks/src/toast`                                                                          | Sim            | Não                                                                   | Não                                 | Não                  |
| `Tabs`/`Tab`/`TabsList`                                | `@makeplane/propel/components/tabs`                                                                  | Sim            | Não                                                                   | Não                                 | Não                  |
| `Badge`, `Button`, `InputField`                        | `@makeplane/propel/components/*`                                                                     | Sim            | Não                                                                   | Não                                 | Não                  |
| `AppHeader`, `ContentWrapper`, `PageHead`              | `apps/web/components/core/*`                                                                         | Sim            | Não                                                                   | Não                                 | Não                  |
| `Header`, `Breadcrumbs`, `BreadcrumbLink`              | `@plane/blocks/layout`, `@plane/blocks/breadcrumb`, `apps/web/components/common/breadcrumb-link.tsx` | Sim            | Não                                                                   | Não                                 | Não                  |
| `ResizableSidebar`, `SidebarWrapper`, `SidebarNavItem` | `apps/web/components/sidebar/*`                                                                      | Sim            | Não                                                                   | Não                                 | Não                  |

¹ O wrapper do editor chama `useEditorFlagging` e `useParseEditorContent` com `projectId` indefinido; ambos aceitam isso. A extensão `work-item-embed` continua registrada no pacote, mas fica inerte.

---

## 13. Updated BaseModel Assessment

Verificação em runtime: `BaseModel.save()` foi executado num shell Django do container `plane-radar-api-1`, com o write no banco mockado (nada persistido):

```
update without request user -> created_by_id: None | was: 02b609db-…
update with created_by_id=X  -> created_by_id overwritten: True | updated_by_id: None
```

Ou seja:

1. Um `save()` fora de request (Celery, worker, runtime de agente) **apaga o `created_by` de um registro existente**.
2. O único hook de ator explícito (`created_by_id=`) **sobrescreve o criador original** num update e deixa `updated_by` nulo.

Isso contradiz diretamente "Provenance é obrigatório".

| Elemento                                             | O que faz                                            | Classe          | Justificativa                                                                                             |
| ---------------------------------------------------- | ---------------------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------- |
| `TimeAuditModel`                                     | `created_at` / `updated_at`                          | **R1**          | Puro, sem semântica escondida                                                                             |
| PK UUID                                              | `UUIDField(default=uuid4)`                           | **R1** (padrão) | Trivial; redeclarar no modelo RADAR                                                                       |
| `ChangeTrackerMixin`                                 | Detecta campos alterados                             | **R1**          | Útil para montar payload de Domain Events                                                                 |
| `UserAuditModel` (só os campos)                      | FKs `created_by` / `updated_by`                      | **R2**          | Os campos servem se preenchidos explicitamente pelo Command Layer                                         |
| `BaseModel.save()`                                   | Ator implícito via `crum.get_current_user()`         | **R4**          | Comprovado acima: apaga/sobrescreve autoria fora de request                                               |
| `SoftDeleteModel.delete()`                           | `deleted_at` + `soft_delete_related_objects.delay()` | **R4**          | Cascata Celery fora da transação, sem evento, via introspecção de FKs reversas → grafo/backlinks divergem |
| `SoftDeletionManager` / `QuerySet.delete(soft=True)` | Filtra deletados / `update(deleted_at=…)` em massa   | **R3**          | Padrão ok, mas a semântica difere do `delete()` de instância (sem cascata). Reimplementar com regra única |
| `AuditModel` (composto)                              | Time + User + SoftDelete                             | **R4**          | Arrasta `SoftDeleteModel`                                                                                 |
| `BaseModel` (composto)                               | UUID + AuditModel + save implícito                   | **R4**          | Arrasta tudo acima                                                                                        |

**Recomendação (não implementada):** um futuro `RadarBaseModel` herda só de `TimeAuditModel` e:

- declara a própria PK UUID;
- declara `created_by` / `updated_by` como FKs preenchidas **apenas** pelo Command Layer, recebendo um `Actor` explícito; nunca `crum`;
- tem `deleted_at` próprio com manager que filtra;
- tem `delete()` de instância bloqueado fora do Command Layer, para que exclusão seja um command transacional que emite evento;
- usa `ChangeTrackerMixin` para o payload de eventos.

Isso **substitui** a linha "BaseModel / AuditModel → R1" do REUSE_MAP.

---

## 14. Plane Touch Points

### Arquivos do Plane modificados (4 arquivos, +16 / −4)

| Arquivo                                           | Por quê                                       | Mudança                                                       | Risco de merge                                                | Isolamento futuro                                                                                   |
| ------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `apps/web/app/routes/extended.ts`                 | Registrar rotas RADAR pelo seam oficial       | `import { radarRoutes }` + `[...radarRoutes]` (2 linhas)      | **Muito baixo**: array vazio upstream                         | Já isolado; o resto vive em `routes/radar.ts`                                                       |
| `apps/web/app/(all)/[workspaceSlug]/layout.tsx`   | Ligar o App Rail                              | `<AppRailVisibilityProvider isEnabled>` (1 linha)             | **Baixo**: layout curto, pouco editado                        | Upstream poderia tornar `isEnabled` configurável por env/feature flag                               |
| `apps/web/components/navigation/app-rail-hoc.tsx` | Dock item RADAR                               | import `RadarIcon` + item no array + `isRadarPath` (9 linhas) | **Baixo/médio**: é onde o upstream adicionaria apps (Wiki/AI) | Extrair `dockItems` para uma lista estendível (`extended-dock-items.ts`), como já existe para rotas |
| `apps/web/hooks/use-workspace-paths.ts`           | `isRadarPath` e excluí-lo de `isProjectsPath` | 4 linhas, mesmo padrão de `isWikiPath`/`isAiPath`             | **Baixo**                                                     | Mesma extração acima resolveria                                                                     |

Nenhum arquivo de backend, model, migration, store raiz, Issue, Project, IssueRelation, IssueActivity ou IssueType foi tocado.

Comparado à previsão de DOMAIN_COUPLING §4: os 2 toques de backend (`INSTALLED_APPS`, urls) não foram necessários nesta etapa. Os 4 de frontend se confirmaram.

### Arquivos novos (todos do RADAR)

```
apps/web/app/routes/radar.ts
apps/web/app/(all)/[workspaceSlug]/(radar)/layout.tsx
apps/web/app/(all)/[workspaceSlug]/(radar)/radar/page.tsx
apps/web/app/(all)/[workspaceSlug]/(radar)/radar/[section]/page.tsx
apps/web/app/(all)/[workspaceSlug]/(radar)/radar/spike/page.tsx
apps/web/app/(all)/[workspaceSlug]/(radar)/radar/spike/object/page.tsx
apps/web/components/radar/header.tsx
apps/web/components/radar/home.tsx
apps/web/components/radar/sections.ts
apps/web/components/radar/sidebar.tsx
apps/web/components/radar/spike/generic-layouts.tsx
apps/web/components/radar/spike/mock-data.ts
apps/web/components/radar/spike/mock-object-page.tsx
apps/web/components/radar/spike/notes-editor.tsx
apps/web/components/radar/spike/overlays.tsx
apps/web/components/radar/spike/playground.tsx
apps/web/components/radar/spike/section.tsx
docs/radar/phase-0/RUNTIME_SEAM_VALIDATION.md
docs/radar/phase-0/runtime-screenshots/*.jpg (8)
```

Fora do git: `.secrets/radar-dev-login.md` (gitignored) com a conta de teste `radar-tester@plane.local`, que existe só no stack isolado.

---

## 15. Merge Risk

**Baixo.**

- 3 dos 4 toques são de 1 a 4 linhas em arquivos pequenos e estáveis.
- O único com risco real de conflito é `app-rail-hoc.tsx`: é o lugar natural para o upstream registrar novas apps. Um conflito ali é trivial de resolver (lista de objetos).
- Todo o resto é arquivo novo em diretórios exclusivos (`(radar)/`, `components/radar/`, `routes/radar.ts`).

Para reduzir ainda mais: transformar `dockItems` e os path flags num seam estendível (o mesmo padrão `extended.ts`). Assim o fork passa a ter 3 toques de 1–2 linhas.

---

## 16. Architecture Recommendation

**Prosseguir para `ObjectType`, `Object`, `PropertyDefinition`, `PropertyValue`, `RelationType` e `Relation`**, com estas condições de entrada:

1. **Backend:** app Django próprio (ex.: `plane/radar`) com migrations próprias. Modelos sobre um `RadarBaseModel` conforme §13, **sem** herdar `BaseModel`, `AuditModel` ou `SoftDeleteModel`. Isso adiciona os 2 toques de backend previstos (`INSTALLED_APPS`, urls).
2. **Escrita só por commands** com `Actor` explícito desde o primeiro model, mesmo antes de outbox/eventos. Views DRF finas, permissão `allow_permission(level="WORKSPACE")`.
3. **Frontend:** continuar em `(radar)/` + `components/radar/`, e introduzir `RadarRootStore` por context no `(radar)/layout.tsx` quando houver dados reais (§11).
4. **List/Kanban genéricos** como base das views de objetos. Seleção, reordenação intra-grupo e paginação são do RADAR (o layout não oferece).
5. **Não usar Drawer `side="end"`** até alinhar Tailwind ↔ propel, ou usar `variant="inline"` / `contained`.
6. **Power-K para o RADAR** (provider próprio sobre `PowerKCommandRegistry`) só quando houver comandos reais.

---

## Testes executados (PARTE F)

| #   | Teste                                    | Resultado | Evidência                                                                                                                                |
| --- | ---------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Workspace com projetos: Projects e RADAR | PASS      | `radar-projects`: home e lista de work items de Projects OK (`07-projects-app-still-works.jpg`); RADAR OK                                |
| 2   | Workspace com 0 projetos: RADAR          | PASS      | `radar-zero` (`01-radar-home-zero-projects.jpg`)                                                                                         |
| 3   | Navegação Projects → RADAR → Projects    | PASS      | Client-side (marcador `window` preservado), sem erro, rail/sidebars corretos                                                             |
| 4   | Refresh direto em `/:slug/radar`         | PASS      | Hard load / reload, só o hydration warning pré-existente                                                                                 |
| 5   | Deep link `/:slug/radar/spike/object`    | PASS      | `06-mock-object-page-deep-link.jpg`                                                                                                      |
| 6   | Não autenticado                          | PASS      | Redirect para `/?next_path=/radar-projects/radar/` (tela de login)                                                                       |
| 7   | Fora do workspace                        | PASS      | `/radar-other/radar/` → "Workspace not found"; nenhum componente RADAR montado; API responde 403 (`08-non-member-workspace-blocked.jpg`) |

Checagens estáticas (`apps/web`):

- `check:types` (`react-router typegen && tsc --noEmit`): **OK** (exit 0).
- `oxlint --deny-warnings` nos arquivos RADAR e tocados: 0 warnings, 0 erros.
- `oxfmt --check`: OK.

**Testes unitários:** `apps/web` não tem framework de teste (sem vitest/jest, sem script `test`, zero arquivos `*.test.*`). Não foi adicionado nesta etapa, porque isso criaria um touch point em `package.json`/lockfile. A validação desta etapa é runtime. Ao começar o RADAR Core, os testes do backend usam o pytest existente (`docker-compose-test.yml`), e o frontend do RADAR precisará de vitest (o `packages/blocks` já tem setup reaproveitável).


## Referência posterior — Prompt 0.3A

O vertical slice persistido e a nova sequência Foundation → Semantic Model estão em [CORE_VERTICAL_SLICE_REPORT.md](../CORE_VERTICAL_SLICE_REPORT.md), [SPIKE_PLAN.md](../SPIKE_PLAN.md) e [ARCHITECTURE.md](../ARCHITECTURE.md). Esta referência não altera os resultados históricos deste documento.
