# RADAR Agent Config — Fase 1.4

Data: 04/10/2026. Fonte de verdade: PostgreSQL do Plane. O runtime em COS_AGENT_V2 consome uma cópia estruturada e versionada por execução.

## Configuração mínima

`AgentConfiguration`, migration RADAR `0007_agent_configuration`, associa uma configuração a um `RuntimeCredential` de canal `plane`. O vínculo já identifica workspace, usuário/revisor, agente, Person e contexto. Configurar não cria identidades nem grants implícitos.

| Bloco           | Campos                                                                                         |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Identity / Soul | `name` (100 caracteres), `soul` (2.000)                                                        |
| Role            | `name` (100), `purpose` (2.000)                                                                |
| Policies        | `guidelines` (até 20 itens de 500 caracteres), `require_human_approval=true`, `read_only=true` |
| Permissions     | `commands`, `object_types`, `fields`, `object_ids` (UUIDs ou `null`)                           |

O schema `1.0` é fechado: rejeita campos extras, Markdown em lugar dos blocos, tipos incorretos, flags coercivas, duplicatas e textos acima dos limites. Soul/purpose são textos dentro do JSON; nenhum arquivo Markdown participa da autoridade ou da persistência. Não há memória longa, Graph DB, builder de ferramentas ou nova integração.

Cada vínculo tem sua própria configuração, mesmo que dois vínculos usem o mesmo agente. Vínculos existentes sem configuração persistida recebem um default explícito de versão `0`. Uma leitura não grava esse default; o primeiro save cria versão `1`.

## API e UI

Sessão autenticada e membership ativa são obrigatórias. A lista e o detalhe mostram somente vínculos Plane válidos do usuário no workspace. Um usuário com vínculo pode visualizar; edição exige ser owner ou admin ativo **e** dono desse vínculo. A fase não introduz um console administrativo para editar vínculos de outras pessoas.

| Endpoint                                                      | Comportamento                                                                                               |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `GET /api/workspaces/{slug}/radar/agent-config/`              | Configurações dos vínculos válidos do usuário; lista vazia quando não provisionado/revogado                 |
| `GET /api/workspaces/{slug}/radar/agent-config/{binding_id}/` | Configuração salva/default, permissões efetivas, teto administrativo, direito de edição e opções de Objects |
| `PUT /api/workspaces/{slug}/radar/agent-config/{binding_id}/` | Quatro blocos completos e `expected_version`; devolve estado salvo                                          |

As respostas não contêm token, hash de credencial ou segredo do host. As opções de Objects respeitam o contexto e o grant e mostram até 100 itens, com indicador de truncamento. Títulos obedecem às permissões de campo.

A navegação **RADAR → Agent configuration**, em `/{workspaceSlug}/radar/agent-config/`, exibe os quatro blocos. A UI usa primitives `@makeplane/propel`, estado MobX por workspace e os endpoints de sessão. Permite selecionar commands e Objects, editar tipos/campos e salvar/recarregar. `*` significa todos os valores concedidos pelo grant e só pode ser selecionado quando o teto contém `*`; lista vazia concede zero valores. `object_ids=null` conserva todos os Objects do contexto autorizado; `[]` não disponibiliza nenhum Object.

Erros mantêm o rascunho. Em conflito, o usuário deve recarregar explicitamente a configuração salva antes de editar de novo. Uma gravação cuja resposta se perdeu pode ser conferida por GET/reload; não há retry automático que sobrescreva uma versão concorrente.

## Autoridade e auditoria

Edição usa o comando interno auditado `AgentConfigurationConfigured`, na mesma transação de provenance/outbox do RADAR. O lock de workspace serializa a gravação; `expected_version=0` cria somente se ainda não existe configuração. Versão divergente responde `409 agent_config_stale`. O modelo conserva autor, editor e referências de provenance; cada atualização incrementa a versão.

Permissions restringem o grant administrativo. A API recusa expansão de commands ou de um teto explícito de tipos/campos; Objects precisam pertencer ao contexto do vínculo. Ao executar, o backend calcula novamente a interseção entre a configuração e o grant vigente. Assim, um `*` salvo antes de uma redução do grant não restaura a autoridade anterior. Configuração não edita `ActorGrant` e não publica tools de mutação. Os commands selecionados são elegibilidade para propostas futuras, não capacidade de escrita deste executor.

## Fluxo de execução

```text
UI → sessão + membership + vínculo → AgentConfiguration versionada
                                              ↓
grant vigente ∩ permissions + contexto do vínculo + object_ids
                                              ↓
Objects/Relations/campos limitados → snapshot + agent_config + authorization_hash
                                              ↓ Bearer do host
COS_AGENT_V2 → DTO fechado → ledger do run → DeepAgentsAdapter
                                              ↓
motor existente com contexto comportamental e superfície somente leitura
```

O snapshot de dados permanece limitado a 10 raízes, 21 Objects, 40 Relations e 30.000 caracteres serializados, como na 1.3. Na fachada Plane, cada Object inclui até 20 propriedades permitidas, com até 500 caracteres JSON por valor; valores omitidos por tamanho ou limite marcam truncamento. As permissões de campos são aplicadas na consulta antes do orçamento. Ambos os extremos das relações devem estar visíveis. IDs, tipos e versões identificam os Objects; texto/propriedades seguem as permissões de campos. Não há consulta de dados pelo LLM fora desse snapshot.

`agent_config` entra na intenção persistida e no fingerprint de autoridade. Identity/Soul, Role e guidelines orientam a inferência; os limites são garantidos pelo código. O CoS também recusa contexto com Object, tipo ou campo incompatível com as permissões recebidas. O builder continua sem tools, memória pessoal, filesystem ou subagentes, independentemente do conteúdo de Soul.

Alteração de configuração invalida acesso/replay/resume de runs anteriores com `409 authorization_stale`; o usuário inicia uma nova intenção. O run antigo mantém sua cópia original para auditoria. A configuração não muda retrospectivamente uma inferência em andamento. Não existe cancelamento remoto automático por edição; a fachada bloqueia leitura/retomada sob autoridade divergente, conforme o contrato da 1.3.

## Compatibilidade e ativação

O campo CoS `agent_config` é aditivo e opcional para clientes anteriores. Pedidos sem esse campo preservam o hash original do ledger e o comportamento da 1.3. O Plane passa a enviar configuração explícita; runs Plane anteriores à atualização podem ficar incompatíveis com o novo fingerprint e exigem nova intenção. O token exclusivo, a API sintética e o canal Telegram mantêm seus contratos.

Atualizar os dois serviços antes de usar a configuração pelo Plane e aplicar a migration `0007` no ambiente escolhido. Este desenvolvimento aplica migrations somente no ambiente de testes descartável. O provisionamento e a chave do host seguem [AGENT_RUNTIME.md](AGENT_RUNTIME.md). GET sem vínculo válido mostra a orientação de provisionamento; não cria um agente automaticamente.

## Validação e diagnóstico

Os testes cobrem persistência/reload, versão concorrente, provenance, flags obrigatórias, rejeição de campos/tipos, isolamento de usuário/workspace/canal, guest/admin, revogação, interseção de grant reduzido, recorte de Objects/Relations/campos e invalidação de run. No CoS, verificam configuração recebida pelo motor, persistência após pausa/reinício, replay e compatibilidade de hash legado. O teste HTTP entre processos usa adapter real e geração determinística, sem provider.

Comandos reproduzíveis e resultados estão em [output/agent-config-20261004](../../output/agent-config-20261004/README.md). `403` indica autoridade insuficiente; `404` esconde vínculos fora do escopo; `400` indica configuração inválida; `409` exige conferir a versão revisada. `503` do runtime continua indicando configuração/transporte do host indisponível.

A [Fase 1.5 — Risk Review](RISK_REVIEW.md) foi entregue localmente em 05/10/2026, com propostas e Accept/Edit/Reject pelo Command Layer. A configuração não entrega esse loop nem ativa um piloto.

## Resultado da entrega

Implementação local concluída em 04/10/2026. **199 testes backend RADAR passaram**, incluindo 22 de configuração e 13 da fachada runtime; **67 testes selecionados CoS** e **58 frontend** passaram. Ambos os ciclos HTTP, com e sem configuração salva, usam o adapter real e geração determinística. Types, lint, format, migration check e diff check aprovados. A migration 0007 foi aplicada sobre banco de testes vazio durante a validação; nenhuma migration foi aplicada às stacks existentes. O formulário real/MobX foi conferido no Chrome em fixture isolada, cobrindo save/refresh, seleção de Objects, conflito/reload e viewer.

O [passe geral das fases implementadas](GENERAL_VALIDATION_REPORT.md) registra a regressão ampliada e a correção do recorte de propriedades autorizadas, com artefatos separados da entrega original.
