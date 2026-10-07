# CORE_VERTICAL_SLICE_REPORT — 0.3A

2026-10-03 · worktree `plane-radar-phase-0-spike` · stack isolado `plane-radar`.

## Executive Summary

**PASS WITH CAVEATS.** Vertical slice completo, persistido e validado pela UI e PostgreSQL. Commands recebem Actor explícito desde o primeiro write; created_by permanece estável no update; version incrementa de forma serializada. Funciona com zero Plane Projects.

Ressalvas: overhead e warnings preexistentes do shell, já registrados no spike 0.2B; listagem sem paginação, atualização com last-write-wins e auditoria mínima (sem histórico de eventos). Nenhuma impede os critérios de 0.3A.

Documentos anteriores estavam em `docs/radar/phase-0/`, não na raiz solicitada. Foram lidos nessa localização. SPIKE_PLAN e ARCHITECTURE não existiam; foram criados em `docs/radar/`. A nova sequência é **0.3A Foundation → 0.3B Semantic Model**; 0.3B não foi implementada.

## Backend Architecture

```text
apps/api/plane/radar/
├── apps.py
├── models/core.py
├── commands/actor.py
├── commands/objects.py
├── api/serializers.py
├── api/views.py
├── api/urls.py
├── migrations/0001_initial.py
└── tests/test_core.py
```

App label `radar`; PostgreSQL é fonte de verdade. Migration independente, dependente de `db.0122` e do User configurado. Tabelas `radar_object_types` e `radar_objects`. Nenhum model em plane.db, nenhuma FK para Project/Issue/ProjectBaseModel. Únicas entidades externas referenciadas: Workspace e User; membership é consultado para autorização.

## RadarBaseModel

Abstrato próprio, diretamente sobre models.Model. UUID uuid4, created_at/updated_at, FKs próprias created_by/updated_by e deleted_at. TimeAuditModel foi inspecionado: é puro; os dois campos foram redeclarados para evitar importar um módulo que também importa tarefas Celery. ChangeTrackerMixin também foi inspecionado, mas não utilizado.

Não herda BaseModel/AuditModel/SoftDeleteModel, não importa crum e não sobrescreve autoria com estado de request. objects filtra deleted_at; all_objects permite inspeção histórica. delete de instância e queryset é bloqueado; exclusão futura será command. FKs de workspace/tipo usam PROTECT. Exclusão de User preserva o registro e anula sua FK de autoria (SET_NULL).

## Actor

Dataclass imutável com actor_type, actor_id, reason, source, correlation_id, run_id. Tipos preparados: human/agent/system/integration; commands autorizam somente human nesta etapa. API obtém actor_id do usuário autenticado, define source/reason e gera correlation_id. Não aceita ator nem campos de autoria do payload.

Contexto reason/source/correlation/run é transportado pelo Actor, ainda sem armazenamento histórico. Identidade de autoria humana é persistida em created_by/updated_by. Não existe Agent model ou runtime.

## Command Layer

- initialize_object_types: membership de leitura, trava Workspace, get_or_create dos cinco tipos, atomic e idempotente inclusive sob concorrência.
- create_object: usuário humano ativo, Workspace ativo, membership member/admin, tipo ativo/não excluído do mesmo tenant, título válido e HTML sanitizado; preenche ambos os autores e versão 1.
- update_object: mesmas validações, objeto do workspace, campos permitidos somente title/content/object_type; select_for_update, created_by preservado, updated_by explícito, version incrementada. Campos de auditoria são somente leitura.

Todos persistem em transaction.atomic. Não há escrita ORM de Object na view. Falhas revertem o write e a eventual inicialização dos tipos. Futuro evento/outbox poderá entrar antes do retorno dentro da mesma transação, sem reimplementar a operação. Não há Command Bus, Domain Events ou Outbox agora.

## ObjectType

workspace, key, name, description, icon, is_system, is_active, auditoria e deleted_at. UniqueConstraint parcial de (workspace, key) WHERE deleted_at IS NULL. is_active=false desabilita uso; reserva a chave até exclusão. Tipos iniciais objective/project/decision/action/risk, is_system=true.

Inicialização lazy no GET object-types e no CreateObject via command. Todo workspace recebe os mesmos cinco tipos como registros próprios. Não altera provisionamento de workspace nem workspace_seed, não cria Project demo. Um guest pode ler/inicializar tipos; criação/edição de Object exige member/admin.

## Object

workspace, object_type, title, content HTML, version, auditoria e deleted_at. FK de tipo validada no command contra workspace. CheckConstraint de versão ≥1; índice workspace/object_type. HTML é o formato já produzido pelo RichTextEditor; validate_html_content (nh3) sanitiza no command, inclusive para consumidores futuros sem DRF. Não existe PropertyDefinition/PropertyValue.

## API

Somente API interna de sessão; BaseSessionAuthentication/BaseAPIView e WorkspaceMemberPermission do Plane. Sem API pública v1.

| Método      | Endpoint                                                  |
| ----------- | --------------------------------------------------------- |
| GET         | `/api/workspaces/:workspaceSlug/radar/object-types/`      |
| GET / POST  | `/api/workspaces/:workspaceSlug/radar/objects/`           |
| GET / PATCH | `/api/workspaces/:workspaceSlug/radar/objects/:objectId/` |

DRF valida o payload → monta Actor → chama command → serializa resultado. Serializers de saída são read-only; campos desconhecidos/de auditoria no input retornam 400. Non-member recebe 403; Object de outro workspace não é encontrado (404), mesmo se o usuário participa de ambos. Nenhum endpoint requer projectId.

## Frontend

RadarService tem listObjectTypes/listObjects/getObject/createObject/updateObject, somente URLs RADAR e cliente HTTP de sessão do shell. Tipos próprios; sem IssueService/ProjectService.

RadarRootStore MobX guarda ObjectTypes e Objects, com cache por id e proteção contra resposta de versão antiga. Provider fica em (radar)/layout e é recriado por workspaceSlug; não registrado no root.store do Plane nem recebe IssueRootStore/ProjectRootStore.

- Home aponta para Objects.
- BaseListLayout real agrupa Objects por ObjectType.
- Dialog Type/Title salva pela store/service/API/command; erro mantém formulário, sucesso fecha, atualiza cache/lista, navega e mostra toast.
- `/:workspaceSlug/radar/objects/:objectId/` lê Object real e mostra tipo, título, content, created_by, updated_by e version. Editor HTML não colaborativo; save explícito via PATCH.
- Properties/Relations/Backlinks/Activity têm indicação clara de não implementados.
- A rota histórica de mock Object Page agora mostra a lista real; playground de componentes continua claramente mock e não é o caminho do produto.

## Plane Touch Points

| Métrica                          | Nesta etapa 0.3A              | Cumulativo desde o shell   |
| -------------------------------- | ----------------------------- | -------------------------- |
| Arquivos upstream alterados      | 4 novos touch points          | 8                          |
| Seams de runtime upstream        | 2 backend                     | 6 (4 frontend + 2 backend) |
| LOC upstream                     | +9 / −2                       | +25 / −6                   |
| Arquivos de código RADAR criados | 26 (15 backend + 11 frontend) | 43 (inclui 17 do shell)    |
| Models concretos                 | 2                             | ObjectType e Object        |
| Model abstrato / ator            | 1 / 1 dataclass               | RadarBaseModel / Actor     |
| Migrations RADAR                 | 1                             | 0001_initial               |
| Endpoints (método + path)        | 5                             | 3 patterns de URL          |
| Testes automatizados RADAR       | 48                            | 43 backend + 5 frontend    |

Os quatro touch points adicionais são settings/common.py (+1), plane/urls.py (+1), apps/web/package.json (+4/−2 para Vitest/script) e pnpm-lock.yaml (+3, dependência já existente no catálogo). Os quatro anteriores mantêm +16/−4. Mudanças em arquivos RADAR do shell não são contadas como upstream. Documentos/screenshots não entram na contagem de código. Nenhum toque no root store, modelos, services ou UI de Issue/Project.

## Tests

### Backend — PASS (43 testes)

Suite em PostgreSQL separado, project Compose `radar-core-tests`, migrations habilitadas. Cobre criação/escopo/unique/soft-delete/tipos iniciais, create/update/version, HTML sanitizado, Actor explícito, criador preservado com segundo ator e fora de request, tenant/tipo cruzado, membership/guest/inativo, rollback, delete bloqueado e os cinco endpoints com sessão, anônimo e non-member. Concorrência real com duas conexões confirma versões 2/3 e inicialização idempotente.

Comando padrão reproduzível:

```sh
docker compose -f docker-compose-test.yml run --rm --build api-tests pytest plane/radar/tests --migrations
```

Neste ambiente o buildx não pôde escrever seu arquivo de atividade sob ~/.docker. A execução usou a imagem local já construída `plane-radar-api:latest`, via override temporário apenas da imagem do api-tests, mantendo serviços/env/volumes do docker-compose-test.yml. Código vem do volume deste worktree; nenhum teste executado no banco de desenvolvimento nem no stack principal. Resultado final: **43 passed**.

### Frontend — PASS

```sh
pnpm --filter web test:radar
pnpm --filter web check:types
pnpm --filter web check:lint
pnpm --filter web check:format
```

5 testes Vitest: carregamento por workspace, criação/cache/update/auditoria, isolamento entre instâncias, falha sem write inventado e rejeição de versões antigas em respostas. Typecheck e format passaram. Lint web: 0 erros, 538 warnings preexistentes; lint estrito nos arquivos RADAR: 0 erros/warnings. Django check, ruff check/format e makemigrations radar --check --dry-run passaram.

Revisão React: hooks incondicionais, provider com vida útil por tenant, cancelamento de atualizações de estado após unmount, fetch paralelo dos tipos/lista, feedback de loading/error/retry, input labels e submit desabilitado durante requests. Nenhum framework Next.js introduzido; os shims existentes continuam usados.

### Cenário UI + PostgreSQL — PASS

Chrome/Playwright, UI deste worktree e API :8001.

| Passo                                            | Resultado                                                      |
| ------------------------------------------------ | -------------------------------------------------------------- |
| RADAR home → Objects → Create Object → Objective | PASS                                                           |
| Criar “Implantar Governança de IA”               | version 1; tipo objective; created_by=updated_by=usuário atual |
| Editar “Implantar Governança de IA na C3”        | version 2; created_by preservado; updated_by correto           |
| Hard refresh + deep link                         | título e versão 2 persistem                                    |
| Voltar à lista e refresh                         | objeto real agrupado em Objective                              |
| Workspace radar-zero                             | 0 Plane Projects confirmado na API e no ORM/PostgreSQL         |
| Projects → RADAR → Projects                      | client-side; marcador window preservado                        |
| Workspace radar-projects                         | Objects funciona e home Projects continua funcionando          |
| Non-member em radar-other                        | Workspace not found; Object não monta; API 403                 |
| Anônimo em deep link                             | redirect para login com next_path                              |
| Network no fluxo RADAR                           | 0 requests Issue/work-items; 0 parâmetros projectId/project_id |

Objeto persistido: `8b79f670-fc63-48df-b511-184c1823621d`, workspace `radar-zero`; ator `44bd8c7c-ca1e-4eb3-b1a7-f016262d6a16` (`radar-tester`). O Object de prova permanece no stack isolado.

Evidência estruturada: [validation-evidence.json](./core-runtime/validation-evidence.json). Screenshots: [criação](./core-runtime/core-create-object.png), [versão 1](./core-runtime/core-object-version-1.png), [versão 2 após refresh](./core-runtime/core-object-version-2-refresh.png), [lista real](./core-runtime/core-real-list.png), [non-member](./core-runtime/core-nonmember-blocked.png), [anônimo](./core-runtime/core-anonymous-redirect.png), [Projects](./core-runtime/core-projects-still-works.png).

## Technical Debt

- RootStore global do shell ainda instancia IssueRootStore e workspace wrapper ainda busca projects/project-roles/states/user-properties. Overhead já constatado em 0.2B, sem dependência funcional do RADAR.
- Hard load produz hydration mismatch e warnings MobX preexistentes; Projects também tem warnings de button aninhado. Non-member gera 403 esperados nas chamadas antecipadas do wrapper. Não foram alterados neste slice.
- Lista sem paginação/filtros; editor sem anexos/colaboração; sem histórico de atividade, exclusão ou UI de edição de ObjectTypes.
- Version é contador auditável, não optimistic concurrency: updates simultâneos são serializados, mas último write vence. Política de conflito futura deve usar expected_version se necessária.
- reason/source/correlation/run não são histórico persistido; isso exige futura estratégia de provenance/eventos. Commands são a interface de aplicação; SQL/ORM interno de manutenção ainda pode contorná-los, não é um boundary de segurança para código Python confiável.
- Created by/Updated by mostram UUID estável; apresentação de nome/avatar pode usar o roster do shell posteriormente. Remoção de usuário anula a FK, conforme política SET_NULL explícita.
- Lazy initialization escreve no primeiro GET autorizado de tipos e serializa por workspace. É opção de menor impacto agora; provisioning explícito pode substituí-la no futuro sem acoplar Projects.

## Next Recommendation

**Estamos prontos para implementar PropertyDefinition / PropertyValue / RelationType / Relation? YES.** Os gates fundamentais passaram: app/migrations próprias, ator explícito, commands transacionais, escopo, auditoria, concorrência, persistência e UI sem Projects. 0.3B deve estender os mesmos commands e a mesma fronteira; decidir armazenamento de PropertyValue e escopo de RelationType antes da migration. Nenhuma implementação de 0.3B foi iniciada.

## Resultado final

- **CORE VERTICAL SLICE: PASS WITH CAVEATS** — cenário real completo; ressalvas de shell e limites descritos acima.
- **COMMAND LAYER FROM FIRST WRITE: YES** — inclusive inicialização dos tipos; UI e views convergem para commands.
- **WORKITEM COUPLING: NONE** — no Core/API/service/store/componentes RADAR; overhead indireto do shell continua documentado.
- **READY FOR PROPERTIES + RELATIONS: YES** — foundation validada; sequência 0.3B como próxima tarefa, não executada automaticamente.
