# Risk Review — Fase 1.5

Entregue localmente em **05/10/2026**, no Plane e COS_AGENT_V2. Uma única nova skill de produto: `risk_review`. O diagnóstico legado `context_summary` permanece compatível. Não houve commit, merge, deploy ou ativação de ambiente publicado.

## Comportamento

RADAR → **Risk Review** permite selecionar o agente e até 10 Objects de contexto. O snapshot autorizado contém até 21 Objects, 40 Relations e 30.000 caracteres. O CoS usa o Deep Agents existente, sem tools de escrita, memória pessoal, filesystem ou subagentes. A geração só produz análise; não altera Objects/Relations.

A saída fechada contém `summary` e até cinco sugestões:

- `explanation`: hipótese explicada como inferência;
- `suggested_relation`: Risk → `threatens` → Objective/Project;
- `suggested_action`: mitigação opcional, com título, descrição, próximo passo e Risk;
- `confidence`: número finito de 0 a 1;
- `evidence`: Object ID, versão, campo e citação literal;
- `context_used`: IDs das Relations utilizadas.

Os dois serviços verificam os extremos/tipos, fontes/versões, citações exatas, vínculo da mitigação e Relations do snapshot. Ambos os extremos precisam ser citados. Campos extras, confidence inválida, fontes externas e pares duplicados são recusados. `title`, `content` e `properties:<key>` são os únicos campos de evidência. Essa validação garante a origem das evidências, não a correção causal da inferência. Um resultado sem sugestões é válido; truncamento permanece explícito.

## Revisão e unidade de aprovação

Plane mantém uma cópia imutável do resultado em `RiskReview` e uma proposta por componente em `RiskReviewProposal`. Relação e ação são **unidades de aprovação independentes**, associadas a `CommandExecution`/`CommandApproval`, ao run e à revisão. Preparar usa os handlers reais em savepoints de preview e rollback: nenhuma linha de domínio persiste antes do aceite.

**Accept** revisa o hash da intenção salva e aplica `LinkObjects` ou `CreateAction` na mesma transação de aprovação. O executor confiável usa o envelope salvo, sem nova chamada ao modelo. IDs, estado real, provenance e recibo são retornados; retry devolve o resultado salvo, sem duplicar efeitos.

**Edit** valida os novos argumentos, conserva o Risk e a família de efeito, limita os IDs ao snapshot autorizado e registra quem editou. Salva uma nova intenção, com nova prévia e contexto filtrado atualizado, retirando a intenção anterior. A edição **não executa**; a nova intenção exige Accept. Citações e confidence continuam sendo da inferência original, identificada na UI como “Original inference”. Target pode mudar para outro Objective/Project do mesmo snapshot; a ação só pode mitigar o Risk original. Falha de validação desfaz toda a edição, mantendo a proposta original pendente.

**Reject** chama `review_command`, salva rationale na aprovação e provenance da revisão humana com run, proposal ID e decisão. Não altera Objects/Relations. Uma proposta rejeitada não pode ser aceita depois. O histórico de substituições permanece disponível.

Não existe promessa de atomicidade entre a relação e a ação: aceitar a relação pode mudar versões usadas pela ação. O aceite da ação então retorna conflito, preserva o efeito já confirmado e pede **Edit** para salvar/revisar uma nova intenção ou uma nova execução de Risk Review. Não há atualização automática de versões. TTL da aprovação: 30 minutos; expiração exige nova revisão. Configuração, grants, membership, Person, binding e schema vigentes continuam sendo revalidados; configuração obsoleta invalida runs/propostas históricos sem rebase. Contexto deletado ou fora do escopo deixa de aparecer na fila.

## API de sessão

| Endpoint | Operação |
| --- | --- |
| `POST agent-runtime/runs/` | `skill=\"risk_review\"`, binding, raízes, prompt e Idempotency-Key |
| `GET risk-reviews/` | Até 30 runs recentes e propostas do usuário/workspace ainda autorizados |
| `POST risk-reviews/` | `run_id`; consulta resultado, valida e prepara as intenções uma vez; retorna 202 enquanto incompleto |
| `POST risk-reviews/{proposal_id}/resolve/` | `decision=accept/edit/reject`, `intent_hash`, `rationale`; somente Edit recebe `edited_input` |

O navegador nunca escolhe Actor, grant, workspace de escrita ou envelope. A API fornece uma projeção mínima do preview/recibo: linhas completas de auditoria não são expostas por esta superfície. Errors de versão, autoridade e expiração são traduzidos em instruções de revisão na UI. O store MobX mantém a mesma chave ao repetir um start cuja resposta se perdeu. Resultados pendentes podem ser recuperados com **Check review**; polling automático é limitado.

## Validação e limites

- **229 testes backend RADAR passaram**, com migrations reais em PostgreSQL isolado; 27 casos do novo arquivo Risk Review incluídos. Cobrem preview sem domínio, Accept, Reject/feedback, Edit/rollback, replay, versões concorrentes, revogação/configuração, limites de fontes e HTTP real entre processos.
- **1.182 testes CoS passaram**, 11 opt-in desativados, zero falhas/erros. A suíte inclui Deep Agents real com modelo scripted, JSON fechado, citações, ausência de tools e replay sem outra inferência.
- **72 testes frontend passaram**; tipos, lint e format verificados. Incluem renderização com MobX real, controles, histórico, errors e chave de retry.
- Chrome: componentes reais Risk Review/serviço/store, Plane HTTP e PostgreSQL isolados, CoS HTTP e Deep Agents com modelo scripted. Aceite de relação, conflito da ação, edição e aceite de ação, reload e rejeição verificados. Consultas de banco confirmam uma relação `threatens`, uma Action, uma relação `mitigates`, identidade canônica da Action e provenance da rejeição.

A fixture usa autenticação sintética exclusivamente no servidor de teste. O teste da Object Page usa permissões de leitura sintéticas, apresentação passiva das notas e placeholder do seletor de membro. Login/shell completo, editor rico, qualidade com provider real e TLS remoto não foram homologados. Piloto/Today/colaboração permanecem etapas posteriores.

[Evidências, comandos e screenshots](../../output/risk-review-20261005/README.md). [Motor CoS e decisões](../../../COS_AGENT_V2/docs/development/045-radar-risk-review.html).

## Ativação posterior

Atualizar ambos os serviços e aplicar as migrations Plane `0008_risk_review` e `0009_risk_review_preview`. O CoS reutiliza o ledger existente, sem nova migration. O binding de canal Plane precisa de grants vigentes para `LinkObjects` e `CreateAction`, cobertura de Risk/Objective/Project/Action e campos de criação/defaults; Agent Config só restringe esse teto. URLs/chave de transporte continuam exclusivamente no servidor. Nenhuma chave nova é necessária.

Antes de piloto, homologar provider real e shell completo e manter os gates de baseline/release do [relatório de prontidão](NEXT_PHASE_READINESS.md). Publisher de outbox, memória longa, Graph DB e catálogo amplo de skills continuam fora deste incremento.
