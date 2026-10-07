# E2E da simbiose — Fase 1.8

Executado localmente em **05/10/2026**. Primeira homologação do loop `Human → State → Agent → Suggestion → Human → State` com **navegador, login/shell reais do Plane, backend, runtime CoS e PostgreSQL juntos**, sem fixture de UI nem autenticação sintética. O uso em piloto com gestores reais continua pendente; não houve deploy.

**Resultado: 68/68 verificações aprovadas numa execução limpa e única**, com Deep Agents real e modelo scripted. Uma execução com o **provider real `anthropic:claude-sonnet-4-6`** completou o loop pelo shell. O E2E encontrou e corrigiu um **bloqueio CORS** que impedia qualquer mutação RADAR a partir do shell real. [Evidências e reprodução](../../output/e2e-symbiosis-20261005/README.md).

## Ambiente

| Camada | O que rodou | Diferença em relação às fases 1.4–1.7 |
| --- | --- | --- |
| Navegador | Chromium headless (Playwright), login e-mail/senha no `/` do Plane | Antes: preview app e login de fixture |
| Shell | `apps/web` em :3000 com App Rail, workspace switcher, editor rico e seletores reais | Antes: Object Page com editor/membership substituídos |
| Backend | Stack `plane-radar` (API :8001, PostgreSQL :5434), migrations RADAR 0001–0010 aplicadas | Antes: servidores WSGI descartáveis com sessão forçada |
| Runtime | Router `agent_runtime` + `DeepAgentsAdapter` do COS_AGENT_V2 em :8940 | Igual à 1.5, agora chamado pelo API real |
| Transporte | Chave por ambiente em `.secrets/` (gitignored); servidor CoS só em loopback | Antes: chave pública de teste |

Workspace dedicado por execução, com tester (admin, revisor do agente), membro sem vínculo, guest e outsider. O provisionamento usa o caminho administrativo documentado: `radar_runtime_provision` cria Person, `PersonIdentity`, binding de canal `plane` e grant; `register_actor_grant` acrescenta `CreateAction` ao teto.

## Fluxo do prompt 1.8

| Passo | Como foi exercitado | Verificado |
| --- | --- | --- |
| 1. Humano cria Risk | Diálogo "Create object" cria Objective "Implantar Governança de IA", Project "Sandbox IA" e Risk "Licenciamento pode atrasar" (com descrição) | URL da Object Page, versão 1, autoria do tester |
| 2. Risk no contexto | Admin vincula os três Objects ao contexto `company:<slug>` pelo CLI; na tela Risk Review o humano escolhe o agente e marca os três | `root_ids` do run = três Objects criados pelo humano |
| 3. Risk Review analisa | `POST agent-runtime/runs` 202 → CoS executa → `POST risk-reviews` valida fontes/versões e prepara intenções | Run completo; review e propostas salvas uma única vez |
| 4. Sugestão THREATENS + ação | Duas sugestões: Risk → Objective (confidence 0.8) e Risk → Project (0.55), cada uma com ação mitigadora | Cartões "→ threatens →" e ação com título/próximo passo |
| 5. Accept/Edit/Reject | Controles nos cartões reais | Os três botões presentes |
| 6. Humano aceita | Accept da relação; Accept da ação retorna 409 `revision_conflict` com instrução de Edit (contrato da 1.5); Edit salva revisão 2; Accept | Relação e ação `executed` |
| 7. Command Layer aplica | `LinkObjects` e `CreateAction` executados uma vez a partir da intenção salva | Eventos `ObjectLinked`, `ObjectCreated`, `ActionCreated`; Action ganha identidade `ACT-…` no contexto |
| 8. Provenance | Duas linhas por command: `pending_approval` (agente, sem aprovação) e `executed` | Ver abaixo |
| 9. Object Page | Risk: "Threatens → Implantar Governança de IA" e backlink "Mitigated by → Validar licenciamento de IA"; Action: "Mitigates → Risk"; Objective: "Threatened by → Risk" | Inclusive após reload completo |

Provenance da execução aceita (consulta direta ao PostgreSQL, 29 asserções):

| Campo pedido | Valor registrado |
| --- | --- |
| agente | `actor_type=agent`, `actor_id` = agente do binding |
| humano | `on_behalf_of` = tester; `approval_id` → `CommandApproval` com `approver_id` = tester e rationale |
| reason | explicação da sugestão |
| source | `radar.skill.risk_review` |
| run_id | run do Risk Review (também `correlation_id`) |
| confidence | 0.8 |

A aprovação é de uso único: termina `consumed`. A revisão humana (`ReviewCommand`) também é registrada com o rationale.

## Rejection, permission e idempotência

| Caso | Resultado |
| --- | --- |
| Reject da segunda sugestão (relação e ação, com rationale) | `rejected`, sem relação Risk → Project nem Action extra; provenance humana com rationale |
| Aceitar depois de rejeitar | 409 `proposal_closed` |
| Membro sem binding | Tela "No agent is linked…", nenhum review alheio; lê o Risk; start com binding alheio e resolve de proposta alheia → 404 |
| Guest | Sem controle de Run; start → 403 |
| Outsider | Shell mostra "Workspace not found"; API → 403 |
| Anônimo | resolve → 401 |
| Admin retira `CreateAction` com proposta pendente | Accept → 409 `authorization_stale`; tela informa a falta de permissão e desabilita Run |
| Grant restaurado | Proposta antiga continua 409: autorização obsoleta não é reativada |
| Replay do start com a mesma `Idempotency-Key` | Mesmo `run_id`; um único run no banco |
| Preparar o mesmo run duas vezes | Mesmas propostas; um único review |
| Repetir Accept / Reject | Resultado salvo, sem segunda escrita (uma relação, uma Action) |

## Provider real

Uma execução com `anthropic:claude-sonnet-4-6`, configurado no CoS, sobre o estado já alterado pelo fluxo: Risk com a ameaça ao Objective e a Action de mitigação. A saída passou pela validação do CoS e do Plane e foi decidida na UI.

- Sugestões: Risk → Objective (0.95) e Risk → Project (0.88). As evidências citam literalmente `title` e `properties:description/status/timeframe`, e `context_used` aponta as Relations do snapshot.
- O humano aceitou a ameaça ao Sandbox IA (`executed`) e rejeitou as duas ações. A Object Page passou a mostrar as duas ameaças, cada uma uma vez.

O resultado comprova o loop com o provider. Uma execução não mede qualidade estatística.

## Achados

| # | Achado | Tratamento |
| --- | --- | --- |
| 1 | **CORS bloqueava toda mutação RADAR do shell real.** Web (:3000) e API (:8001) são origens distintas; o preflight não permitia `Idempotency-Key` e `X-Radar-*`. Criar Object falhou com "Network Error" no primeiro passo; iniciar run e as mutações com versão esperada usam os mesmos headers. As fixtures das fases anteriores eram same-origin. | **Corrigido** em `plane/settings/common.py` (bloco RADAR; linha upstream intacta). Regressão: `test_session_transport.py` (preflight permite os cinco headers em quatro rotas; origem não listada continua recusada) |
| 2 | `radar_runtime_provision` concede `LinkObjects`, mas não `CreateAction`, exigido pelo Risk Review | Passo de ativação: estender o grant pelo controle existente (`register_actor_grant`), como feito no E2E |
| 3 | Objects criados pelo humano só entram no contexto do agente após vínculo administrativo pelo CLI (decisão de [COS_INTEGRATION](COS_INTEGRATION.md)) | Mantido. Para o piloto, cada novo Object relevante exige esse passo; avaliar fluxo administrativo na UI |
| 4 | Aceitar a relação torna a ação irmã obsoleta (409 → Edit → Accept) | Mantido por decisão (contrato 1.5, sem rebase automático); custo de UX: um Edit por par aceito |
| 5 | O cartão da ação aparece antes do da relação (ordenação por `component`) | Pendente (UX) |
| 6 | O modelo real reconhece uma relação já existente e ainda a sugere; Accept consome a aprovação sem alterar o domínio, mas o cartão diz "Applied successfully" | Domínio protegido (sem duplicata nem versão nova). Pendente: sinalizar "já registrada" no review |
| 7 | Rejeição não volta ao agente: a ameaça ao Sandbox IA, rejeitada no run scripted, reapareceu no run real | Esperado sem memória (Fase 4); registrar para o piloto |
| 8 | Uma ação sugerida pelo modelo real apenas repetia a própria relação ("Vincular formalmente…") | Qualidade de skill; o humano rejeitou |
| 9 | Object Page mostra UUID em "Created by"/"Updated by"; o agente não vem pré-selecionado | Pendente (UX menor) |

## Validação automatizada

Regressão backend com migrations reais em banco vazio após a correção: **972/972 aprovados** (272 RADAR, incluindo 5 novos de transporte CORS, + 700 Plane), zero skipped; integrações HTTP Plane → CoS ativas; `manage.py check` e drift de migrations limpos. Ruff aprovado. Nenhum arquivo frontend de produto mudou. [Log e JUnit](../../output/e2e-symbiosis-20261005/README.md).

## Limites

- **Piloto não realizado**: utilidade para gestores reais não foi medida; 1.8 fica com a homologação técnica concluída e o piloto pendente.
- Provider real em uma única execução; Chromium headless em viewport desktop; servidor web de desenvolvimento, HTTP local sem TLS.
- Passos administrativos (provisionamento, vínculo, grant) por CLI/shell, como documentado; não há UI administrativa para eles.
- Publisher da outbox, Today com propostas pendentes e upload de anexo pela UI (pendência da 1.7) não fizeram parte deste fluxo.

## Teardown

Ao final: servidores CoS (:8940/:8937) e web (:3000) encerrados, sessões `.secrets/e2e-auth/` apagadas, Compose de regressão removido com `down -v` e stack `plane-radar` parada sem remover volumes. Os workspaces `radar-e2e` e `radar-e2e-clean` permanecem no banco local como evidência consultável. A stack Plane baseline não foi tocada.
