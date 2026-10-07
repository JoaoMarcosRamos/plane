# Prontidão após o E2E 1.8 — simbiose no shell real

Atualizado em 05/10/2026. Escopo: implementação local no Plane e **COS_AGENT_V2**. `JMR_Personal-CoS` permanece referência histórica, sem ser destino deste desenvolvimento.

**Fases 1.5 e 1.6 entregues localmente; colaboração mínima 1.7 implementada.** Today consulta riscos relevantes, decisões pendentes, ações vencidas e propostas persistidas, sem mutações automáticas. Ver [Today](TODAY.md). Risk Review, Accept/Edit/Reject, intenção salva e execução pelo Command Layer foram validados com geração determinística. Ver [contrato e evidências](RISK_REVIEW.md). Comments, attachments e activity usam backend próprio por Object e Command Layer. A homologação do upload pela UI ainda está pendente; ver [escopo e evidências de colaboração](COLLABORATION.md). O [E2E 1.8](E2E_SYMBIOSIS.md) homologou o loop completo no shell real, com login, runtime CoS e provider real. O MVP Human–Agent Loop ainda não passou pelo piloto e não está pronto para avanço à Fase 2.

## Evidências vigentes

E2E 1.8: **68/68 verificações** numa execução limpa com login/shell reais, API, runtime CoS (Deep Agents) e PostgreSQL; provider real `anthropic:claude-sonnet-4-6` completou o loop pela UI. Rejection, permissões (membro, guest, outsider, anônimo, grant revogado) e idempotência verificados. Corrigido o CORS que bloqueava mutações RADAR no shell real. [Relatório e achados](E2E_SYMBIOSIS.md).

Colaboração mínima: **263 backend e 92 frontend aprovados**, quatro opt-in skipped; checks/migrations aprovados. [Testes, HTTP real e navegador](../../output/collaboration-20261005/README.md). Sessão Django/PostgreSQL reais validaram autoria, isolamento, auditoria, downloads e remoção; storage é privado no PostgreSQL, 2 MiB por arquivo. Upload pela UI, storage/quotas/retenção no ambiente escolhido e shell/login completos são gates de homologação, não itens entregues por mocks.

Today: 77 frontend e 234 backend únicos aprovados, quatro opt-in backend desativados; types/lint/format/Ruff aprovados. Navegador verificou quatro filas, links para Object/revisão, rejeição/refresh e estados vazio/erro com HTTP/PostgreSQL isolados. [Logs e limites](../../output/today-20261005/README.md). CoS não foi alterado/reexecutado nesta fase.

Evidência histórica da 1.5: 229 testes RADAR backend e 1.182 CoS passaram, com 11 opt-in desativados; 72 frontend passaram. Migrations PostgreSQL e HTTP entre processos foram validados. Chrome verificou os controles reais com dados sintéticos; provider real, login/shell completo e piloto continuam pendentes. Relação e ação têm approvals independentes; concorrência exige nova intenção explícita via Edit. [Logs e limites](../../output/risk-review-20261005/README.md).

## Base e evidências históricas da 1.4

A entrega 1.4 passou em **199 testes backend RADAR, 67 CoS selecionados e 58 frontend**. Types, lint, format, Ruff e migration check passaram. Os resultados pertencem à execução da implementação; esta atualização documental não reexecutou as suítes.

O backend foi validado contra PostgreSQL isolado, incluindo migration `0007_agent_configuration` e transporte HTTP entre processos Plane → CoS com adapter real e geração determinística. O formulário real e o store MobX foram verificados no Chrome em fixture isolada: save, refresh, seleção de Objects, conflito/reload e viewer. Essa fixture não homologa login, shell completo, provider real ou TLS remoto.

Fontes: [resultado e comandos](../../output/agent-config-20261004/README.md), [resultado estruturado](../../output/agent-config-20261004/result.json), [Agent Config](AGENT_CONFIG.md), [Agent Runtime](AGENT_RUNTIME.md) e [integração de commands](COS_INTEGRATION.md).

As alterações permanecem locais, sem commit/merge/deploy. A evidência não representa uma release reproduzível somente a partir de HEAD. Os manifestos registram os arquivos no momento da entrega; atualizações documentais posteriores não alteram esses hashes históricos.

O [passe geral posterior](GENERAL_VALIDATION_REPORT.md) revalidou 902 casos backend únicos, 1.170 CoS e 58 frontend, corrigiu o orçamento de propriedades e confirmou migrations/checks. Nove avaliações de provider real continuaram desativadas; os gates de piloto não foram encerrados.

## Situação por etapa

| Etapa                        | Estado atual                                                                                                | Trabalho restante                                                   |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 1.1 — Command Layer          | Implementado; catálogo comum e quatro operações CoS                                                         | Manter contrato e catálogo alinhados                                |
| 1.2 — Provenance e approvals | Backend implementado: autoria, grants, versões, intenção, revisão, replay e outbox transacional             | UI e coordenação entregues na 1.5; publisher operacional pendente   |
| 1.3 — Agent Runtime          | Implementado localmente: fachada Plane, adapter CoS, contexto limitado, eventos, pausa/retomada cooperativa | Ativação do ambiente escolhido; integração com propostas em 1.5     |
| 1.4 — Agent Config           | Implementado localmente: quatro blocos persistidos, versão, UI e cópia por run                              | Ativação conjunta Plane/CoS e provisionamento dos vínculos          |
| 1.5 — Risk Review            | Entregue localmente                                                                                         | Homologação de qualidade com provider real                          |
| 1.6 — Today                  | Entregue localmente; quatro filas com consulta real e deep links                                            | Homologar atenção gerencial no shell completo/piloto                |
| 1.7 — Colaboração            | Implementada localmente: comments, anexos privados e activity por Object                                    | Homologar upload UI/sessão real e storage/quotas/retenção no piloto |
| 1.8 — E2E/piloto             | E2E homologado localmente no shell real; provider real em uma execução; CORS corrigido ([E2E](E2E_SYMBIOSIS.md)) | Piloto com gestores reais; achados de UX/ativação do relatório       |

## Contratos preservados pelas entregas 1.5/1.6

O PostgreSQL do Plane governa domínio, configuração, permissões e approvals. O CoS recebe uma intenção durável e um snapshot limitado; tipos LangChain/LangGraph permanecem atrás do adapter. O caminho Plane → runtime é separado do caminho CoS → commands. A API de simulação e o canal Telegram conservam seus contratos.

Identity/Soul, Role e guidelines orientam comportamento. Autoridade é calculada pelo servidor: grant vigente ∩ configuração ∩ contexto do vínculo. O contexto comporta até 10 raízes, 21 Objects, 40 Relations e 30.000 caracteres serializados. Ambos os extremos de uma relação precisam estar visíveis; campos são filtrados antes do snapshot.

O executor de produto entregue continua sem tools de mutação, filesystem, memória pessoal ou subagentes. Policies mantém `read_only=true` e `require_human_approval=true`. Selecionar commands na configuração indica elegibilidade futura de propostas; não habilita escrita pelo modelo.

Editar configuração invalida leitura/replay/resume de runs anteriores com `409 authorization_stale`, preservando sua intenção histórica. Não cancela automaticamente inferência remota em andamento. A [1.5](RISK_REVIEW.md) define explicitamente o vínculo entre run, sugestão e command, respeitando configuração/grants/versões vigentes.

## Escopo da 1.5 entregue e critérios usados

1. Implementar uma única skill Risk Review, com saída validada: explanation, suggested_relation, suggested_action, confidence e evidence/context used. As fontes devem pertencer ao snapshot autorizado; inferência deve permanecer distinguível de fato.
2. Mostrar propostas do escopo com explicação, evidências e prévia. Accept revisa a intenção salva; Edit produz uma nova intenção validada; Reject registra feedback/provenance sem alterar o domínio.
3. Reutilizar o armazenamento autoritativo de approvals e o Command Layer. Após aceite, um executor confiável aplica a intenção revisada uma vez, sem pedir ao modelo para recriá-la. A UI acompanha o resultado real.
4. Verificar grants e catálogo necessários, incluindo LinkObjects/CreateAction. Configuração de usuário não pode ampliar o teto administrativo. Definir unidade de aprovação e falha parcial quando relação e ação envolvem commands separados; não presumir atomicidade entre eles.
5. Provar o cenário “Licenciamento pode atrasar” → “Implantar Governança de IA”/“Sandbox IA”, com evidências e estado final na Object Page. Cobrir rejeição, edição, repetição, revogação, autorização obsoleta e versões concorrentes com geração determinística.

Contrato de execução: [prompt 1.5](../../../DOCS_PROJETO_RADAR_COMPLETO/radar_prompts_por_fase.md#prompt-15--primeira-skill-risk-review). O prompt define o escopo; a evidência de entrega está no relatório Risk Review.

## Gates antes de piloto compartilhado

Atualizar ambos os serviços (incluindo a liberação CORS dos headers RADAR), aplicar migrations no ambiente escolhido e provisionar identidades canônicas, vínculo de canal Plane e grants — o grant do binding precisa de `CreateAction` além do padrão do CLI, e Objects criados pela UI precisam de vínculo administrativo ao contexto. A chave de transporte permanece exclusivamente no servidor. Homologar o fluxo completo e a qualidade com provider real; homologar uploads e storage/retenção da [colaboração RADAR](COLLABORATION.md), mantendo os gates de storage/anexos/replay pristine da [baseline Plane](SPIKE_REPORT.md) separados e consolidar versão reproduzível dos dois repositórios.

Eventos/outbox estão persistidos transacionalmente, mas publisher/consumidores operacionais não foram entregues. Essa persistência não comprova entrega assíncrona. Graph DB, memória longa, segundo runtime e catálogo extenso de skills permanecem fora do próximo slice.

## Histórico da decisão

A avaliação anterior autorizava iniciar 1.3 e apontava a ausência de contrato de runtime e configuração estruturada. Essas lacunas foram atendidas pelas entregas [1.3](AGENT_RUNTIME.md) e [1.4](AGENT_CONFIG.md); seus relatórios e manifestos permanecem como evidência histórica. As fases 1.5 e 1.6 foram entregues em 05/10/2026; a decisão vigente é preparar as etapas seguintes sem encerrar os gates do piloto.
