# PLANE_MAP — Mapa técnico do Plane CE para o RADAR

> Fase 0 · Prompt 0.1 · 2026-10-03 · branch `radar-phase-0-spike` (base `c7a5afee6a`, Plane CE v1.4.x)
> Análise somente leitura. Nenhum código foi alterado.
> Documentos irmãos: [REUSE_MAP.md](./REUSE_MAP.md) · [DOMAIN_COUPLING.md](./DOMAIN_COUPLING.md)

Todos os caminhos são relativos à raiz do repositório.

---

## 1. Stack e topologia

| Unidade                    | Caminho                                                  | Tecnologia / papel                                                                                                                                         |
| -------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web app                    | `apps/web`                                               | React 19.2 + React Router 8.3 (framework mode, Vite 8), MobX 6.12, SWR 2.4. Imports `next/navigation` são shim de compatibilidade (`apps/web/app/compat`). |
| Admin                      | `apps/admin`                                             | Painel da instância (god mode).                                                                                                                            |
| Space                      | `apps/space`                                             | Boards públicos (deploy de projeto). Irrelevante para o RADAR.                                                                                             |
| Live                       | `apps/live`                                              | Servidor Hocuspocus (Yjs) para edição colaborativa em tempo real.                                                                                          |
| API                        | `apps/api`                                               | Django 5.2 + DRF 3.17, Celery 5.5 (`plane/bgtasks`), Postgres, Redis, MinIO/S3.                                                                            |
| Proxy                      | `apps/proxy`                                             | Caddy.                                                                                                                                                     |
| Design system              | `@makeplane/propel` **0.7.3** (npm, externo ao monorepo) | Primitivos: dialog, drawer, calendar, combobox, table, tabs, toast, menu, popover, etc.                                                                    |
| Blocks                     | `packages/blocks`                                        | Componentes compostos sobre propel (property-select, select, dialog, layout, charts, empty-state…). Só props, sem store.                                   |
| Editor                     | `packages/editor`                                        | Tiptap. Exporta `RichTextEditor`, `LiteTextEditor`, `DocumentEditor`, `CollaborativeDocumentEditor`.                                                       |
| Tipos / utils / constantes | `packages/types`, `packages/utils`, `packages/constants` | Compartilhados web/admin/space/live.                                                                                                                       |
| Estado compartilhado       | `packages/shared-state`                                  | MobX: user, workspace, rich-filters, work-item-filters.                                                                                                    |
| Serviços HTTP              | `packages/services` + `apps/web/services`                | Clientes axios (há duplicação parcial entre os dois).                                                                                                      |
| i18n                       | `packages/i18n`                                          | 21 locales, inclui `pt-BR`.                                                                                                                                |

### Duas pilhas de API no backend

| Montagem      | App Django             | Autenticação                     | Consumidor                     |
| ------------- | ---------------------- | -------------------------------- | ------------------------------ |
| `api/`        | `plane/app`            | Sessão (cookie)                  | Web app                        |
| `api/v1/`     | `plane/api`            | API key (`APIKeyAuthentication`) | Integrações externas           |
| `api/public/` | `plane/space`          | Anônima                          | Boards públicos                |
| `auth/`       | `plane/authentication` | —                                | Login/sign-up/OAuth/magic link |

`plane/app` e `plane/api` têm **views próprias com lógica duplicada** (ex.: `issue_activity.delay` aparece 14× em `plane/api/views/issue.py` e também em `plane/app/views/issue/*`). Não há camada de serviço/command entre a view e o ORM. Ver DOMAIN_COUPLING §C9.

---

## 2. Modelo de domínio do Plane

```
Instance
└── Workspace ──────────────── WorkspaceMember (role 20/15/5)
    ├── Project ─────────────── ProjectMember (role por projeto)
    │   ├── Issue (= WorkItem) ── IssueActivity, IssueComment, IssueRelation,
    │   │                         IssueAssignee, IssueLabel, IssueLink, IssueMention,
    │   │                         IssueSubscriber, IssueReaction, IssueVersion…
    │   ├── State, Estimate, Cycle, Module, IssueView, Intake
    │   └── ProjectPage ──┐
    ├── Page ◄────────────┘ (workspace-level, M2M com Project)
    ├── Label        (project nullable)
    ├── Sticky       (workspace-level puro)
    ├── IssueType    (workspace-level; is_epic; SEM propriedades custom no CE)
    ├── UserFavorite / UserRecentVisit   (entity_type + entity_identifier)
    ├── Notification (project nullable; entity_name + entity_identifier + data JSON)
    ├── Description / DescriptionVersion (rich text versionado)
    └── FileAsset    (FKs opcionais por entidade + entity_type/entity_identifier)
```

### Classes base (`apps/api/plane/db`)

| Classe               | Arquivo                   | O que impõe                                                                                                                                                |
| -------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AuditModel`         | `mixins.py`               | `created_at/updated_at`, `created_by/updated_by` (via `crum.get_current_user`), soft delete (`deleted_at`, `objects` filtra deletados, `all_objects` não). |
| `BaseModel`          | `models/base.py`          | PK UUID + `AuditModel`.                                                                                                                                    |
| `WorkspaceBaseModel` | `models/workspace.py:185` | FK `workspace` obrigatória, FK `project` **opcional**.                                                                                                     |
| `ProjectBaseModel`   | `models/project.py:180`   | FK `project` **obrigatória** + `workspace`. Base de Issue, Cycle, Module, State, IssueComment, IssueActivity, IssueRelation…                               |
| `ChangeTrackerMixin` | `mixins.py`               | Detecção de campos alterados (usado por Issue e IssueComment).                                                                                             |

Todos os modelos vivem no app único `plane.db` (122 migrations até `0122_…`). Não há modelos em outros apps Django.

---

## 3. Shell da aplicação web (rotas e layouts)

Definição: `apps/web/app/routes.ts` = `mergeRoutes(coreRoutes, extendedRoutes)` envolvido em `app/layout.tsx`.

- `apps/web/app/routes/core.ts` — todas as rotas do CE.
- `apps/web/app/routes/extended.ts` — **array vazio**; ponto de extensão oficial (usado pela edição EE). `mergeRoutes` (`routes/helper.ts`) faz deep-merge por arquivo de layout.

```
app/layout.tsx
└── (all)/layout.tsx
    ├── [workspaceSlug]/layout.tsx          ← AuthenticationWrapper → WorkspaceAuthWrapper
    │                                          → AppRailVisibilityProvider → WorkspaceContentWrapper
    │                                          (TopNavigationRoot + AppRailRoot) + GlobalModals
    │   ├── (projects)/layout.tsx           ← "app" Projects: ProjectsAppPowerKProvider + ProjectAppSidebar
    │   │   ├── :slug                        (home do workspace)
    │   │   ├── :slug/notifications, /drafts, /stickies, /profile/:id, /workspace-views, /analytics/:tab
    │   │   ├── :slug/browse/:workItem       (detalhe de issue por identificador)
    │   │   └── :slug/projects/:projectId/{issues,cycles,modules,views,pages,intake,archives}
    │   └── (settings)/layout.tsx           ← settings de workspace e de projeto
    ├── settings/profile/:tab
    └── sign-up, accounts/*, onboarding, invitations, create-workspace
```

### Modelo "multi-app" latente

O shell já foi desenhado para várias apps lado a lado no workspace:

- `lib/app-rail/provider.tsx` — `AppRailVisibilityProvider` com `isEnabled = false` por padrão; o layout do workspace não passa `isEnabled`, então **o App Rail está desligado no CE**.
- `components/navigation/app-rail-hoc.tsx` — `withDockItems` declara um único dock item: "Projects".
- `hooks/use-workspace-paths.ts` — já reconhece `/{slug}/wiki` e `/{slug}/pi-chat` (apps da edição EE) e define `isProjectsPath` como "tudo que não é wiki/ai/settings".
- `(projects)/extended-sidebar*.tsx`, `components/workspace/sidebar/extended-sidebar-item.tsx`, `components/common/extended-app-header.tsx` — seams de extensão.

**Implicação:** uma app RADAR pode ser um route group irmão `(radar)/` sob `[workspaceSlug]/layout.tsx`, com sidebar própria e dock item próprio, herdando auth, workspace, top nav, modais globais e tema sem passar por `(projects)`.

---

## 4. Mapa por capacidade

Legenda da última coluna: acoplamento a Project/WorkItem — **N**enhum · **L**eve (parâmetro opcional / tipo nomeado "Issue") · **F**orte (lógica de domínio Issue embutida).

| #   | Capacidade              | Frontend (`apps/web` salvo indicação)                                                                                                                                                                                                                     | Pacotes                                                                                                                                                                                        | Backend (`apps/api/plane`)                                                                                                                                                                         | Acopl.                               |
| --- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| 1   | Authentication          | `app/(home)`, `app/(all)/sign-up`, `app/(all)/accounts/*`, `components/auth-screens`, `lib/wrappers/authentication-wrapper.tsx`                                                                                                                           | `@plane/blocks/auth`, `packages/constants/src/auth`                                                                                                                                            | `authentication/` (montado em `auth/`), `db/models/user.py`, `db/models/session.py`, `db/models/api.py` (APIToken)                                                                                 | N                                    |
| 2   | Workspace               | `app/(all)/[workspaceSlug]/layout.tsx`, `layouts/auth-layout/workspace-wrapper.tsx`, `store/workspace`, `components/workspace/*`, `app/(all)/create-workspace`                                                                                            | `shared-state/src/store/workspace.store.ts`                                                                                                                                                    | `db/models/workspace.py`, `app/views/workspace/*`, `app/permissions/workspace.py`                                                                                                                  | L¹                                   |
| 3   | Navigation              | `components/navigation/*` (top-navigation-root, app-rail-root/hoc, tab-navigation-\*), `lib/app-rail`, `hooks/use-workspace-paths.ts`, `hooks/use-navigation-preferences.ts`                                                                              | —                                                                                                                                                                                              | `WorkspaceUserPreference` (`db/models/workspace.py`)                                                                                                                                               | L                                    |
| 4   | Sidebar                 | `components/sidebar/*` (sidebar-wrapper, resizable-sidebar, sidebar-item, toggle), `components/workspace/sidebar/*` (projects-list, favorites, menu items, user/workspace menu), `app/(all)/[workspaceSlug]/(projects)/{_sidebar,sidebar,extended-*}.tsx` | —                                                                                                                                                                                              | —                                                                                                                                                                                                  | L²                                   |
| 5   | Design System           | `apps/web/styles`, `components/ui`, `components/icons`, `components/empty-state`                                                                                                                                                                          | `@makeplane/propel` (npm), `packages/blocks`, `packages/tailwind-config`                                                                                                                       | —                                                                                                                                                                                                  | N                                    |
| 6   | Rich Text Editor        | `components/editor/{rich-text,lite-text,document,sticky-editor,embeds}`, `hooks/editor/*`                                                                                                                                                                 | `packages/editor` (Tiptap)                                                                                                                                                                     | `Description`, `DescriptionVersion`, campos `description_{json,html,binary,stripped}`; colaboração em `apps/live`                                                                                  | L³                                   |
| 7   | Comments                | `components/comments/*` (UI dirigida por `TCommentsOperations`), `components/issues/issue-detail/issue-activity/*`, `store/issue/issue-details/{comment,comment_reaction}.store.ts`                                                                       | `types/src/issues/activity/issue_comment.ts`                                                                                                                                                   | `IssueComment`, `CommentReaction` (`db/models/issue.py`), `app/views/issue/comment.py`                                                                                                             | F (backend) / L (UI)                 |
| 8   | Attachments             | `components/issues/attachment`, `services/file.service.ts`, `services/file-upload.service.ts`, `store/editor/asset.store.ts`, `store/issue/issue-details/attachment.store.ts`                                                                             | `utils/src/attachment.ts`, `utils/src/file.ts`                                                                                                                                                 | `FileAsset` (`db/models/asset.py`), `app/views/asset/v2.py` (endpoints `assets/v2/workspaces/<slug>/…` e `…/projects/<id>/…`), `app/views/issue/attachment.py`                                     | L⁴                                   |
| 9   | Activity                | `components/common/activity/*` (`ActivityBlockComponent` genérico), `components/core/activity.tsx` (issue), `components/issues/issue-detail/issue-activity/*`, `store/issue/issue-details/activity.store.ts`                                              | `types/src/activity.ts` (`TBaseActivity`, `TWorkspaceBaseActivity` genéricos)                                                                                                                  | `IssueActivity`, `bgtasks/issue_activities_task.py` (1604 linhas), `bgtasks/webhook_task.py::model_activity`                                                                                       | F (backend) / L (UI base)            |
| 10  | Search                  | `components/power-k/ui/modal/search-*`, `services/workspace.service.ts` (`/search/`, `/entity-search/`)                                                                                                                                                   | `types/src/search.ts` (`TSearchEntities`)                                                                                                                                                      | `app/views/search/base.py` (`GlobalSearchEndpoint` com dict `entity → filter_fn`, `icontains` no Postgres; `entity-search`), `app/views/search/issue.py`                                           | F⁵                                   |
| 11  | Filters                 | `components/rich-filters/*` (UI genérica), `components/work-item-filters/*` (consumidor issue), `components/issues/issue-layouts/filters` (legado)                                                                                                        | `types/src/rich-filters`, `utils/src/rich-filters`, `shared-state/src/store/rich-filters` (motor genérico com `IFilterAdapter`), `shared-state/src/store/work-item-filters` (adapter de issue) | `utils/filters`, `utils/issue_filters.py`                                                                                                                                                          | N (motor) / F (adapter)              |
| 12  | Lists                   | `components/base-layouts/list` (**genérico, sem consumidores no CE**), `components/issues/issue-layouts/list`, `components/core/list`                                                                                                                     | `@plane/blocks/virtual-list`, propel `list`/`table`, `types/src/base-layouts`                                                                                                                  | —                                                                                                                                                                                                  | N (base) / F (issue)                 |
| 13  | Boards                  | `components/base-layouts/kanban` (**genérico, sem consumidores**), `components/base-layouts/gantt`, `components/issues/issue-layouts/{kanban,calendar,spreadsheet,gantt}`, `components/gantt-chart` (39 arquivos, 3 acoplados)                            | `types/src/base-layouts/{kanban,gantt}`                                                                                                                                                        | —                                                                                                                                                                                                  | N (base) / F (issue)                 |
| 14  | Modals                  | `components/common/modal`, `components/modals/{workspace,project,work-item}-level.tsx`, `GlobalModals`                                                                                                                                                    | propel `dialog`/`alert-dialog`, `@plane/blocks/dialog`                                                                                                                                         | —                                                                                                                                                                                                  | N (primitivos) / F (modais de issue) |
| 15  | Drawers                 | `components/issues/peek-overview/*` (painel lateral de issue)                                                                                                                                                                                             | propel `drawer`, `popover`, `preview-card`                                                                                                                                                     | —                                                                                                                                                                                                  | N (primitivo) / F (peek)             |
| 16  | User / Assignee pickers | `components/dropdowns/member/member-select.tsx` (roster do workspace quando `projectId` ausente), `store/member`                                                                                                                                          | `@plane/blocks/property-select` (`MemberSelect`), propel `avatar`/`avatar-group`                                                                                                               | `WorkspaceMember`, `ProjectMember`                                                                                                                                                                 | L                                    |
| 17  | Date pickers            | `components/dropdowns/merged-date.tsx`                                                                                                                                                                                                                    | `@plane/blocks/property-select` (`date-select`, `date-range-select`), propel `calendar`, `utils/src/datetime.ts`                                                                               | —                                                                                                                                                                                                  | N                                    |
| 18  | Command palette         | `components/power-k/*` (`core/registry.ts`, `core/context-detector.ts`, `config/*`, `menus/*`, `ui/*`), `store/base-power-k.store.ts`, `store/base-command-palette.store.ts`                                                                              | `types/src/command-palette.ts`                                                                                                                                                                 | —                                                                                                                                                                                                  | L⁶                                   |
| 19  | Notifications           | `components/workspace-notifications/*`, `store/notifications/*`, rota `:slug/notifications`                                                                                                                                                               | `types/src/workspace-notifications.ts`                                                                                                                                                         | `Notification`, `UserNotificationPreference`, `EmailNotificationLog` (`db/models/notification.py`), `bgtasks/notification_task.py`, `bgtasks/email_notification_task.py`, `app/views/notification` | L (modelo) / F (produtor + UI)       |

Notas:

1. `WorkspaceAuthWrapper` busca na carga do workspace: projetos parciais, permissões de projeto, estados do workspace, favoritos e preferências de navegação. Funciona sem projetos, mas é overhead.
2. `SidebarWrapper` é genérico (title + children + quickActions); a sidebar "Projects" concreta é que lista projetos.
3. Editor: o tipo de menção `TSearchEntities` é uma união fechada (`"user_mention" | "issue" | "project" | "cycle" | "module" | "page"`); existe extensão `work-item-embed`; `projectId` é opcional em `hooks/editor/use-editor-config.ts`. O servidor `apps/live` só aceita `TDocumentTypes = "project_page"` (`apps/live/src/types/index.ts:26`, `services/page/handler.ts` lança erro para qualquer outro tipo).
4. `FileAsset.EntityTypeContext` é enum fechado; `WorkspaceFileAssetEndpoint.get_entity_id_field` e `asset_url` fazem `if/elif` por tipo. O endpoint workspace-level (`assets/v2/workspaces/<slug>/`) existe e não exige projeto.
5. Search: adicionar uma entidade = adicionar uma função `filter_*` e uma chave no dict. Não há motor de busca (sem OpenSearch/Meili no CE); é `icontains` no Postgres.
6. Power-K: registry aberto (`register`/`registerMultiple`), mas `TPowerKContextType = "work-item" | "page" | "cycle" | "module"` e o detector de contexto lê params de rota (`workItem`, `cycleId`, `moduleId`, `pageId`).

---

## 5. Outras áreas relevantes

| Área                   | Onde                                                                                                                                                          | Observação para o RADAR                                                                                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Permissões             | `app/permissions/base.py` (`allow_permission(roles, level="PROJECT"\|"WORKSPACE")`), `workspace.py`, `project.py`; FE `hooks/store/user` (`allowPermissions`) | Nível `WORKSPACE` já funciona sem projeto.                                                                                                        |
| Labels                 | `db/models/label.py` (`WorkspaceBaseModel`), `store/label.store.ts`                                                                                           | Labels de workspace possíveis (project nullable).                                                                                                 |
| Favorites / Recent     | `db/models/favorite.py`, `db/models/recent_visit.py`, `hooks/use-favorite-item-details.tsx` (`switch` por tipo)                                               | Modelos genéricos por `entity_type`; UI faz `switch` fechado.                                                                                     |
| Pages (wiki)           | `db/models/page.py`, `components/pages`, `store/pages`                                                                                                        | Página é workspace-level no banco, mas a UI CE só expõe páginas de projeto. Melhor referência existente de "objeto rico com editor colaborativo". |
| Stickies               | `db/models/sticky.py`, `components/stickies`, `store/sticky`                                                                                                  | Entidade workspace-level pura com rich text, 0 arquivos acoplados a projeto. Melhor template "mínimo" de CRUD workspace-level.                    |
| Webhooks               | `db/models/webhook.py`                                                                                                                                        | Flags booleanas fixas por entidade (`project`, `issue`, `module`, `cycle`, `issue_comment`).                                                      |
| Eventos assíncronos    | `bgtasks/*` (Celery)                                                                                                                                          | Disparo via `.delay()` direto da view; `transaction.on_commit` só em `plane/api/views/project.py`. Não há outbox.                                 |
| Testes backend         | `apps/api/plane/tests/{unit,contract,smoke}`, `docker-compose-test.yml`                                                                                       | pytest + factories; ver `tests/TESTING_GUIDE.md`.                                                                                                 |
| Stack isolada do spike | `docker-compose.radar.yml` (commit `8fa56b19d7`)                                                                                                              | Projeto Compose `plane-radar`, portas deslocadas (api 8001, db 5434, redis 6380, minio 9001/9091).                                                |

---

## 6. Limites desta análise

- Análise estática do código. A aplicação não foi executada nesta etapa.
- A edição EE (wiki, pi-chat, issue properties) não está no repositório; apenas seus seams no CE foram observados.
- O prompt 0.1 recebido estava truncado a partir do item 3 ("Quais componentes estão fo…"). Os itens seguintes foram inferidos a partir dos entregáveis da Fase 0 (`PLANE_MAP`, `REUSE_MAP`, `DOMAIN_COUPLING`).
