# RADAR — Command Layer

**Status:** Command Layer implementado na camada Django em 04/10/2026, com os dez comandos, migrations, provenance, grants, approvals e outbox transacional. UI e adaptadores Python passam pelo mesmo dispatcher. A entrega original 1.1/1.2 não integrava Deep Agents. O runtime foi entregue posteriormente em [1.3](AGENT_RUNTIME.md), seguido de [Agent Config 1.4](AGENT_CONFIG.md); revisão humana na UI é escopo de 1.5.

**Extensão CoS:** o [contrato de integração 1.0](./COS_INTEGRATION.md) acrescenta quatro comandos de domínio, autenticação de host, vínculos canônicos e confirmação da intenção salva. O snapshot passa a onze Object Types, conservando a versão/hash do Core. O relatório de compatibilidade anterior registra o estado antes desse adapter.

**Extensão colaboração 1.7:** [seis commands human-only](COLLABORATION.md) — AddComment, EditComment, DeleteComment, AddAttachment, RenameAttachment e DeleteAttachment — compartilham dispatcher, idempotência e provenance. Comentários/anexos têm revisão própria sem alterar Object.version; upload multipart vincula metadados/hash a bytes transitórios e grava tudo atomicamente no PostgreSQL. Activity já consulta essa provenance, incluindo filhos no endpoint de auditoria do Object.

## 1. Objetivo e base existente

Humano e agente usam os mesmos nomes, schemas, validações, permissões, transações e eventos. UI, API e adaptador de agente apenas autenticam a origem, montam o contexto confiável e invocam a mesma camada de aplicação. Nenhum deles escreve diretamente em Object, PropertyValue ou Relation. PostgreSQL permanece a fonte de verdade; não há dependência de Plane Project/Issue.

O ponto de partida é a camada em `apps/api/plane/radar/commands`, não uma segunda implementação:

| Contrato público                                                                         | Base do spike                                                  | Implementação atual                                        |
| ---------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------- |
| CreateObject                                                                             | `create_object`                                                | Propriedades iniciais, idempotência, provenance e evento   |
| UpdateObject                                                                             | `update_object`, `set_property_value`, `remove_property_value` | Patch atômico, revisão esperada e guards de domínio        |
| LinkObjects                                                                              | `create_relation`                                              | Contrato comum, guards de relações protegidas e provenance |
| UnlinkObjects                                                                            | `remove_relation`                                              | Mesmo contrato, proteção de evidências e approvals         |
| CreateAction, CompleteAction, RegisterRisk, CreateDecision, ApproveDecision, AddEvidence | Novos handlers de aplicação dedicados                          | Composição das mesmas primitivas, com regras específicas   |

A camada central é `commands.execution.execute_command`. As fachadas existentes (`objects.py` e `semantic.py`) convertem chamadas para o envelope comum; as primitivas exigem um contexto de comando. `Actor` identifica human, agent, system ou integration. Grants, revisão esperada, histórico completo, idempotência e aprovação são persistidos. Os registros de domínio apontam para a provenance de criação e última alteração.

Referências locais: [ARCHITECTURE](./ARCHITECTURE.md), [SEMANTIC_MODEL_ADR](./SEMANTIC_MODEL_ADR.md), [SEMANTIC_MODEL_REPORT](./SEMANTIC_MODEL_REPORT.md) e [snapshot Core 3.2.0](../../apps/api/plane/radar/ontology/core-3.2.0.json). A snapshot registra a origem `JMR_RADAR_ONTOLOGY/ontology/core.yaml` e seu SHA-256. A fonte completa também define `create_action`, `close_action`, `approve`, `document`, `verifies`, `informed_by`, `evidences`, `manage_in_context`, `approve_in_context` e `action_closure_requires_evidence`; parte disso está fora do subconjunto do spike.

Regras adicionais de approval e controle de revisão são políticas da aplicação. O snapshot mantém a versão e hash da fonte normativa e inclui Document, verifies e informed_by; evidences continua restrita aos pares normativos, cujos tipos de alvo não estão neste subconjunto.

## 2. Fronteira e contrato comum

```text
UI humana / API / adaptador de agente
    → autenticação e Actor explícito
    → Command Layer: schema → scope → permission → regras → approval
    → transação PostgreSQL: domínio + provenance + resultado + eventos/outbox
    → consumidores futuros após commit: activity, índices, notificações internas
```

Não é necessário um framework de Command Bus. O dispatcher resolve os contratos originais e suas extensões CoS/colaboração para handlers que reutilizam validadores e primitivas internas. Composição não deve chamar endpoints HTTP nem abrir commits independentes.

### 2.1 Envelope

Todos os commands recebem o envelope abaixo, além do `input` específico. `?` significa opcional; UUID significa identidade RADAR imutável. Campos desconhecidos são rejeitados.

| Campo                             | Contrato                                                                                                                                                                                                                         |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `command_name`, `command_version` | Nome do catálogo público documentado aqui e nas extensões CoS/colaboração; versão inicial `1`. Versão desconhecida é rejeitada.                                                                                                  |
| `workspace_id`                    | UUID opcional no envelope porque o workspace já vem do argumento confiável/URL; quando informado deve coincidir. O boundary é obrigatório para objetos, tipos, pessoas, evidências, grants e approvals.                          |
| `idempotency_key`                 | String não vazia, até 128 caracteres, estável nos retries da mesma intenção.                                                                                                                                                     |
| `expected_versions`               | Mapa UUID → inteiro ≥ 1. Obrigatório para todos os Objects existentes lidos como precondição ou alterados; `{}` somente quando não há referências existentes. O handler calcula o conjunto necessário e rejeita omissões/extras. |
| `reason`                          | Texto não vazio explicando a intenção. Não substitui rationale, outcome ou descrição do domínio.                                                                                                                                 |
| `input`                           | Payload tipado do command; nunca aceita campos internos de autoria, aprovação concedida ou versão final.                                                                                                                         |
| `approval_id?`                    | Referência a uma aprovação de execução persistida; não é um booleano enviado pelo consumidor.                                                                                                                                    |
| `proposal_id?`                    | Referência a proposta agente rejeitada quando um humano assume uma nova intenção; execução pelo próprio agente usa seu CommandExecution como proposta.                                                                           |
| `assertion`                       | `{kind: asserted \| observed \| inferred, evidence_ids: UUID[], confidence?: number}`. `confidence` em [0,1] para inferências; não mede autorização nem prova veracidade.                                                        |

O adaptador acrescenta um **Actor confiável**, fora do payload livre: `actor_type`, `actor_id`, `source`, `correlation_id`, `timestamp`, `reason`, `run_id?`, `approval_id?`, `confidence?` e `on_behalf_of?`. `reason` validado integra o Actor. Identidade, source e IDs de execução são derivados ou conferidos pela autenticação; não são aceitos por declaração do cliente.

Human exige User ativo, não bot, sessão/autenticação válida e membership ativo. Agent exige principal próprio registrado, execução rastreável, `run_id` obrigatório e delegação explícita no workspace. Não pode se apresentar como humano. `on_behalf_of` identifica quem delegou, sem transferir automaticamente suas permissões. System/integration exigem os mesmos grants explícitos; sem registro ficam negados. Um owner/admin pode configurar dispensa de approval individual para esses dois tipos. Agentes sempre exigem revisão humana.

`assertion` é obrigatório para registrar a origem epistêmica da alteração. Evidências referenciadas devem existir, ser legíveis e pertencer ao workspace. Uma alegação inferida permanece identificada como inferida após approval; aprovação autoriza uma mudança, não transforma uma hipótese em observação. Dados de agente não podem perder sua origem ao serem aceitos ou editados por humano.

### 2.2 Resultados e erros

Resposta comum: `command_id`, `status`, `code`, `correlation_id`, `created_ids`, `affected_ids`, `versions_before`, `versions_after`, `event_ids`, `provenance_id`, `approval_id?`, `proposal_id?`, `findings` e `data` específico. IDs/versões/eventos de domínio ficam vazios enquanto não houve execução. Resultado de criação inclui o Object; link inclui Relation; aprovação inclui DecisionApproval.

| `status`           | Significado                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| `executed`         | Commit concluído; resultado persistido e eventos registrados.                                    |
| `noop`             | Estado já equivalente, sem mudança de versão nem novo evento de domínio. Tentativa auditada.     |
| `pending_approval` | Solicitação/proposta persistida; **nenhuma mutação de domínio**.                                 |
| `rejected`         | Schema, permission ou regra impeditiva falhou.                                                   |
| `conflict`         | Revisão, idempotência ou approval não corresponde ao estado atual. Releitura/revisão necessária. |
| `failed`           | Falha de persistência/infraestrutura; domínio integralmente revertido.                           |

A API usa os erros DRF: 400 para validação, 403 para permissão, 404 para referência fora do scope e 409 para `revision_conflict`, `idempotency_conflict` ou `approval_stale`. Pendência retorna 202 com `approval_required`. Falhas de infraestrutura revertem a transação; não são convertidas em sucesso. Erros de validação por campo são estruturados. `rejected`, `conflict` e `failed` descrevem resultados de erro, não um CommandExecution confirmado; `rejected` é persistido quando há rejeição humana de proposta. Não retornar detalhes de registros de outro workspace; resolução de identidade fora do scope equivale a `not_found`. A falha de membership não revela se o Object existe.

### 2.3 Validação, concorrência e idempotência

1. Autenticar e validar schema/envelope; autorizar workspace antes de resolver identidades do domínio. Revalidar permissão em cada tentativa, inclusive replay.
2. Reservar a chave única `(workspace_id, actor_type, actor_id, idempotency_key)`. Guardar hash canônico de nome/versão/input/reason/assertion/proposal e revisões esperadas. Actor e workspace fazem parte do contexto. `approval_id` é credencial de autorização anexável à mesma intenção, não parte da intenção revisada.
3. Mesmo hash e chave retornam o resultado anterior; hash diferente retorna `idempotency_conflict`. Pending pode avançar para executed com aprovação válida. Execuções concorrentes da mesma chave aguardam o resultado único; uma falha revertida admite retry da mesma intenção, sem reservar sucesso inexistente.
4. Carregar tipos/propriedades/relações ativos do workspace e validar valores sem coerção: datas ISO, datetime com timezone, enums fechados, limites e campos obrigatórios. Sanitizar HTML na aplicação. UUID, tipo, scope e campos de auditoria não são editáveis por payload.
5. Aplicar invariantes estruturais e regras impeditivas. Findings gerenciais não invalidam por si sós dados válidos; por exemplo, Action sem owned_by gera RADAR-M001, não um erro de schema. Findings persistem com a versão avaliada.
6. Calcular plano de efeitos e dependências. Avaliar permission e approval sobre **todos** os efeitos, inclusive relações/propriedades derivadas. O wrapper genérico não reduz os requisitos de um command especializado.
7. Na execução, travar Objects envolvidos em ordem UUID e comparar `expected_versions`. Para consultas de conjuntos usados como precondição, travar também o conjunto/guard necessário contra alterações concorrentes. Toda alteração de relação trava e versiona endpoints, de modo que mudanças no conjunto invalidem snapshots anteriores.
8. Revalidar regras, grants, policy version, approvals e dependências sob transação. Persistir domínio, resultado, provenance, eventos e outbox no mesmo commit.

Cada Object existente alterado recebe **um** incremento por command composto, mesmo se várias propriedades/relações mudarem. Object novo termina em versão 1 com seus defaults e efeitos iniciais. Relações versionam os dois endpoints, uma vez cada; self-link versiona o Object uma vez. Objetos somente consultados são verificados/travados, mas não incrementados. Creator é preservado; remoção de propriedade/relação mantém tombstone e autoria.

Retry de command executado não produz novo write, evento ou approval consumido. Noop não reatribui autoria. Para LinkObjects, uma aresta ativa equivalente retorna a identidade existente; relink após soft delete gera nova Relation. UnlinkObjects de tombstone conhecido no workspace retorna noop; UUID desconhecido retorna not_found. Alterar payload/revisões após conflito é nova intenção e exige nova chave; não há rebase automático.

### 2.4 Eventos e efeitos assíncronos

Eventos são fatos de um commit, não pedidos para executar efeitos. Envelope comum: `event_id`, `event_type`, `event_version=1`, `workspace_id`, `command_id`, `occurred_at` do servidor, `correlation_id`, `causation_id`, `actor`, `run_id?`, `proposal_id?`, `approval_id?`, `provenance_id`, `versions_before/after` e `payload` do fato. Referências sensíveis seguem o mesmo controle de leitura; logs não recebem tokens ou conteúdo integral desnecessário.

Gravar evento/outbox na mesma transação; consumidores idempotentes por `event_id`, entrega ao menos uma vez e ordenação por versão do Object. Não prometer exactly-once na rede. Publicar após commit; rollback não publica eventos de domínio. Falhas de projeção não fazem o command confirmado parecer falho.

Commands compostos geram os eventos dos fatos efetivamente produzidos com o mesmo `command_id`; não duplicam eventos ao reutilizar primitivas. Exemplo: CreateAction gera ObjectCreated, ActionCreated e ObjectLinked para cada link novo. Replay/noop não reemite fatos. Pendência gera somente evento de controle `CommandApprovalRequested`; rejeição/conflito não geram evento de domínio. Revisão humana gera evento de controle e provenance; falhas de validação e infraestrutura não persistem uma execução parcial.

A outbox durável está implementada; publisher, consumidores de activity/busca e notificações internas são trabalho posterior. Nenhum dos dez commands executa uma tarefa externa, envia e-mail/mensagem, chama integração ou prova que uma pessoa foi comunicada. `requires_notification` registra obrigação, não entrega.

## 3. Permission, provenance e approval

### 3.1 Permission

Permission responde se o principal pode solicitar/executar a operação. Approval responde se aquela intenção específica recebeu revisão humana suficiente. Approval não concede permission ausente.

Humano: membership member (15) ou admin (20) é requisito de escrita; guest (5) permanece somente leitura. Operações ordinárias seguem `manage_in_context`: write_grant + contexto + acesso aos Objects. Aprovação de decisão segue `approve_in_context`: esses requisitos mais context_approver. Membership admin não é aprovação implícita nem atribuição automática de context_approver. Person é Object do domínio, não db.User; `owned_by`/`assigned_to` não concedem acesso por si sós.

Na implementação inicial humana, `manage_in_context` é resolvida pelo gate member/admin e workspace vigente. ActorGrant e context_approver são persistidos antes de sua utilização; na ausência de uma autoridade de aprovação configurada, ApproveDecision é negado. Os nomes de capacidades por command abaixo descrevem as responsabilidades; os gates efetivos são membership, ActorGrant e PersonIdentity, sem uma engine RBAC genérica.

Agente: exige grant por workspace/command/tipo/campos e acesso aos Objects, limitado pela delegação e pelo estado atual do delegante. Grant ausente é deny; approval não supre essa ausência. Os mesmos validators e guards se aplicam a humano/agente. Mesmo catálogo não significa mesmos direitos: ApproveDecision e a tomada de decisão são human-only.

### 3.2 Provenance persistida

Uma entrada append-only por command executado registra:

- `command_id`, chave/hash de intenção, nome/versão, workspace e schema/ontology version;
- iniciador, executor efetivo e delegante, com actor_type/id; reason, source, correlation, run e timestamps do servidor; o timestamp declarado pelo Actor permanece no contexto, separado do horário de registro;
- proposal/origem do agente e suas revisões; confidence, kind e referências à evidência da assertion;
- input normalizado ou referência imutável a ele, diff antes/depois, versões, IDs criados/removidos e resultados/findings;
- policy/grants/regras avaliadas e suas versões; aprovação, aprovador humano, rationale e instante da revisão;
- IDs dos eventos e relação causal com comando/proposta anterior.

Provenance também acompanha valores e arestas por referência a essa entrada; `created_by`/`updated_by` são compatibilidade de auditoria, não sua substituição. Se o principal é agente, não gravar o delegante como se tivesse feito a alteração: guardar identidade do agente e humano revisor separadamente. FKs de User anuladas futuramente não apagam a identidade histórica registrada.

Noops, solicitação e revisão/recusa de approval têm provenance; expiração é conferida na revisão/execução, sem job de alteração de estado. Tentativas inválidas, conflitos e falhas revertidas retornam erro, sem registro durável separado de tentativas nesta implementação. Dados protegidos continuam sujeitos a acesso/retenção; provenance não pode servir como canal de exposição entre workspaces.

### 3.3 Dois registros distintos de approval

**CommandApproval** autoriza a execução de uma intenção pendente. Guarda workspace, command/proposal, hash do payload normalizado, hash do schema efetivo e prévia dos efeitos armazenada no resultado da execução, `expected_versions`, referências/versões das evidências, policy version, solicitante, aprovador, reason/rationale, timestamps, expiração e estado `pending | approved | rejected | consumed` (expiração derivada de expires_at). São estados do registro de controle, não vocabulários de Decision.

Aceitar/editar/rejeitar uma proposta usa esse fluxo comum de controle, sem criar um command alternativo de escrita no domínio. O executor retoma o command original pela mesma chave e principal solicitante. Aceitar não executa SQL na UI nem reclassifica o executor agente como humano. Editar cria nova revisão da proposta/intenção, novo hash/chave e exige revisão. Rejeitar não escreve no domínio. Se humano assumir a execução de uma sugestão, encerrar a intenção pendente anterior e registrar uma nova intenção humana vinculada à proposta, preservando a origem do agente; nunca manter as duas intenções executáveis.

Approval aprovada é de uso único e consumida no mesmo commit do command. Revalidar aprovação/grants/expiração/versões sob lock. Qualquer mudança no payload, efeitos, dependências ou policy invalida o aceite; não executar a versão antiga sobre um estado novo. Retry após sucesso retorna o resultado com approval já consumida, sem reutilizá-la. Concorrência entre executores só admite um consumo.

**DecisionApproval** é o fato gerencial gerado por ApproveDecision. Guarda Decision, revisão/conteúdo revisados, evidências, aprovador humano e Person correspondente, rationale e policy version. Não é um token para aprovar outro command nem o aceite de uma sugestão de agente. Approval de execução para CreateDecision não equivale a aprovação gerencial dessa Decision.

Approval gerencial stale impede seu uso sobre uma revisão nova; não apaga o snapshot aprovado nem revoga uma Decision já tomada. Invalidação é registro adicional/evento, não edição do fato histórico. A validade também depende de evidências, grants e policy atuais, não somente de Decision.version.

Como no `approve` normativo, ApproveDecision **não muda automaticamente** `proposed` para `decided`. Para declarar uma decisão tomada, UpdateObject pode fazer a transição protegida descrita na seção 4.2. Nunca criar `decision.status=approved`: esse valor não existe no Core 3.2.0.

### 3.4 Política inicial de aprovação

Baseline conservadora, anterior a qualquer autonomia: toda escrita solicitada por agente precisa de CommandApproval humana além de grant; comandos human-only continuam negados ao agente, mesmo com approval. Um futuro modelo de autonomia pode permitir execução de baixo risco sem revisão individual por política versionada; não está habilitado por este documento.

| Command         | Humano                                                                     | Agente futuro                                                      |
| --------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| CreateObject    | Sem approval extra para tipo ordinário; herda regra especializada          | CommandApproval obrigatória                                        |
| UpdateObject    | Sem approval extra para edição ordinária; guards abaixo                    | CommandApproval; transição de Decision para decided negada         |
| LinkObjects     | Sem approval extra para link ordinário; vínculos protegidos exigem revisão | CommandApproval; made_by negado                                    |
| UnlinkObjects   | Revisão humana distinta para vínculos protegidos                           | CommandApproval; remoção de approval/evidência de conclusão negada |
| CreateAction    | Sem approval extra; não executa trabalho externo                           | CommandApproval                                                    |
| CompleteAction  | Sem approval extra após validação da evidência                             | CommandApproval                                                    |
| RegisterRisk    | Sem approval extra para registrar risco identified                         | CommandApproval                                                    |
| CreateDecision  | Sem approval extra para proposta                                           | CommandApproval; não toma/aprova decisão                           |
| ApproveDecision | A própria operação é approval gerencial por context_approver               | Negado: human-only                                                 |
| AddEvidence     | Sem approval extra; anexar não confirma a alegação                         | CommandApproval                                                    |

Vínculos protegidos: mudança/remoção de `owned_by` e remoção de `requires_consultation`/`requires_notification` em Action ativa ou Decision proposed/decided exigem CommandApproval de humano autorizado distinto do solicitante. Criar owned_by inicial em criação composta não é transferência de responsabilidade. `made_by` e evidências que sustentam approvals/conclusão têm guards impeditivos, não uma aprovação genérica que os contorne. Esses guards também valem para effects indiretos dos wrappers.

## 4. Catálogo inicial

As sete dimensões de cada command são cumulativas com as regras comuns. Strings obrigatórias devem conter texto; datetime não pode ser futuro quando afirma ocorrência passada. Campos opcionais omitidos usam defaults normativos quando existentes. Null não é valor de propriedade.

### 4.1 CreateObject

- **Input:** `{object_type_id: UUID, title: string, content?: HTML, properties?: map<property_key, typed_value>}`. UUID, status inicial e defaults derivados são gerados/validados no servidor. Sem relações arbitrárias embutidas.
- **Validation:** tipo ativo do workspace; title após trim com 1–255 caracteres; HTML sanitizado; propriedades declaradas para o tipo, obrigatórias/defaults, enums e invariantes. Não aceitar propriedades de auditoria, score manual ou estado terminal no create. Tipo `action`, `risk` ou `decision` é normalizado para CreateAction, RegisterRisk ou CreateDecision, respectivamente, inclusive seus inputs obrigatórios/guards; payload insuficiente é rejeitado. Não criar instância especializada por uma rota menos restrita.
- **Permission:** `object.create` + manage_in_context + acesso ao tipo. Herda capacidades e restrições do tipo especializado.
- **Side effects:** Object com versão 1, PropertyValues explícitos/defaults e provenance atômicos. Identidade UUID e creator são imutáveis. Inicialização do schema é pré-requisito controlado, não um efeito que o agente possa usar para redefinir tipos.
- **Evento gerado:** `ObjectCreated {object_id, object_type_id, version: 1, property_keys}`. Para tipo especializado, também seu evento de domínio, sem duplicar ObjectCreated.
- **Provenance:** comum + tipo/schema utilizados, propriedades informadas versus defaults, assertion de origem e IDs criados.
- **Necessidade de approval:** humano ordinário não; agente sim; segue regra especializada quando aplicável. Criar proposta de Decision não registra DecisionApproval.

### 4.2 UpdateObject

- **Input:** `{object_id: UUID, changes: {title?: string, content?: HTML}, set_properties?: map<key, value>, remove_properties?: string[]}`. Pelo menos uma alteração; `expected_versions` inclui Object e referências necessárias. Uma chave não pode aparecer em set e remove.
- **Validation:** Object/tipo/definições ativos; mesmas validações de CreateObject; não remover campos obrigatórios ou derivados; sem troca de workspace, UUID, creator ou ObjectType neste contrato inicial. Alteração de tipo existente no spike fica desabilitada até contrato de migração específico. Patch validado sobre o estado final, não campo a campo com commits intermediários. likelihood/impact recalculam score atomicamente; due_date de Objective não precede start_date.
  - `action.status=done` e completed_at são exclusivos de CompleteAction. Cancelar/reabrir ações e aceitar/fechar riscos ficam fora deste catálogo inicial; não usar UpdateObject para simular esses workflows.
  - Decision proposed → decided exige executor humano, manage_in_context + context_approver, DecisionApproval válida da revisão imediatamente anterior e conteúdo aprovado intacto. `decided_at` é timestamp do servidor no mesmo commit, não input livre. ApproveDecision grava a revisão revisada e a revisão resultante; a approval cobre essa revisão resultante **somente para a transição sem edição concomitante**. A transição aponta para a approval e seu snapshot no histórico; não reutiliza a approval para outra tomada de decisão.
  - Não alterar contexto/escolha/rationale/consequences de Decision decided; nova escolha deve ser nova Decision. Revogar/substituir é workflow futuro. Edição de conteúdo ou evidências de Decision proposed após approval torna essa approval stale e exige revisão nova. Document usado em DecisionApproval ou conclusão preserva conteúdo/fonte: negar edição/remoção desses campos pelo patch; nova revisão documental exige workflow específico. Não substituir evidencia imutável por edição do Object genérico.
  - Allowlist inicial de status ordinários: Objective/Project draft → active e active ↔ on_hold; Action todo → in_progress e in_progress ↔ waiting; Risk identified → monitoring e monitoring ↔ mitigating; Document draft → active; Person active ↔ inactive. Transição de Decision segue o guard anterior. Outras transições são negadas neste catálogo; enum válido, sozinho, não autoriza transição. State igual é noop. Mudança de status gerencial não equivale a desativar/excluir ObjectType.
- **Permission:** `object.update` + manage_in_context + acesso aos campos; mudanças de estado herdam suas restrições. Propriedades não são uma via alternativa para alterar campos protegidos.
- **Side effects:** title/content/PropertyValues no mesmo commit; soft delete dos valores removidos; um incremento de versão por Object; score derivado e invalidação de DecisionApproval aplicável. Patch equivalente retorna noop.
- **Evento gerado:** `ObjectUpdated {object_id, changed_fields, property_keys_set, property_keys_removed, derived_keys, before_version, after_version}`; transição para decided também `DecisionTaken {decision_id, decision_approval_id, decided_at}`. Invalidação efetiva emite `DecisionApprovalInvalidated`.
- **Provenance:** comum + diff por campo, valor explícito/derivado, revisões e aprovação gerencial usada ou invalidada. Reason não substitui justificativa da escolha.
- **Necessidade de approval:** humano ordinário não; agente sim. DecisionTaken exige approval gerencial e execução humana; não aceitar agent com token humano para contornar human-only.

### 4.3 LinkObjects

- **Input:** `{source_id: UUID, relation_type_id: UUID, target_id: UUID}`; revisão esperada dos dois endpoints, uma entrada para self-link.
- **Validation:** Objects e RelationType ativos do mesmo workspace; domain/codomain, allowed_pairs, cardinalidade de ambos os lados quando declarada, self-link e regras do tipo. Uma aresta canônica; inverso é leitura. `creates` permite Decision→Action, não Decision→Risk; exigir Decision decided no vínculo que origina Action. `made_by` só é produzido por ApproveDecision; `verifies` isolado não conclui Action. `supersedes` fica indisponível até workflow que trate ambas as Decisions atomicamente. Relacionar por `relates_to` não satisfaz obrigações de um vínculo específico.
- **Permission:** `relation.link` + manage_in_context + acesso aos dois endpoints e ao tipo; guards especializados também se aplicam a links solicitados isoladamente.
- **Side effects:** cria Relation e provenance; versiona os dois endpoints. Duplicata ativa retorna noop e identidade existente. Mudanças no conjunto de evidências/consulta de Decision invalidam approvals da revisão anterior.
- **Evento gerado:** `ObjectLinked {relation_id, relation_type_id, source_id, target_id, endpoint_versions}`; `DecisionApprovalInvalidated` se necessário.
- **Provenance:** comum + direção canônica, tipo/schema, endpoints/revisões e natureza asserted/observed/inferred da relação. Não duplicar provenance para backlink.
- **Necessidade de approval:** humano ordinário não; agente sim. Transferência de owned_by precisa de revisão distinta; remover e criar em dois commands não elimina esse requisito. made_by human-only pela operação de aprovação, não por LinkObjects.

### 4.4 UnlinkObjects

- **Input:** `{relation_id: UUID}`; revisões esperadas dos endpoints. Reason obrigatório identifica por que o vínculo deixou de valer.
- **Validation:** resolver Relation, inclusive tombstone conhecido, dentro do workspace; endpoints/versões válidos. Não remover vínculo que deixe cardinalidade mínima inválida. Negar remoção de made_by que registra DecisionApproval ou de verifies usado em Action done. Negar remoção de evidência que sustente uma Decision decided. Correção/revogação desses fatos depende de workflow futuro; não apagar histórico nem fingir que a conclusão/aprovação nunca ocorreu.
- **Permission:** `relation.unlink` + manage_in_context + acesso aos endpoints; remover vínculo não concede poder de aprovar ou revogar decisão.
- **Side effects:** soft delete com remover explícito; preservar creator e tombstone; versionar ambos os endpoints. Recriação futura recebe nova identidade. Alteração permitida de evidências de Decision proposed invalida a approval anterior.
- **Evento gerado:** `ObjectUnlinked {relation_id, relation_type_id, source_id, target_id, removed_at, endpoint_versions}`; `DecisionApprovalInvalidated` quando aplicável.
- **Provenance:** comum + snapshot do vínculo removido, criador original, motivo, autor da remoção e IDs de approvals invalidadas.
- **Necessidade de approval:** humano ordinário não; remoção de owned_by/obrigações protegidas exige revisão distinta. Agente precisa CommandApproval e permanece proibido de remover evidência de conclusão ou registro gerencial de approval.

### 4.5 CreateAction

- **Input:** `{title: string, description: string, next_step?: string, priority?: enum, due_date?: date, origin_decision_id?: UUID, owner_person_id?: UUID, executor_person_ids?: UUID[], mitigates_risk_ids?: UUID[]}`. Sem completed_at/status de conclusão.
- **Validation:** tipo action ativo; title/description não vazios, propriedades tipadas e priority do vocabulário. Status inicial todo. Se origin_decision_id informado, deve ser Decision decided: aplicar a precondição do `create_action` normativo. Sem origem, permite Action independente como criação tipada. Pessoas ativas do domínio, riscos existentes e todos no scope; validators de creates/owned_by/assigned_to/mitigates. Owner não equivale a executor; atribuição proposta não prova aceite. Ausência de owner gera finding RADAR-M001.
- **Permission:** `action.create` + object.create + manage_in_context; acesso a referências e relation.link para cada relação embutida. Não exigir User correspondente ao owner nem inferir permission dele.
- **Side effects:** cria Object action, propriedades/defaults e, se informadas, Decision creates Action, Action owned_by Person, assigned_to Persons e mitigates Risks; tudo atômico. Object novo fica em versão 1; endpoints existentes alterados incrementam uma vez. Não inicia execução nem agenda integração externa.
- **Evento gerado:** `ObjectCreated`, `ActionCreated {action_id, origin_decision_id?, initial_status: todo}` e `ObjectLinked` por vínculo novo.
- **Provenance:** comum + compromisso descrito, origem da ação, owner/executores propostos, riscos e defaults. Preservar proposta de agente separada da autoria gerencial da Decision.
- **Necessidade de approval:** humano não para criação ordinária; agente sim na baseline. Policy futura pode liberar criação de baixo risco, sem liberar transferência de owner ou execução externa.

### 4.6 CompleteAction

- **Input:** `{action_id: UUID, outcome: string, evidence_id: UUID}`. evidence_id referencia Document já persistido; adicionar primeiro por AddEvidence. Revisões esperadas da Action e do Document.
- **Validation:** tipo action; transição todo/in_progress/waiting → done; cancelled não pode ser concluída; outcome não vazio e evidência legível/ativa do workspace com conteúdo ou referência de fonte. Aplicar action_closure_requires_evidence. A presença de Document/link não comprova sucesso: executor/revisor assume a alegação e sua provenance. Aprovar evidência inferida não a reclassifica como observada. Guard de dependências, se configurado, usa versões e resultado verificável; sem configuração, não inventar regra impeditiva. Nova intenção sobre Action já done não sobrescreve a conclusão; retry da original retorna resultado anterior.
- **Permission:** `action.complete` + manage_in_context + acesso à Action/Document e relation.link para verifies. Ownership é contexto de responsabilidade; restrição a owner/executor só vale se declarada pela policy.
- **Side effects:** grava status done e completed_at do servidor; resultado/evidência ficam em registro imutável de conclusão, não em propriedade inventada no schema. Cria Document verifies Action se ausente. Action incrementa uma vez; Document somente se nova relação. Não conclui Project/Objective/Risk automaticamente.
- **Evento gerado:** `ActionCompleted {action_id, completion_id, evidence_id, completed_at, before_status, after_status: done}` e `ObjectLinked` se verifies novo. Não emitir ObjectUpdated duplicado para a mesma transição.
- **Provenance:** comum + outcome, evidência/revisão usada, assertion do resultado, estado anterior e executor/aprovador. Timestamp observado da fonte, se houver, é metadado distinto de completed_at.
- **Necessidade de approval:** humano não além das regras; agente sempre exige CommandApproval humana sobre outcome, evidência e revisão. Nenhuma aprovação dispensa evidência.

### 4.7 RegisterRisk

- **Input:** `{title: string, description: string, likelihood?: integer, impact?: integer, response_strategy?: enum, review_date?: date, threatens_object_ids?: UUID[], owner_person_id?: UUID}`.
- **Validation:** tipo risk; descrição do evento incerto não vazia; status inicial identified; likelihood/impact inteiros de 1 a 5, default 3; score calculado como produto, default 9, sem input manual. response_strategy no vocabulário, default reduce. threatens somente Objective/Project conforme schema; Pessoa ativa para owner. Sem deduplicação por similaridade textual: mesmo evento/contexto pode gerar finding de duplicata para revisão, nunca merge silencioso.
- **Permission:** `risk.register` + object.create + manage_in_context; acesso e relation.link para todas as referências.
- **Side effects:** cria Object risk, propriedades/defaults, score derivado, owned_by e threatens informados; atomicidade e versões como CreateAction. Registrar não significa aceitar o risco, fechar o risco ou iniciar mitigação.
- **Evento gerado:** `ObjectCreated`, `RiskRegistered {risk_id, likelihood, impact, score, initial_status: identified}` e `ObjectLinked` para vínculos novos.
- **Provenance:** comum + fatores explícitos/defaults, fórmula/schema do score, contexto ameaçado e fontes. Risco inferido por agente continua hipótese identificada, mesmo após revisão humana.
- **Necessidade de approval:** humano não para registro; agente sim. Aceitação/fechamento do risco não estão liberados por RegisterRisk ou pelo patch genérico.

### 4.8 CreateDecision

- **Input:** `{title: string, context: string, decision: string, rationale: string, consequences?: string[], project_id?: UUID, evidence_ids?: UUID[], consultation_person_ids?: UUID[], notification_person_ids?: UUID[]}`.
- **Validation:** tipo decision; context, escolha proposta e rationale não vazios; consequences tipada; status inicial proposed, sem decided_at. project_id é Object project RADAR, ligado por Project contains Decision. Evidências são Document; vínculo Decision informed_by Document. Consulta/notificação usam requires_consultation/requires_notification: obrigação declarada, não prova de realização. Não criar Decision affects Project nem creates Risk por aliases incompatíveis com Core.
- **Permission:** `decision.create` + object.create + manage_in_context; acesso a referências e relation.link para efeitos embutidos. Poder propor não dá context_approver.
- **Side effects:** Object decision, propriedades/defaults e relações informadas no mesmo commit. Não criar made_by, DecisionApproval, Action automática ou fato de decisão tomada. Ausência de evidência pode permitir proposta; revisão gerencial exige evidência antes de approve.
- **Evento gerado:** `ObjectCreated`, `DecisionCreated {decision_id, initial_status: proposed}` e `ObjectLinked` por relação nova.
- **Provenance:** comum + contexto/escolha/rationale propostos, consequências, evidências e origem humana/agente. Registrar quem propôs, separado de quem tomou/aprovou.
- **Necessidade de approval:** humano não para proposta; agente sim para persistir. A proposta persistida não está aprovada: ApproveDecision é operação separada.

### 4.9 ApproveDecision

- **Input:** `{decision_id: UUID, rationale: string, approver_person_id: UUID}`; expected_versions inclui Decision, Person e Documents informados como fundamentos da aprovação. Rationale da revisão é distinta da rationale da escolha.
- **Validation:** Decision proposed ou decided, nunca superseded/revoked; escolha/contexto/rationale completos e ao menos um Document informed_by ativo com fonte/conteúdo. Resolver o conjunto integral de fundamentos e exigir suas revisões. Person ativa deve ter vínculo verificado com o User humano autenticado; Person não é identidade de segurança por nome/e-mail enviado. Sem mapeamento confiável, negar approval. Aprovador precisa ser distinto do autor da proposta/alteração revisada; falta de outro aprovador mantém pendência, sem exceção implícita para admin. Approval repetida pelo mesmo humano do mesmo snapshot retorna noop; aprovação por outra autoridade gera registro próprio.
- **Permission:** `decision.approve` + approve_in_context; human-only e context_approver explicitamente configurado. Nenhum grant de agente, run ou CommandApproval transforma agente em aprovador humano. Relação made_by isolada não comprova autoridade.
- **Side effects:** cria DecisionApproval imutável vinculada ao snapshot e evidências revisados; cria Decision made_by Person se ausente; Decision incrementa uma vez e Person apenas se a relação for nova. Guarda reviewed_version/hash e resulting_version para o guard de tomada de decisão. **Não muda status nem decided_at**, em conformidade com `approve.transitions={}`. Para proposed → decided, usar UpdateObject com o guard da seção 4.2; se Decision já decided, registra ratificação do snapshot sem reescrever a escolha.
- **Evento gerado:** `DecisionApproved {decision_id, decision_approval_id, reviewed_version, resulting_version, approver_actor_id, approver_person_id, evidence_ids}` e `ObjectLinked` se made_by novo.
- **Provenance:** comum + autoridade/policy, separação de funções, escolha/evidências revisadas, rationale humano, reviewed/resulting version e IDs de aprovação. Conservar autoria do proponente; made_by é relação do domínio, não substituto de Actor.
- **Necessidade de approval:** é o ato humano de approval gerencial; não exige uma recursão de approvals sobre approvals. Em política futura com quórum, cada voto é fato separado e só o quórum libera a tomada de decisão. Baseline: um context_approver distinto do autor. Agente pode preparar sugestão de revisão, mas não executar ApproveDecision.

### 4.10 AddEvidence

- **Input:** `{target_id: UUID, document: {existing_id: UUID} | {title: string, content?: HTML, document_type?: enum, summary?: string, uri?: URI, source_system: string}, relation_key: verifies | informed_by | evidences, observed_at?: datetime, content_hash?: string}`. União exclusiva: referenciar documento existente ou criar novo. Source_system obrigatório identifica origem; observed_at/hash são metadados de evidence/provenance, não propriedades novas implícitas de Document.
- **Validation:** Document é Object document, não tipo Evidence; exige tipo e RelationTypes ativados por snapshot compatível. Documento novo deve ter conteúdo não vazio após sanitização ou URI válida; existente também precisa conteúdo/fonte. Não confundir URI sintaticamente válida com conteúdo externo verificado. URI apenas é registrada, sem fetch/upload nesse command. Se hash fornecido para conteúdo local, validar contra bytes normalizados; para referência externa, registrar como alegado até verificação específica. observed_at tem timezone e não pode ser futuro.
  - Direction/pairs: Document **verifies** Action; Decision **informed_by** Document; Document **evidences** ManagementItem/Case/Indicator. Não usar evidences para Action, Risk, Objective ou Project, nem inventar domínio universal. Alvo não suportado retorna rule_violation/unsupported_schema; apoio a outros tipos exige extensão normativa versionada.
  - Documento/relação não podem ser editados/reutilizados para alterar silenciosamente evidence já referenciada em conclusão/approval. Alteração de linhagem/conteúdo é versão nova com identidade/rastreabilidade de revisão. Este command é aditivo, não substitui evidência anterior.
- **Permission:** `evidence.add` + manage_in_context + acesso ao target/Document, object.create quando novo e relation.link para o vínculo. Leitura do documento/fonte continua sujeita ao scope; possuir URI não concede acesso ao conteúdo.
- **Side effects:** cria/reusa Document e cria vínculo canônico atomicamente; novo Document versão 1; endpoints existentes alterados incrementam uma vez. Materializa propriedades normativas de Document. Invalida approval de Decision proposed se fundamento mudou. Não conclui Action, aprova Decision, verifica autenticidade externa ou cria attachment do Plane.
- **Evento gerado:** `EvidenceAdded {target_id, document_id, relation_id, relation_key, created_document, observed_at?, content_hash?}`; `ObjectCreated` quando documento novo, `ObjectLinked` quando vínculo novo e `DecisionApprovalInvalidated` se aplicável. Documento/vínculo já associados sem novo metadado retornam noop.
- **Provenance:** comum + autor da anexação separado do autor/fonte do documento, URI/source_system, conteúdo/revisão/hash quando verificável, momento observado versus registrado e assertion da alegação apoiada. Evidência apresentada pelo agente preserva run/proposta e revisor.
- **Necessidade de approval:** humano não para anexar; agente sim para persistir. Aceite não valida automaticamente fonte, conclusão ou decisão. Remover evidência é outro workflow, fora do catálogo inicial.

## 5. Fechamento dos caminhos alternativos

Todos os pontos de escrita existentes convergem para esse contrato: views, commands semânticos, scripts de cenário/importação, jobs e futuros adaptadores. `_authorize`, sanitização, validação de propriedades, guards de status/relações e approval não podem existir somente no endpoint ou wrapper especializado.

Primitivas internas recebem contexto validado e plano de efeitos do handler; não são ferramentas expostas ao agente. CreateObject especializado aplica as mesmas regras, set_property_value não conclui Action, create_relation não fabrica made_by e remove_relation não apaga evidencia de um fato terminal. Não expor hard delete, escrita livre de schema, SQL/ORM, troca de tipo ou alterações arbitrárias de auditoria como commands.

A fronteira de aplicação não é isolamento contra Python confiável com acesso ao banco. Reduzir bypasses exige revisar todos os writers e restringir credenciais operacionais; não afirmar que os models atuais já impedem toda escrita fora de commands.

## 6. Fluxos verificáveis e critérios de implementação

**Humano:** CreateDecision(proposed) → AddEvidence(informed_by) → ApproveDecision por outro humano autorizado → UpdateObject(status=decided, sem edição concomitante) → CreateAction(origin_decision_id) → AddEvidence(verifies) → CompleteAction. Cada passo usa revisão atual, chave própria e retorna provenance/eventos. ApproveDecision mantém proposed até a tomada explícita; decided não dispara execução externa.

**Agente futuro:** prepara LinkObjects(Risk threatens Objective) → validadores/permissões calculam efeitos → pending_approval, sem relação de domínio → humano aceita snapshot exato → executor retoma o mesmo LinkObjects → commit da Relation, provenance com agente + humano e evento. Se qualquer endpoint mudou, approval_stale/revision_conflict; renovar proposta/aceite, sem aplicação automática.

**Edição de proposta:** humano muda alvo, texto ou evidência → nova revisão/hash/chave → novas validações e approval quando exigida. **Rejeição:** registrar feedback/auditoria, sem write. Nenhum desses fluxos requer runtime Deep Agents para testar a camada.

A suíte valida os fluxos com unit tests e testes transacionais na stack Django/PostgreSQL existente:

| Caso                                                                            | Resultado esperado                                                                |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Humano e principal agente futuro enviam a mesma intenção                        | Mesmas regras de domínio/efeitos; policy explica diferença de permission/approval |
| guest/non-member ou referência cross-workspace                                  | Negado sem write, publicação ou vazamento de identidade                           |
| Actor/source/approval boolean falsificados                                      | Rejeição; identidade e aprovação obtidas do contexto persistido                   |
| CreateObject(action) incompleto; patch done; link made_by                       | Mesmo guard especializado; sem bypass                                             |
| Score 4 × 5; data inválida; Decision creates Risk                               | Score 20 atômico; data e par inválidos rejeitados                                 |
| Retry e execução concorrente com mesma chave                                    | Um commit e um conjunto de eventos; mesma resposta/IDs                            |
| Mesma chave com payload diferente; expected_version stale                       | Conflict, sem mutação parcial                                                     |
| Composição falha no último link/propriedade/outbox                              | Rollback de todos os efeitos, resultados e eventos de domínio                     |
| Approval expirou, grant revogado, evidence/policy mudou                         | Não executar; trilha de motivo e necessidade de nova revisão                      |
| Dois executores consomem a mesma approval                                       | Um consumo/commit; outro replay ou conflito                                       |
| Agente tenta ApproveDecision, inclusive com approval_id                         | Negado human-only                                                                 |
| Humano sem context_approver, Person falsa ou autor revisando a própria proposta | Approval gerencial negada                                                         |
| DecisionApproved e transição protected decided                                  | Status inalterado no approve; transição só da revisão aprovada, com DecisionTaken |
| CompleteAction sem evidência; Unlink de verifies usado em done                  | Rejeição sem alterar conclusão/histórico                                          |
| Evidência inferida aceita                                                       | Origem/confidence preservadas; nenhum fato externo alegado como verificado        |
| Falha de consumidor após commit ou entrega duplicada                            | Command continua confirmado; projeção idempotente/reprocessável                   |

## 7. Uso e operação

Entrada Python compartilhada: `execute_command(actor=Actor(...), workspace=workspace, envelope=payload)`. O Actor vem da autenticação do adaptador; o payload não pode declarar a identidade do executor. Adaptadores não humanos precisam autenticar o principal registrado antes de chamar essa função. Nenhum endpoint de sessão aceita impersonação de agente.

Os endpoints ficam sob `/api/workspaces/{slug}/radar/`:

| Endpoint                              | Uso                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------- |
| `POST commands/`                      | Executar qualquer um dos dez comandos com o envelope comum                            |
| `GET commands/{command_id}/`          | Consultar intenção, hash, Actor e prévia/resultado                                    |
| `POST commands/{command_id}/review/`  | Humano revisa com `{intent_hash, approve, rationale}`                                 |
| `POST actor-grants/`                  | Owner/admin configura tipo, principal, delegante, comandos, tipos e campos permitidos |
| `POST person-identities/`             | Owner/admin verifica User↔Person e can_approve                                        |
| `GET objects/{object_id}/provenance/` | Consultar diffs e todos os campos mínimos de autoria                                  |

As rotas legadas de objects/properties/relations também chamam o dispatcher e exigem `Idempotency-Key` e `X-Radar-Expected-Versions` (JSON UUID→versão). O frontend envia o snapshot carregado e trata 202 como pendência, sem atualizar seu cache como se o domínio tivesse sido alterado. Chamadores Python legados podem obter a revisão corrente sob lock pela fachada; novos adaptadores devem enviar a revisão explícita.

Exemplo de envelope sem referências existentes:

```json
{
  "command_name": "RegisterRisk",
  "command_version": 1,
  "idempotency_key": "risk-licensing-001",
  "expected_versions": {},
  "reason": "Registrar hipótese de atraso",
  "assertion": { "kind": "asserted", "evidence_ids": [] },
  "input": { "title": "Licenciamento atrasado", "description": "Contrato pode atrasar", "likelihood": 4, "impact": 5 }
}
```

A revisão aceita o hash consultado, sem aplicar mudanças no domínio. Para executar, o principal original reenvia a mesma intenção/chave com approval_id. A prévia usa IDs simbólicos `$new:...`, pois a simulação foi revertida. Mudanças no schema/defaults, revisões de referências ou versão do grant impedem o consumo. O lock de workspace serializa comandos, grants e inicialização de schema dentro da aplicação; depois disso, Objects são travados em ordem UUID. A serialização conservadora pode ser refinada futuramente conforme volume.

A migration `0003_commandexecution_provenance_personidentity_and_more` adiciona os registros de controle, grants, identidades, conclusão, evidence metadata, provenance, outbox e referências nos models existentes. Não faz backfill de autoria anterior: registros antigos mantêm provenance nula até a próxima mutação. Aplicar com o procedimento Django habitual (`python manage.py migrate`) antes de usar os novos endpoints.

O cenário de demonstração agora deixa a Decision em proposed e contém a Action pelo Project; não fabrica decisão tomada nem approval para montar a fixture. Para obter uma Decision decided, executar o fluxo humano da seção 6.

Validação: `pytest plane/radar/tests -q` na stack `docker-compose-test.yml`; frontend com `pnpm --filter web test:radar` e `pnpm --filter web check:types`. A suíte cobre todos os comandos, atores, grants, replay, concorrência, alterações de schema, revisões, aprovação, evidências, rollback de outbox, provenance e os adaptadores de API/UI. Resultado em 04/10/2026: 149 testes de backend e 49 de frontend aprovados; tipos TypeScript, Ruff, OxLint, check Django e ausência de migrations pendentes aprovados. As migrations reais, incluindo 0003, foram aplicadas no PostgreSQL isolado dos testes.

Limites da entrega original 1.1/1.2: não incluía runtime Deep Agents nem autenticação de transporte não humano, entregues posteriormente na integração e em 1.3. Permanecem pendentes interface de revisão de approvals, publisher/consumidores da outbox, engine genérica de metodologia/RBAC, auditoria durável de tentativas inválidas, comunicação externa e deploy. A interface Python compartilhada e as policies para os quatro tipos de Actor estão implementadas e testáveis sem integrar um agente.

## Extensão do catálogo para o CoS

Os comandos abaixo usam o mesmo envelope, dispatcher e provenance dos dez comandos iniciais. `context` é um contexto gerencial explícito; no transporte CoS ele vem do vínculo autenticado. IDs no envelope comum são UUIDs; o port CoS traduz IDs canônicos antes de invocar o dispatcher.

| Comando             | Input                                                                                                  | Validation                                                                                                       | Permission                                                                          | Side effects e evento                                                                                      | Provenance e approval                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `CaptureIssue`      | context, title, case_title, evidence_title, source; priority/owner_id opcionais                        | Schema estrito; vocabulário de prioridade; Person ativa e vinculada ao contexto; fonte CoS autenticada           | Humano writer ou agente com grant de todos os tipos/campos e relações compostas     | Case + ManagementItem issue + Document; contains/evidences/owned_by; `IssueCaptured`                       | Actor e fonte originais, três identidades e diffs no mesmo commit; agente requer approval                 |
| `DelegateAction`    | context, action_id, executor_id ou executor_ids, due_at; next_review_at opcional                       | Action ativa; executores ativos; revisão até o prazo; versões de owner, atribuições e compromissos anteriores    | Owner vinculado a PersonIdentity ou gerente do contexto; grant completo para agente | Substitui assigned_to; supersede compromissos confirmed; assignment proposed sem aceite; `ActionDelegated` | Provenance dos vínculos, termos e compromissos; humano revisor separado do agente; agente requer approval |
| `ReviewObject`      | context, target_id, assessment, evidence_id; next_review_at/disposition opcionais                      | Document válido; tipo/status compatíveis com a disposição; revisão retrospectiva sem disposição                  | Humano writer ou agente com grant e acesso a todas as referências                   | Histórico de revisão; resolved encerra item/risco, accepted aceita risco; `ObjectReviewed`                 | Fonte, assessment e evidência versionada no histórico; agente requer approval                             |
| `RecordMeasurement` | context, indicator_id, value, measured_at; evidence_id ou evidence_title/evidence_source/evidence_text | Indicator ativo; número finito; data sem futuro e posterior à observação anterior; uma única origem de evidência | Humano writer ou agente com grant; criação inline exige escopo de contexto completo | Atualiza current/measured_at; evidence link e histórico; `MeasurementRecorded`                             | Actor, fonte/hash da evidência e instante observado; agente requer approval                               |

O port autenticado oferece preparação para o catálogo comum. Ele persiste a pendência e o mapa completo de versões sem commit de domínio. `resolve` revisa/retoma exclusivamente o envelope salvo e não aceita parâmetros substitutos. O CoS conserva o recibo em seu ledger; replay evita efeitos duplicados. Detalhes de políticas, provisionamento, versões e testes: [COS_INTEGRATION](./COS_INTEGRATION.md).
