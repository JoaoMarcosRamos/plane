# 0.6 — Auditoria da Fase 0 e Go/No-Go

**Decisão técnica: CONDITIONAL GO**, em **03/10/2026**, para evoluir o MVP local da Fase 1 sobre o Plane. O cenário completo comprova Core e Object Page independentes de Project/WorkItem. O alvo amplo de reuso da UI e a baseline de anexos permanecem ressalvas verificáveis. Esta decisão não representa readiness de produção, merge ou publicação.

## Evidência do gate

0.3A, 0.3B e 0.4 permanecem documentadas nos relatórios históricos. [0.5 — Governança de IA](./GOVERNANCE_SCENARIO_REPORT.md) acrescenta os cinco Objects conectados pelas quatro relações normativas, edição de propriedades, navegação nos dois sentidos, refresh, isolamento e PostgreSQL em workspace sem Plane Projects. Backend: **130 testes PASS**; frontend: **42 PASS**; types, format, lint estrito RADAR, Ruff, migrations e diff conferidos nesta execução.

O tipo adicional `audit_probe` foi configurado como **fixture de schema** num workspace separado, `radar-audit-generic`. Apareceu no Create Dialog e na lista genérica; seu Object foi criado pela UI e `reading=42` salvo/recarregado na mesma Object Page. [Screenshot](../../output/playwright/radar-governance/06-generic-type.png), [assertion PostgreSQL](./governance-runtime/validation-evidence.json) e teste backend comprovam a ausência de tela específica. Configuração de schema foi feita pela fixture administrativa; isso não comprova Type Builder, API de configuração ou extensibilidade completa da Fase 2.

## Baseline e entrega consolidada

| Item                     | Estado conferido                                                                                   |
| ------------------------ | -------------------------------------------------------------------------------------------------- |
| Tag `radar-baseline`     | `1ee511b642babd4ec9f9cb734883b51d7a217a50`                                                         |
| HEAD / branch            | `8fa56b19d7864da0c80a4ae92dc4371d5487699e` / `radar-phase-0-spike`                                 |
| Worktree                 | `plane-radar-phase-0-spike`; árvore principal separada `../plane`                                  |
| Remotes                  | origin: JoaoMarcosRamos/plane; upstream: makeplane/plane; radar: JoaoMarcosRamos/plane-radar-spike |
| Isolamento DB            | Compose `plane-radar`, PostgreSQL:5434, API:8001; testes em projeto separado `plane-radar-tests`   |
| Versionamento da entrega | Alterações locais e arquivos novos inventariados; sem novo commit, push, merge ou deploy           |

O inventário compara **working tree versus a tag**, incluindo fontes RADAR ainda untracked. A comparação apenas de commits não contém os slices locais e seria insuficiente. [fork-metrics.json](./governance-runtime/fork-metrics.json) guarda caminhos, linhas e imports. Reproduzir: `python3 docs/radar/phase-0/audit_spike.py > /tmp/radar-fork-metrics.json`. O script é somente leitura e não depende de rede.

Regressão das rotas Plane preservadas, no stack do spike: login por senha com humano de teste dedicado, workspace, Project existente, criação de WorkItem `RADAR-8`, edição pelo editor original e comentário salvos e mantidos após refresh. [Baseline estruturada](./governance-runtime/baseline-evidence.json), [screenshot](../../output/playwright/radar-governance/08-plane-baseline.png) e [rede](./governance-runtime/baseline-network.txt).

**Baseline não recebe PASS integral.** A tentativa de anexo `.txt` recebeu HTTP 400; os metadados enviados pelo uploader precisam de diagnóstico, e nenhum upload foi concluído. A API isolada ainda anuncia `AWS_S3_ENDPOINT_URL=http://localhost:9000`, porta do MinIO da árvore original. Antes de repetir com arquivo válido, isolar também a configuração de storage e validar upload/download/refresh. A validação atual é regressão de código Plane preservado no spike; não é reexecução de um checkout pristine da tag. Esses limites encerram o checklist com resultado parcial explícito, sem substituir evidência histórica nem alterar o upstream para fazê-lo passar.

## Arquivos Plane alterados e risco de merge

**Oito touch points upstream, +25/−6 linhas cumulativas; zero novos touch points em 0.5/0.6.** O `docker-compose.radar.yml` (+30 linhas desde a tag) é arquivo próprio do isolamento, contabilizado separadamente.

| Arquivo                                         | Delta | Finalidade / risco                                                              |
| ----------------------------------------------- | ----- | ------------------------------------------------------------------------------- |
| apps/api/plane/settings/common.py               | +1    | Registrar app Django RADAR; conflito localizado em INSTALLED_APPS               |
| apps/api/plane/urls.py                          | +1    | Incluir URLs próprias; conflito localizado na composição de rotas               |
| apps/web/app/(all)/[workspaceSlug]/layout.tsx   | +1/−1 | Habilitar App Rail; wrapper compartilhado exige regressão                       |
| apps/web/app/routes/extended.ts                 | +2/−1 | Agregar rotas RADAR; acompanhar alterações de routing                           |
| apps/web/components/navigation/app-rail-hoc.tsx | +9/−1 | Dock item/seam RADAR; maior risco relativo por mudanças frequentes de navegação |
| apps/web/hooks/use-workspace-paths.ts           | +4/−1 | Detecção do caminho RADAR                                                       |
| apps/web/package.json                           | +4/−2 | Script/dependência Vitest local; acompanhar catálogo e scripts upstream         |
| pnpm-lock.yaml                                  | +3    | Resolução do catálogo; regenerar de forma consistente em upgrades               |

Nenhuma alteração em model/view/serializer de Issue, Project, autenticação, membership, editor, design system, comments ou attachment. Nenhuma FK RADAR para Project/Issue/ProjectBaseModel. RadarBaseModel deriva diretamente de Django; autoria recebe Actor pelos commands.

## Reuso: denominador e limite do percentual

O alvo original “>70% da UI reaproveitável” não definiu denominador nem pesos. Para medir **reuso efetivamente integrado**, usamos as 19 capacidades fixas de REUSE_MAP §1; retiramos Authentication/Workspace do denominador UI, restando **17 capacidades de UI com peso igual**. Contam apenas integrações reais em código RADAR validado; mock, primitive com bug visual e capacidades futuras não contam. Isso mede cobertura de capacidades, não percentual de linhas, telas ou esforço poupado.

Resultado: **8/17 = 47,06% de integração efetiva de UI**; incluindo Auth/Workspace, **10/19 = 52,63%**. O patamar >70% não foi atingido por essa medida conservadora. Não converter classificações R1/R2 potenciais ou quantidade de imports em percentual entregue. [Scorecard completo](./governance-runtime/reuse-scorecard.json).

| Capacidade UI                                                                    | Estado para a contagem                                                                                                            |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Navigation, Sidebar, Design System, Rich Text Editor                             | Reutilizados no fluxo persistido                                                                                                  |
| Lists, Modals                                                                    | BaseListLayout e Dialog com Objects reais                                                                                         |
| User/Assignee pickers                                                            | MemberSelect integrado ao renderer `user`; validação tipada e primitive no spike; ownership normativo continua Person via relação |
| Date pickers                                                                     | InputField `type=date/datetime-local` no fluxo persistido; DateSelect foi demonstrado no spike, não substitui esse renderer       |
| Boards                                                                           | Primitive validada com mock; nenhum board persistido                                                                              |
| Drawers                                                                          | Primitive demonstrada com bug de CSS conhecido; não conta como integração concluída                                               |
| Comments, Attachments, Activity, Search, Filters, Command palette, Notifications | Não entregues como capacidades RADAR reutilizadas neste gate; search própria não é reuso da busca Plane                           |

Os componentes Plane consumidos sem alteração incluem SidebarWrapper/ResizableSidebar/SidebarNavigation, AppHeader/ContentWrapper/PageTitle/BreadcrumbLink, BaseListLayout, RichTextEditor e MemberSelect; Propel Button/InputField/TextAreaField/Select/Dialog/Badge/icons e Plane Blocks layout/breadcrumb/select/toast. O JSON de métricas lista cada import e consumidor **fora do playground mock**.

Adaptações vivem em RadarSidebar/Header, provider/layout/rotas, RadarNotesEditor, RadarObjectsList, RadarObjectPage, PropertyEditor, ChoiceField, SemanticPanel e RelationDialog. APIService/RadarService e stores MobX próprios seguem padrões Plane. Comments/attachments/activity requerem backend RADAR próprio; IssueComment/IssueActivity não são base segura para isso.

## Código RADAR novo e manutenção

O inventário contém **66 arquivos de código/config/seed/testes RADAR**, **6.533 linhas**, **sete arquivos de testes**, **duas migrations** e **seis models concretos**: ObjectType, Object, PropertyDefinition, PropertyValue, RelationType e Relation. Inclui arquivos `__init__`, playground e configuração; exclui documentação, screenshots e caches. Esse denominador é mais amplo que contagens históricas, portanto não representa automaticamente o delta entre slices. Nesta entrega foram acrescentados commands/governance.py, management command e seus dois `__init__`, e tests/test_governance.py; scripts de auditoria/evidência são documentação e ficam fora desse total.

Estimativa de manutenção **qualitativa: baixa superfície de conflito direto e risco médio de regressão do shell/contratos de primitives**. +25/−6 linhas não medem custo real de upgrades. Sem histórico de rebase/upgrade e tempo de correção, não há base para horas, dinheiro ou frequência inventados. A cada atualização Plane, revisar os oito anchors, catálogo/lockfile e contracts de Propel/editor; executar a suíte RADAR e os fluxos de navegação/zero Projects/baseline Plane. O app Django e os namespaces frontend próprios reduzem conflitos de arquivos, mas ainda dependem de sessão, membership, routing e componentes compartilhados.

## Acoplamentos, impacto e dívidas

| Área                   | Conclusão atual                                                                                                                                 |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| WorkItem               | Zero referências de domínio no Core; zero requests Issues no cenário. RootStore global ainda instancia IssueRootStore e emite warnings de MobX. |
| Project                | Zero FK/requisito de container; `project` RADAR é dado. Workspace wrapper ainda faz GETs de Projects e preferências.                            |
| Auth / Workspace       | Sessão e WorkspaceMember herdados; regras de RADAR usam roles 20/15/5. Não há alteração profunda; scope organizacional/policies ainda futuros.  |
| Design system / Editor | Código compartilhado intacto; hidratação, rascunho HTML inicial e Drawer merecem acompanhamento.                                                |
| Comments               | Rotas originais criam/persistem comentários; nenhum backend RADAR implementado ou substituído.                                                  |
| Attachments            | Upload válido da baseline ainda sem round trip; storage do stack precisa de isolamento completo. Nenhum attachment RADAR implementado.          |
| Auditoria              | created_by/updated_by/version comprovados; reason/source/correlation do Actor ainda sem histórico persistido.                                   |
| Concorrência / escala  | Sem expected_version no título/content, sem paginação; não apto a assumir edição concorrente/escala de piloto.                                  |
| Produto                | Today/Boards/playground não equivalem a cockpit/board reais; não há agente, eventos/outbox, Graph ou colaboração RADAR.                         |

## Scorecard original e decisão

| Critério original                                                       | Resultado                                                              |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| UI reaproveitável >70%                                                  | Não demonstrado; integração efetiva 47,06% pelo denominador declarado  |
| Object Page genérica / Relations bidirecionais / backlinks              | PASS no cenário completo                                               |
| Dependência WorkItem / Project obrigatório                              | Baixa no shell; nenhuma no domínio Core comprovado com zero Projects   |
| Alteração profunda Auth / Workspace / Design System / Editor / Comments | Não; código preservado e regressão parcial observada                   |
| Novo tipo sem novo componente                                           | PASS via fixture de schema + UI/API genérica; builder permanece futuro |
| Upstream reconhecível / API RADAR independente                          | PASS pela superfície de oito seams e APIs/commands próprios            |
| Custo do fork aceitável                                                 | CONDITIONAL: superfície pequena; esforço de upgrade ainda não medido   |
| Checklist da baseline original completo                                 | Parcial; anexos e replay pristine continuam pendentes                  |

**CONDITIONAL GO**: a pergunta estrutural do spike foi respondida positivamente. Podemos construir RADAR sobre Plane sem impor WorkItem/Project ao domínio; não há motivo técnico observado para NO-GO. GO sem ressalvas seria incorreto pelos gaps medidos acima.

Condições para continuidade:

1. Evoluir a Fase 1 local mantendo PostgreSQL mestre, scopes de workspace e todas as writes por commands; persistir provenance/propostas/approval antes de writes de agente. Não iniciar runtime/agente nesta entrega.
2. Antes de considerar release compartilhada/piloto, versionar os arquivos locais, completar a configuração isolada de storage, anexos e replay da baseline, e testar upgrade/rebase real para medir manutenção.
3. Reavaliar reuso com o mesmo inventário quando colaboração/board/filtros/search forem necessários; definir meta por capacidades entregues e resolver os limites de concorrência/paginação conforme o piloto. Não tratar mock como reuso de feature.

Fase 0 encerrada **localmente com CONDITIONAL GO**; 0.5 e 0.6 entregues. As ressalvas estão preservadas como gates seguintes, não apagadas dos relatórios anteriores.
