# 0.4 — Semantic UI

Validado em 03/10/2026. Resultado: **PASS WITH CAVEATS**, implementação e validação locais no worktree `plane-radar-phase-0-spike`. 0.3B fornece o modelo e os commands; esta etapa entrega a edição e navegação semânticas na Object Page.

## Entrega

- Renderização por PropertyDefinition dos 11 tipos suportados: string, string_list, number, integer, boolean, enum, date, datetime, email, uri e user. Enum usa choices persistidas; user reutiliza MemberSelect do workspace. Valores/defaults/ausência são distinguíveis; Clear remove valores opcionais persistidos sem default.
- Save individual passa pelo RadarService → API interna de sessão → commands de 0.3B. Datas e limites recebem feedback de validação; datetime converte horário local para ISO com timezone; listas preservam um item por linha. Falha mantém o rascunho e permite tentar novamente.
- Relações usam direção, tipo e Object compatível do mesmo workspace, considerando domain/codomain, allowed_pairs, self, duplicações e cardinalidade conhecida. Criar pela direção incoming persiste a mesma aresta source→target; não cria um segundo registro reverso.
- Forward links e backlinks usam labels normativos e navegam às páginas reais. Remoção exige confirmação e atualiza snapshots dos endpoints; Cancel não remove.
- Guest recebe campos somente leitura, editor desabilitado e ausência de controles semânticos de escrita. Backend permanece responsável pela autorização.
- Carregamento paralelo de schema, lista e snapshots. Property/Relation snapshots precisam corresponder à versão atual do Object; leitura cruzada por writes concorrentes tenta até três vezes. Snapshots anteriores mantêm os formulários montados durante refresh, desabilitados enquanto stale. Atualização de um campo preserva os demais rascunhos e title/content; Retry funciona também após falha de refresh semântico.

Primitives reutilizadas: Propel InputField/TextAreaField/Select/Button/Dialog e Plane MemberSelect, RichTextEditor e Toast. Código novo permanece no namespace RADAR. Não há novo touch point upstream nem mudança backend nesta etapa; os oito arquivos upstream modificados cumulativos (+25/−6) continuam sendo do shell/Core anteriores.

## Verificação

| Verificação | Resultado |
| --- | --- |
| `pnpm --filter web test:radar` | 42 testes, quatro arquivos, PASS (29 testes adicionados em 0.4) |
| `pnpm --filter web check:types` | PASS |
| `pnpm --filter web check:format` | PASS |
| `pnpm --filter web check:lint` | Sem erros; warnings preexistentes do web |
| OxLint estrito em components/store/services RADAR | Zero errors/warnings |
| `git diff --check` | PASS |

Unitários verificam conversões e rejeições tipadas, candidatos de relação, controles dos 11 tipos, boolean false, guest/Clear e snapshots concorrentes/retry limitado. Interações reais foram verificadas com Playwright CLI no navegador, no servidor web:3000 conectado ao stack isolado `plane-radar` (API:8001); PostgreSQL foi conferido por leitura no mesmo stack. Os 118 testes backend de 0.3B são evidência anterior preservada, não uma nova execução de backend nesta etapa.

Workspace dedicado `radar-ui-zero`, cinco Objects (Objective, Project, Risk, Decision, Person), **zero Plane Projects**. A fixture de usuários inclui Profile/onboarding e membership; sessões ficaram apenas em arquivos temporários e não integram os artefatos.

| Cenário de navegador | Evidência observada |
| --- | --- |
| Datas/status/progress, edição de title e outro rascunho | Salvamento e refresh; rascunhos não descartados por mutação de outro campo |
| Due date anterior à start date | Rejeição do command exibida, sem persistir valor inválido |
| Progress 101 | Rejeição local; correção para 25 limpa erro |
| Project advances Objective criado como incoming | Backlink Advanced by e forward Advances; navegação entre endpoints |
| Ownership Project→Person | Cardinalidade/duplicação filtradas; Cancel preserva; confirmação remove e backlink desaparece |
| Risk likelihood=4, impact=5 | Score recalculado para 20; relação threatens preservada após hard refresh |
| Decision consequences e decided_at | Lista tipada e datetime persistidos; Clear/recriação e hard refresh |
| Save com rede abortada | Rascunho preservado; retry persiste Context após restabelecer rede |
| GET properties com HTTP 503 | Erro inicial recuperado por Retry; refresh após edição de title também recuperado por Retry habilitado |
| Guest/anônimo/Object estrangeiro ao workspace | Somente leitura; redirecionamento para login; Object unavailable sem propriedades |

[Evidência estruturada e assertions PostgreSQL](./semantic-ui-runtime/validation-evidence.json) registra identidade, autoria, versões, valores finais, duas arestas ativas e tombstone de ownership. Criador e atualizador permanecem o humano de teste. Evidências visuais:

- [Objective — propriedades](../../output/playwright/radar-semantic-ui/01-objective-backlink.png).
- [Risk — propriedades e score](../../output/playwright/radar-semantic-ui/02-risk-refresh.png).
- [Decision — lista e datetime](../../output/playwright/radar-semantic-ui/03-decision-properties.png).
- [Guest — somente leitura](../../output/playwright/radar-semantic-ui/04-guest-readonly.png).
- [Objective — backlinks](../../output/playwright/radar-semantic-ui/05-objective-relations.png).
- [Diálogo de relações](../../output/playwright/radar-semantic-ui/06-relation-dialog.png).

## Limites e próxima etapa

Warnings de hydration/MobX e preferências/navegação do shell persistem; falhas de rede/503/400 usadas nos cenários negativos são intencionais. Lista permanece sem paginação, title/content seguem last-write-wins e não há histórico persistido de provenance. A cardinalidade outgoing 0..1 é filtrada localmente; para incoming, uma fonte com aresta ocupada para outro target pode ser oferecida, sendo rejeitada pelo command. Backend também resolve concorrência e toda validação final.

Não foram adicionados builders, Kanban real, comments/activity/attachments, agente, eventos/outbox ou Graph. Não foi criado commit, merge ou deploy. 0.4 permite avançar para **0.5 — cenário completo Governança de IA**, ainda pendente: Objective/Project/Decision/Action/Risk e quatro relações normativas (`advances`, `contains`, `creates`, `threatens`). A fixture de 0.4 não substitui esse cenário. **0.6 — auditoria/Go-No-Go** também permanece pendente.
