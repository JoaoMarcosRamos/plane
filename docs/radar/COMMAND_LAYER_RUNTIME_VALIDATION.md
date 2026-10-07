# Relatório de compatibilidade — Command Layer e JMR_Personal-CoS

**Destino atual:** a implementação posterior pertence a `COS_AGENT_V2`. Os caminhos para `JMR_Personal-CoS` abaixo documentam a comparação histórica anterior à integração.

**Referência histórica:** este relatório descreve a comparação anterior ao adapter. A implementação posterior e os limites homologados estão em [COS_INTEGRATION.md](./COS_INTEGRATION.md); os achados abaixo preservam a evidência do estado original.

Data: 04/10/2026. **Resultado: alinhamento arquitetural parcial; integração direta não homologada.** A camada Django atende ao catálogo local, mas não substitui o runtime que o CoS usa hoje. O Core é idêntico; contratos de execução, operações publicadas, identidades e políticas de aplicação diferem.

Esta análise não altera código de aplicação, não integra Deep Agents e não opera a VPS, Telegram ou ABox real. As únicas escritas de domínio desta validação ocorreram em vaults temporários e bancos SQLite dos testes do CoS.

## 1. Base verificada

| Componente | Versão/estado examinado |
| --- | --- |
| `JMR_Personal-CoS` | HEAD `471ddd86358ffcdd80ae61ccfff867876835dd06`; checkout limpo antes/depois da validação |
| Dependência instalada e fixada | `radar-vault 0.5.0`, commit `5f8526425def048804c6a3836d2aaf861f71a49e` |
| Ontologia | Core `3.2.0`; SHA-256 `8ea1a14a17c25ff1e6a4945bf75f51982b7ce2243b3509df18a5f74a3bfd6ab7` em ambos |
| Command Layer | Arquivos atuais do workspace Plane; dez comandos e subconjunto de sete Object Types |
| Testes executados nesta revisão | 33 testes existentes do CoS; probes adicionais com o pacote instalado e vault descartável |
| Testes anteriores da implementação Django | 149 backend e 49 frontend; evidência da entrega anterior, não repetidos nesta revisão documental |

Fontes: [dependência fixada](../../../JMR_Personal-CoS/requirements.txt), [adapter do pacote](../../../JMR_Personal-CoS/app/integrations/radar_vault.py), [runtime normativo](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/runtime.py), [contrato Django](./COMMAND_LAYER.md). O checkout de `JMR_RADAR_ONTOLOGY` está no mesmo commit do pacote instalado; suas fontes são referências para esta versão, não uma especificação de versões futuras.

A API de threads do marco M10, em `app/api/radar.py`, é outra superfície: seu agente sintético é construído sem tools. Ela não é o adapter do vault nem uma API de execução dos dez comandos. O caminho operacional examinado é `Telegram → tools de proposta → RadarService → RadarAgentTools → OperationRuntime`.

## 2. Achados que bloqueiam uma ligação direta

Prioridade P1 significa bloqueio para substituir/conectar o runtime atual; não significa que o sistema já conectado esteja falhando, pois essa integração ainda não existe.

### V1 — P1: as quatro escritas publicadas pelo CoS não têm equivalente semântico no catálogo

O CoS publica, conforme configuração e capacidade do pacote, `capture_issue`, `delegate`, `review` e `record_measurement`. Nenhuma está implementada como operação equivalente nos dez comandos Django.

| Operação do CoS | Efeitos que precisam ser preservados | Lacuna no Plane |
| --- | --- | --- |
| `capture_issue` | Case + Issue/ManagementItem + Evidence, vínculos e fonte autenticada; prioridade/responsável no Issue | `case` e `management_item` estão fora do snapshot; `CreateObject`/`AddEvidence` não compõem essa captura |
| `delegate` | Verifica owner/context manager; substitui atribuições, registra termos propostos e invalida compromissos anteriores | `LinkObjects(assigned_to)` não registra termos, prazo/revisão, aceites nem compromisso; não é delegação equivalente |
| `review` | Registra assessment/evidência e revisão; algumas disposições encerram item ou aceitam/fecham risco | Não equivale a `ApproveDecision`, `AddEvidence` ou patch livre; faltam o registro de revisão e essas transições |
| `record_measurement` | Atualiza Indicator, registra medição/evidência e verifica ordem temporal | `indicator` está fora do snapshot; `UpdateObject` não fornece esse workflow |

O gate `supports_write_operation()` verifica explicitamente `prepare`, definitions, parâmetros e targets. Conectar o dispatcher atual a esse gate não publicará as operações. Traduzir nomes para CRUD genérico perderia regras e efeitos.

Evidências: [gate e execução do service](../../../JMR_Personal-CoS/app/services/radar_service.py), [tools publicadas](../../../JMR_Personal-CoS/app/tools/radar.py), [políticas do runtime](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/policies.py), [catálogo Django](../../apps/api/plane/radar/commands/inputs.py), [subconjunto da ontologia](../../apps/api/plane/radar/ontology/snapshot.py).

### V2 — P1: principal, namespace de entidades, contexto e revisões não são intercambiáveis

| Dado | CoS / radar-vault | Django |
| --- | --- | --- |
| Principal | `telegram:42`, Person `PER-...` | `Actor.actor_id` UUID; humano exige User ativo/membership, não humano exige ActorGrant |
| Contexto | `company:...` ou `manager:...`, `read_contexts`/grants por contexto | Workspace UUID e membership |
| Entidade | ID como `ACT-20260912-ABC123` | UUID de Object; tipos e relações também têm UUID |
| Revisão | `expected_revision` do alvo; criação começa em `0` | `expected_versions` de todas as referências; criação começa em `1` |
| Acesso | Contexto e, quando configurado, `Principal.object_ids`; policies por operação | Workspace + escopo de comando/tipo/campos; sem equivalente direto de `object_ids` |
| Persistência | ABox Markdown e `.radar` | PostgreSQL |

É necessário um vínculo persistido de identidades e contexto, preservando os IDs externos. Não converter `telegram:42` em um humano Django por convenção nem associar entidades por título. Não assumir `version = revision + 1`: os dois runtimes alteram conjuntos diferentes de objetos em alguns efeitos.

As revisões de **todas** as referências precisam ser fixadas na preparação. Consultar versões atuais no instante do “sim” esconderia mudanças ocorridas depois da revisão humana. O payload salvo hoje no CoS só contém a revisão do alvo.

Evidências: [build_principal](../../../JMR_Personal-CoS/app/integrations/radar_vault.py), [Principal](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/policies.py), [OperationRequest e revisões](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/runtime.py), [Actor/validação/revisões Django](../../apps/api/plane/radar/commands/execution.py).

### V3 — P1: a aprovação atual do CoS não é uma CommandApproval Django

No CoS, a tool chama `prepare_operation` sem executar, persiste `pending_radar_operations`, devolve `approval_required` e encerra a rodada. O “sim” faz claim single-use por thread/usuário e chama `execute_saved_operation` com o payload/chave salvos, sem invocar o modelo. O service constrói um Principal com `is_agent=False` para esse caminho.

No Django, a execução por agente exige `ActorGrant`, cria uma pendência local, requer `review_command` humano com o hash e depois consome o `approval_id` local na execução pelo principal original. `execute_command` de humano pode executar imediatamente; não serve como uma API genérica de preparação sem efeitos para o CoS.

O `proposal_id` Django também não aceita um UUID externo arbitrário: ele representa takeover humano de um CommandExecution agente rejeitado no mesmo workspace. Não reutilizar esse campo para a proposta do CoS sem um contrato específico.

O adapter deve persistir o vínculo proposta CoS ↔ command/approval Django, o Actor original, o hash e o snapshot. A confirmação Telegram deverá revisar a pendência correspondente e retomar a mesma intenção, conservando a origem agente e registrando o humano revisor. Recusa, expiração, mudança de policy e conflito precisam encerrar a intenção sem rebase. A atual API HTTP do Plane constrói apenas Actor humano de sessão; ainda não há transporte autenticado para esse principal de agente.

Evidências: [resolução Telegram](../../../JMR_Personal-CoS/app/application/telegram.py), [proposta/claim](../../../JMR_Personal-CoS/app/database/radar_operations.py), [Principal de escrita](../../../JMR_Personal-CoS/app/services/radar_service.py), [pendência/consumo Django](../../apps/api/plane/radar/commands/execution.py), [review_command](../../apps/api/plane/radar/commands/control.py), [Actor da API](../../apps/api/plane/radar/api/views.py).

### V4 — P1: o resultado Django é rejeitado pelo consumidor do CoS

O runtime devolve `status`, `code="ok"`, `target_id`, `revision`, `created_ids` de entidades canônicas e `operation_id`. O Django devolve `code=null` no sucesso, `command_id`, mapas de versões e `data`; `created_ids` inclui também registros auxiliares, como PropertyValues e Relations. `noop` e `pending_approval` não são estados aceitos pelo projetor de resultados de execução do CoS.

Provas executadas contra `_safe_result_projection` do CoS:

| Resultado representativo do contrato Django | Projeção atual do CoS |
| --- | --- |
| `executed`, `code=null`, IDs UUID | `failed / invalid_response` |
| Mesmo sucesso com apenas `code` convertido para `ok` | `failed / invalid_response` por formato dos IDs |
| `noop` | `failed / invalid_response` |
| `pending_approval` | `failed / invalid_response` |

Se um adapter apenas encaminhar o resultado, uma mutação confirmada poderá ser apresentada como falha. É preciso projetar resultados de domínio, separar IDs auxiliares, traduzir IDs/revisões/códigos e preservar o estado de pendência fora do caminho de sucesso.

Erros também diferem: Django lança exceções DRF/HTTP; o runtime retorna códigos seguros. O CoS só marca `uncertain` quando recebe `persistence_failure`. Uma perda de resposta após commit exige consulta/replay com a mesma chave, sem criar nova intenção nem afirmar rollback. O commit atômico PostgreSQL já protege o lado Django; não resolve sozinho a confirmação entre processos.

Evidências: [projetor e allowlist de erros](../../../JMR_Personal-CoS/app/services/radar_service.py), [finish/recovery](../../../JMR_Personal-CoS/app/database/radar_operations.py), [resultado Django](../../apps/api/plane/radar/commands/execution.py). Os resultados das provas locais estão registrados neste relatório, nas seções 2 e 6.

### V5 — P1: as informações atuais do CoS não preenchem o Actor exigido sem perda de origem

O CoS tem provenance de mensagem forte: update/chat/message, autor, timestamp e hash do texto autenticado. Para captura/medição, fonte e texto vêm da aplicação, nunca do modelo. Porém, o registro de proposta e a assinatura de execução não transportam `actor_type`, principal agente próprio, `run_id`, `correlation_id`, `approval_id` local ou `confidence` da assertion.

| Campo mínimo | Tradução necessária |
| --- | --- |
| `actor_type`, `actor_id` | Principal agente registrado no Plane; humano solicitante/revisor mantido separadamente. Não copiar `is_agent=False` para ocultar a origem da proposta |
| `timestamp` | Distinguir instante da mensagem, preparação, aprovação e registro; não substituir o timestamp histórico pela retomada |
| `reason` | Justificativa da intenção; não confundir com rationale/outcome/evidência de negócio |
| `source` | Origem autenticada CoS/Telegram e vínculo ao metadado de mensagem; não aceitar fonte inventada pelo modelo |
| `correlation_id` | Identificador estável escolhido pelo host, correlacionado com thread/proposta |
| `run_id` | Run originador persistido com a proposta. Faz parte do hash da intenção Django; usar um novo run no “sim” causaria `idempotency_conflict` |
| `approval_id` | ID da CommandApproval Django, vinculado à confirmação humana do CoS |
| `confidence` | Quando a assertion for inferida; o runtime atual não oferece esse campo. Não inventar confidence para preencher o contrato |

A provenance de seleção é uma garantia diferente da auditoria de mutações: o middleware do CoS exige busca unívoca, seleção humana por papel ou ID explicitamente informado pelo usuário. Não remover esse guard ao introduzir o dispatcher; acesso ao Object e approval não comprovam que o modelo escolheu a entidade pretendida.

Evidências: [fonte autenticada](../../../JMR_Personal-CoS/app/security/radar_provenance.py), [injeção pela tool](../../../JMR_Personal-CoS/app/tools/radar.py), [schema das propostas](../../../JMR_Personal-CoS/app/database/schema.py), [guard de seleção](../../../JMR_Personal-CoS/app/agent/middleware.py), [Actor Django](../../apps/api/plane/radar/commands/actor.py).

## 3. Comparação dos dez comandos com o pacote instalado

O pacote oferece 14 operações governadas. Ter o mesmo Core não significa que cada comando Django tenha a mesma semântica de uma dessas operações. As quatro operações publicadas pelo CoS são o subconjunto descrito em V1.

| Command Layer | Operação mais próxima no pacote | Resultado da comparação |
| --- | --- | --- |
| `CreateObject` | Sem operação genérica pública | `RadarAgentTools.create_entity` é recusado. O catálogo genérico exige uma nova decisão de exposição, mesmo com grants/approval |
| `UpdateObject` | Sem patch genérico público | `update_entity` é recusado; runtime usa operações específicas de domínio |
| `LinkObjects` | Efeito interno de operações | `link_entities` é recusado; uma atribuição não substitui `delegate` |
| `UnlinkObjects` | Efeito interno de operações | `unlink_entities` é recusado; não há contrato público equivalente |
| `CreateAction` | `create_action` | Parcial: runtime exige Decision decided como alvo, cria owned_by do Principal e contém em Cases derivados; Django permite Action independente, owner opcional e outros vínculos |
| `CompleteAction` | `close_action` | Próximo: ambos exigem outcome/evidência, criam verifies e passam a done com completed_at. Django restringe evidência a Document válido e grava conclusão imutável; runtime usa a interface Evidence e closure no operation_data |
| `RegisterRisk` | `register_risk` | Diferente: runtime exige Issue de origem, likelihood/impact e gera Issue creates Risk/Case contains Risk; Django permite registro independente com defaults e threatens Objective/Project |
| `CreateDecision` | `decide` | Diferente: runtime recebe Case + Evidence e já cria decided, addresses, contains e made_by do responsável. Django cria proposed e exige tomada posterior com approval válida |
| `ApproveDecision` | `approve` | Status preservado em ambos. Runtime registra approval em operation_data; Django exige PersonIdentity, evidências versionadas, autoridade distinta do autor e registro DecisionApproval próprio; também cria made_by |
| `AddEvidence` | Efeito composto de captura/medição/decisão/fechamento | Não existe uma operação pública genérica equivalente. Runtime Evidence é uma interface; o subconjunto Django oferece Document |

**V6 — P2: formalizar divergências de política antes de chamar esses comandos de equivalentes.** As restrições adicionais do Plane podem ser intencionais e já estão descritas no desenho local. Elas mudam casos aceitos pelo runtime e exigem uma policy de aplicação versionada. Um adapter de nomes não resolve essas diferenças.

As probes confirmaram no pacote real: `create_action` sem Decision é rejeitado; `decide` gera decided imediatamente; `approve` aceita a mesma autoridade que criou a decisão e mantém o status. Isso não implica que o CoS publique hoje `decide` ou `approve` ao agente: são capacidades do pacote examinadas para comparação.

Fontes: [handlers do pacote](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/runtime.py), [bloqueio de CRUD nas tools](../../../JMR_RADAR_ONTOLOGY/src/radar_vault/agent_tools.py), [handlers Django](../../apps/api/plane/radar/commands/handlers.py).

## 4. Garantias alinhadas e diferenças a preservar

| Tema | Avaliação |
| --- | --- |
| Origem normativa | Core, tipos/vocabulários compartilhados e hash idêntico; pacote também carrega rules/policies/action types completos, enquanto Django usa snapshot estrutural e handlers/policies locais |
| Fronteira determinística | Ambos validam e persistem fora do raciocínio do modelo; domínio testável sem LLM |
| Prévia | Runtime prepara em StagedVault sem alterar notas/audit/receipts, confirmado por probe. Django simula em savepoint e registra a pendência, sem commit de domínio |
| Aprovação | Ambos possuem payload salvo, validade, reautorização e consumo single-use; falta unir as duas máquinas de estado conforme V3 |
| Concorrência | Runtime usa lock/journal do vault e revisão do alvo; Django usa transação/locks PostgreSQL e versões das referências |
| Idempotência técnica | Ambos rejeitam mudança de intenção na mesma chave e evitam repetir efeitos no replay; confirmado no pacote por probe e previamente testado no Django |
| Deduplicação semântica | Já existe no CoS com fingerprint e override humano de uso único. Django só deduplica pela chave; não elimina a necessidade de preservar a proteção conversacional do host |
| Auditoria de falhas | Runtime grava recusas/conflitos no audit. Django persiste execuções/noops/controle de aprovação, mas não tentativas rejeitadas antes do commit; registrar essa diferença antes de prometer paridade de auditoria |
| Auditoria vs dados enviados ao agente | CoS projeta IDs/hashes/códigos e oculta prosa sensível. Provenance Django contém diffs completos; não deve ser repassada integralmente ao modelo como resultado de tool |
| Efeitos externos | Nenhum desses fluxos comprova entrega de mensagem, execução de trabalho externo ou aceite do executor apenas por ter registrado uma relação |

## 5. Contrato necessário para integrar

Considerando PostgreSQL como a fonte de verdade já definida no [COMMAND_LAYER](./COMMAND_LAYER.md), a integração precisa de uma decisão explícita sobre importação/vínculo da ABox e suas identidades. A validação não realizou migração nem sincronização de dados.

1. Definir a matriz de capacidades realmente suportadas. Manter indisponíveis as operações do CoS sem equivalente completo; não emular workflows por CRUD parcial.
2. Introduzir um port determinístico de preparação/execução/consulta de resultado que preserve o catálogo comum usado pela UI. O LLM recebe apenas argumentos de negócio; Actor, grants, workspace, revisões, chave e approvals são injetados pelo host autenticado.
3. Persistir a correspondência de IDs externos, principal/Person/User/workspace, proposta/run de origem e command/approval. Restrições de contexto, acesso e seleção não podem ser ampliadas pela tradução.
4. Preparar a intenção e todas as versões antes da confirmação. No “sim”, revisar e executar a intenção salva com o Actor originador; manter o humano revisor distinto no histórico. Não pedir ao modelo para reconstruir o payload.
5. Projetar resultados e erros para o contrato público do CoS, incluindo sucesso/noop/pendência/conflito e reconciliação de resposta perdida. Manter fingerprint semântico e recibos existentes do host.
6. Homologar cada equivalência de domínio/policy e só então disponibilizá-la na superfície do agente.

Critérios mínimos de aceite de um futuro adapter: mesma intenção pela UI e pelo adapter passa pelo mesmo handler; pendência não muda domínio; recusa/expiração/revisão obsoleta não executam; “sim” não chama LLM; dupla confirmação produz um commit; resposta perdida é reconciliada com a mesma chave; todas as referências têm versões fixadas antes do aceite; seleção ambígua não ganha autoridade; principal/grant revogado é negado; provenance mantém agente, humano revisor, run e mensagem originais.

Esses critérios não exigem integrar Deep Agents nesta etapa. Exigem testes contratuais do adapter e dos comandos correspondentes antes de publicar tools.

## 6. Evidência e reprodução

Na raiz de `JMR_Personal-CoS`, com a `.venv` já existente:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  --basetemp=/tmp/radar-cos-runtime-validation \
  tests/integration/test_radar_approval_flow.py \
  tests/integration/test_radar_semantic_telegram.py \
  tests/integration/test_radar_advanced_telegram.py \
  tests/tools/test_radar_mutation_proposals.py \
  tests/agent/test_radar_provenance.py \
  tests/agent/test_radar_surface.py \
  tests/unit/test_radar_operation_repository.py \
  tests/unit/test_radar_mutation_audit.py
```

Resultado dos testes: **33 passed** em 5,46 s, com um warning de depreciação da dependência `google.genai` em Python 3.14.

As provas adicionais executaram o pacote instalado e o normalizador reais do CoS, com vaults descartáveis. O contrato Django foi comparado por leitura estática; os resultados enviados ao normalizador eram representativos desse contrato, sem executar uma integração CoS/Plane.

| Prova local | Resultado observado |
| --- | --- |
| Comparação dos bytes do Core | Iguais; SHA-256 registrado na seção 1 |
| Preparação de `capture_issue` | Notas, audit e receipts permaneceram inalterados |
| Execução de `capture_issue` | Criou três entidades canônicas com revisão inicial `0` |
| Replay com a mesma chave e intenção | Mesmo resultado, sem novos efeitos no vault ou audit |
| `create_action` sem Decision | Rejeitado |
| `decide` | Criou Decision com status `decided` |
| `approve` pela mesma autoridade criadora | Aceito; status da Decision preservado |
| Principal construído pelo caminho de escrita do CoS | `id="telegram:42"`, `is_agent=False` |
| Projeção de sucesso, noop e pendência Django | `failed / invalid_response`, conforme os quatro casos da seção 2, achado V4 |

Essas provas confirmaram as diferenças descritas. Os testes existentes validam garantias do runtime CoS; não homologam um adapter entre os dois sistemas. A conclusão se limita às versões e fontes examinadas: **compatibilidade arquitetural parcial, sem compatibilidade direta de execução**.

A entrega desta revisão consiste apenas neste relatório Markdown. As propostas da seção 5 são recomendações para trabalho futuro; nenhuma alteração na implementação ou integração foi realizada nesta revisão.
