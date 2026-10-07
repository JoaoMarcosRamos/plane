# Today — atenção gerencial mínima (1.6)

Entregue e validada localmente em 05/10/2026. Acesso: **RADAR → Today**, em `/:workspaceSlug/radar/today/`.

Today reúne exclusivamente quatro filas de atenção, a partir do estado persistido no PostgreSQL. Cada item apresenta título, motivo e link para o Object ou a revisão humana existente. Reutiliza Button/Badge do Propel, navegação, Header/ContentWrapper do Plane e store MobX por workspace. Não acrescenta gráficos, KPIs, cards de totais, criação de objetos ou execução automática.

## Critérios de inclusão

| Grupo                          | Critério                                                                                                                                             | Ordem                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Riscos relevantes              | Status `identified`, `monitoring`, `mitigating` ou `accepted`; score ≥ 15 **ou** `review_date` anterior a hoje                                       | Score decrescente, revisão e ID           |
| Decisões pendentes             | Status `proposed`                                                                                                                                    | Mais recentes primeiro, ID como desempate |
| Ações vencidas                 | Status `todo`, `in_progress` ou `waiting`; `due_date` anterior a hoje                                                                                | Prazo mais antigo primeiro, ID            |
| Sugestões aguardando aprovação | Risk Review do usuário atual; execução `pending_approval`, approval `pending`, não expirado e sem substituição; autoridade/contexto ainda acessíveis | Mais antigas primeiro, ID                 |

Score é o valor canônico derivado de likelihood × impact pelo Command Layer. O limiar 15 é uma regra explícita desta tela mínima, sem nova configuração. Riscos `closed`, decisões tomadas/revogadas/substituídas e ações concluídas/canceladas ficam fora. Prazo no dia corrente não é vencido; data ausente não gera alerta. A tela não infere status a partir de texto ou timestamps de atualização.

## Consulta e autorização

`GET /api/workspaces/:slug/radar/today/?timezone=America/Bahia` retorna `date`, `timezone`, `risks`, `decisions`, `overdue_actions` e `suggestions`. O cliente envia o fuso IANA do navegador; sem parâmetro a API usa UTC, e fuso inválido retorna 400. Datas de prazo/revisão são datas civis, sem conversão de meia-noite UTC na UI.

A consulta exige sessão e membership, aplica workspace e soft deletion, lê apenas tipos/definições ativos e considera defaults persistidos nas definições sem materializá-los. Propriedades são carregadas em lote, sem um request HTTP por Object. O endpoint não inicializa schema, cria configuração, consulta o CoS ou grava domínio/provenance.

Sugestões são limitadas aos runs do próprio usuário, revalidados por `access_run`, incluindo grants, configuração, vínculo e disponibilidade dos Objects no contexto. Não há corte silencioso das sugestões às 30 revisões recentes. O link inclui `?proposal=<id>#risk-proposal-<id>`; a API Risk Review seleciona o run correspondente sob as mesmas permissões, e a UI mantém esse foco após Accept/Edit/Reject. A revisão continua a validar versões e autoridade no momento da decisão. Uma mudança de versão não apaga a pendência: requer revisão/Edit no fluxo existente.

## Comportamento da UI

- Estados de carregamento, erro com botão Atualizar e vazio por grupo.
- Atualização ao abrir, ao retornar o foco/visibilidade e por ação explícita; requests concorrentes são deduplicados.
- Dados anteriores ficam ocultos durante reload e após falha, evitando apresentar approvals antigos como atuais.
- Links para Object Page e Risk Review; nenhuma aprovação acontece dentro de Today.
- Layout de coluna única, títulos acessíveis e links com nomes específicos; validado em desktop e mobile.

## Validação e limites

**77 testes frontend aprovados**, types/lint/format aprovados; **9 testes novos Today backend aprovados** após ajustar os fixtures ao contrato canônico. A regressão backend executou 238 casos: 231 passaram, quatro opt-in foram desativados e três fixtures novos falharam inicialmente; a reexecução final de Today passou nos nove casos. Isso representa **234 casos backend únicos aprovados**, sem somar reexecuções. Ruff aprovado. Nenhuma mudança de schema/migration.

Chrome → HTTP Plane → PostgreSQL isolado comprovou os quatro grupos, links para Object/revisão, remoção de uma proposta rejeitada, layout desktop/mobile sem overflow e estados vazio/erro reais. O preview usa componentes e stores de produto com autenticação sintética e editor/membership simplificados somente na fixture. Não homologa login/shell completo, provider real ou piloto; nenhum deploy foi realizado. CoS não foi alterado nem revalidado nesta entrega.

[Comandos, logs e screenshots](../../output/today-20261005/README.md). Próximas etapas: colaboração necessária ao MVP (1.7) e homologação E2E/piloto (1.8).
