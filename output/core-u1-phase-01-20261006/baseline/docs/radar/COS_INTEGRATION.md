# Integração RADAR Command Layer ↔ COS_AGENT_V2

Destino: **COS_AGENT_V2**, cópia independente de `JMR_Personal-CoS`. A integração foi inicialmente aplicada no original e transferida para a cópia em 04/10/2026. As referências operacionais abaixo apontam para a cópia.

A chamada de execução pelo produto Plane foi acrescentada na Fase 1.3 e tem [contrato próprio de Agent Runtime](AGENT_RUNTIME.md), com identidade de sessão, tabela de runs e API separada. Este documento descreve o caminho CoS → commands do RADAR. A [Fase 1.4 — Agent Config](AGENT_CONFIG.md) acrescentou configuração versionada e recorte de contexto para runs iniciados pelo Plane; seu executor permanece somente leitura. A skill e a revisão de propostas pela UI foram entregues localmente na [Fase 1.5 — Risk Review](RISK_REVIEW.md).

Implementação: 04/10/2026. Contrato HTTP `1.0`; Core `3.2.0`, SHA-256 `8ea1a14a17c25ff1e6a4945bf75f51982b7ce2243b3509df18a5f74a3bfd6ab7`.

O CoS pode usar o PostgreSQL do RADAR como backend para leitura, preparação, aprovação e execução. A UI e o adapter invocam `execute_command`; o adapter não grava em models ou no vault. A seleção do backend é explícita e mantém o caminho de vault disponível para instalações existentes. Esta entrega modifica os repos; a ativação de um ambiente exige as migrations, os vínculos e a configuração abaixo.

## 1. Contrato e fronteira de confiança

Base: `/api/workspaces/<slug>/radar/runtime/v1/`. Autenticação: `Authorization: Bearer <credential>`. O banco armazena somente o hash do token.

| Endpoint                 | Contrato                                                                                                                                        |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET capabilities/`      | Versão, hash do Core, contexto/Person vinculados, comandos permitidos e definições das operações disponíveis                                    |
| `POST query/`            | `method` e `parameters`: search, read, contexto do grafo, catálogo e diagnóstico de propriedades                                                |
| `POST prepare/`          | `operation`, `target_id` canônico, `parameters`, `idempotency_key`, `provenance`; salva pendência sem alterar domínio                           |
| `POST commands/prepare/` | Envelope comum do Command Layer e `provenance`; usa os mesmos schemas/handlers da UI                                                            |
| `POST resolve/`          | `command_id`, `intent_hash`, chave original, `approve`, `rationale`, fonte da confirmação; revisa e executa a intenção salva ou registra recusa |

A credencial é provisionada por um administrador e fixa workspace, contexto, UUID do agente, User revisor, Person, autor Telegram e eventual autoridade de gerente. O `ActorGrant` continua obrigatório e é verificado novamente em cada etapa. Não há campos `actor_type`, `actor_id`, `reviewer_id` ou workspace escolhidos pela tool.

O host CoS é responsável por autenticar a mensagem Telegram. Seu token permite atestar a confirmação daquele único autor e exercer a revisão pelo User previamente vinculado; não é uma credencial para distribuição ao modelo. O backend verifica essa correspondência, membership, identidade ativa, grant e escopo. A credencial pode restringir `object_ids`; criação exige escopo de contexto completo. Mudanças no vínculo invalidam a aprovação preparada.

`provenance` contém `run_id`, `correlation_id`, `reason` e fonte autenticada: update/chat/message, autor, timestamp e SHA-256 do texto. O backend monta Actor `agent`, origem `radar.cos.telegram` e `on_behalf_of` do delegador. A revisão possui Actor `human` próprio e a fonte da mensagem “sim”/“não”. O run originador é preservado, mesmo que a confirmação aconteça em outra execução do CoS. UUIDs existentes são mantidos; identificadores de correlação não UUID recebem uma conversão UUID5 determinística.

Para captura, o backend verifica a fonte contra a metadata autenticada. Para medição com evidência inline, verifica também o hash do texto. Evidência existente não recebe uma segunda fonte inline. `confidence`, quando aplicável a uma assertion inferida pelo catálogo comum, continua obrigatório e validado pelo Command Layer.

## 2. Operações de domínio

O snapshot estrutural foi ampliado de sete para onze tipos: acrescenta Case, ManagementItem, Indicator e Commitment, conservando o hash da fonte normativa. A cardinalidade `1..1` de `commits_to` passa a ser aceita pelo schema/banco e limita o vínculo a uma ação. O vínculo de um Commitment existente exige exatamente uma Action já vinculada no mesmo contexto; essa relação obrigatória não pode ser removida isoladamente. Criar um Commitment canônico exige o fluxo de aceite, que não está publicado nesta integração.

| Tool/operação atual do CoS | Comando comum       | Comportamento                                                                                                                                                                                            |
| -------------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `capture_issue`            | `CaptureIssue`      | Cria Case + ManagementItem `kind=issue` + Document de origem; vincula contains/evidences e owner opcional; registra a alegação sem confirmar seu conteúdo                                                |
| `delegate`                 | `DelegateAction`    | Exige Action ativa e owner ou gerente vinculado; valida executores ativos; substitui assigned_to, torna compromissos confirmed anteriores superseded e registra termos em estado proposed, sem aceite    |
| `review`                   | `ReviewObject`      | Exige Document válido; registra assessment, evidence, próxima revisão e histórico; resolved encerra ManagementItem/Risk, accepted aceita Risk; revisão retrospectiva sem disposição permanece disponível |
| `record_measurement`       | `RecordMeasurement` | Exige Indicator ativo, valor finito e observação mais recente, sem data futura; registra valor, data, evidência e histórico, com vínculo evidences                                                       |

Cada uma usa schemas estritos, versões das referências, grants, transação, provenance e outbox do dispatcher. Humanos também podem invocá-las pelo endpoint comum `commands/`. Agentes sempre exigem aprovação; humanos obedecem às permissões e regras do comando. O port comum não transforma `ApproveDecision` em uma operação de agente: sua restrição human-only permanece.

Os eventos específicos são `IssueCaptured`, `ActionDelegated`, `ObjectReviewed` e `MeasurementRecorded`, além dos eventos de objetos/relações e do controle de aprovação. `OperationalRecord` mantém assignment, reviews e measurements; toda alteração toca a versão do Object e recebe provenance.

## 3. IDs, revisões e persistência

`RuntimeObjectIdentity` associa um UUID RADAR a um ID canônico (`PER-...`, `ACT-...`, etc.) e a um contexto. O vínculo é explícito e imutável; não há associação por título. Objetos novos do adapter ganham identidade no mesmo commit do comando. Objetos existentes precisam de vínculo administrativo antes de aparecerem no CoS.

O port retorna a versão nativa do PostgreSQL, inicialmente `1`. Não soma nem subtrai revisões do vault. Preparação fixa **todas** as referências: alvo, evidência, executores, owner, atribuições anteriores e compromissos afetados. A confirmação usa o mapa salvo; não consulta versões novas para substituir esse snapshot.

Leituras usam o mesmo backend selecionado. IDs fora do contexto/escopo são indisponíveis; relações projetadas não incluem endpoints ocultos. Resultados de execução retornam somente IDs canônicos de Objects, versão do alvo e `operation_id`, com `status=executed`, `code=ok`. IDs de PropertyValue, Relation, provenance e outros registros auxiliares ficam fora do resultado da tool. Um noop confirmado é projetado como sucesso sem novos efeitos.

## 4. Aprovação, deduplicação e recuperação

1. O CoS prepara no backend e recebe um recibo com command ID, hash, chave, operação, alvo, revisão e hash dos parâmetros.
2. O recibo fica em `pending_radar_operations.execution_context`, separado dos argumentos de negócio e da apresentação ao usuário. Também acompanha o payload de override semântico.
3. O “sim” faz claim no ledger CoS e envia o recibo original com metadata da confirmação. O servidor revisa a CommandApproval e executa o envelope armazenado com o Actor agente original. O modelo não é chamado.
4. Recusa explícita é encaminhada ao backend; conflito, expiração, schema/policy/vínculo obsoleto ou revogação impedem o commit.
5. Replay do mesmo recibo retorna o resultado já persistido. Mudança de payload, chave ou hash é recusada. Fingerprint semântico e override single-use do CoS continuam ativos.
6. Timeout, resposta inválida de transporte ou HTTP 5xx usam `persistence_failure`; o CoS conserva `uncertain` e permite reconciliação pela mesma intenção/chave. Reconciliação bloqueada continua incerta: não comprova rollback do commit original.

A pendência do backend expira em 30 minutos; o TTL local é limitado a esse teto para o backend Command Layer, e o valor recomendado é 900 segundos. Uma proposta preparada que não virar registro local, por duplicidade ou falha local, não muda domínio e expira. Não há reconstrução automática nem rebase silencioso.

## 5. Provisionamento e ativação

Aplicar migrations no ambiente escolhido, sem executar estes passos contra produção durante testes:

```sh
# Plane, em apps/api, com o ambiente Django configurado
python manage.py migrate

# COS_AGENT_V2
.venv/bin/alembic upgrade head
```

No Plane, criar/identificar a Person humana e os objetos necessários usando a UI/Command Layer. Vincular cada objeto existente ao ID canônico e contexto. Exemplo de vínculo:

```sh
python manage.py radar_runtime_provision \
  --workspace <slug> --admin-id <user-admin-uuid> --context company:<contexto> \
  --bind-object <person-object-uuid> --external-id PER-20261004-ABC123
```

Emitir uma credencial para o CoS. Este comando também configura PersonIdentity e o grant das quatro operações + LinkObjects. O token aparece uma única vez no stdout; transferi-lo para a configuração protegida do host.

```sh
python manage.py radar_runtime_provision \
  --workspace <slug> --admin-id <user-admin-uuid> --context company:<contexto> \
  --agent-id <agent-uuid> --reviewer-id <human-user-uuid> \
  --person-id <person-object-uuid> --telegram-user-id <telegram-id>
```

`--manager` concede autoridade de delegação no contexto explicitamente. Sem ele, o delegador precisa ser owner da Action. Novos grants para outros comandos são provisionados pelo controle existente; o catálogo genérico não é publicado como tools CRUD ao modelo.

No CoS:

```dotenv
RADAR_ENABLED=true
RADAR_BACKEND=command-layer
RADAR_COMMAND_URL=https://<host>/api/workspaces/<slug>/radar/runtime/v1/
RADAR_COMMAND_TOKEN=<token-provisionado>
RADAR_CONTEXT=company:<contexto>
RADAR_PERSON_ID=PER-20261004-ABC123
RADAR_ALLOWED_TBOX_VERSIONS=3.2.0
TELEGRAM_ALLOWED_USER_ID=<telegram-id>
RADAR_WRITES_ENABLED=true
RADAR_WRITE_OPERATIONS=capture_issue,delegate,review,record_measurement
RADAR_APPROVAL_TTL_SECONDS=900
```

Nesse modo, `RADAR_VAULT_PATH` não é necessário. O handshake verifica contrato, Core, contexto e Person antes de disponibilizar a integração. Backend incompatível ou parcialmente configurado permanece indisponível.

## 6. Validação e limites

Resultados locais em 04/10/2026 (validação original da implementação):

| Verificação                                                                       | Resultado                                               |
| --------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Backend RADAR completo, migrations reais e PostgreSQL isolado                     | **164 passed**, incluindo o teste entre repos           |
| Regressão selecionada CoS, ledger, tools, aprovação e cadeia Alembic              | **93 passed**                                           |
| Protocolo e confirmação executados novamente no repo CoS após aplicar os arquivos | **16 passed**; subconjunto dos 93, sem somar à contagem |
| UI RADAR (`pnpm --filter web test:radar`)                                         | **49 passed**                                           |
| Tipos da aplicação web (`pnpm --filter web check:types`)                          | Passou                                                  |
| Ruff nos arquivos Python alterados; OxLint/oxfmt no tipo TypeScript alterado      | Passou                                                  |
| `makemigrations radar --check --dry-run`                                          | Nenhuma migration pendente                              |

Na transferência para `COS_AGENT_V2`, a regressão selecionada do CoS foi repetida na cópia temporária preparada usando o Python de `COS_AGENT_V2`: **93 passed**. Após a aplicação no destino real, protocolo, confirmação e migrations foram repetidos: **18 passed** (subconjunto dos 93). `JMR_Personal-CoS` foi restaurado somente nos 14 arquivos da integração e seu checkout ficou limpo. Backup e manifesto: `output/cos-agent-v2-relocation-20261004/`. Backend Plane e UI não foram reexecutados nesta transferência.

O teste entre repos carrega `RadarCommandRuntime` real do CoS e encaminha suas requisições HTTP via `httpx.MockTransport` para APIClient Django e PostgreSQL isolado. Exercita as quatro operações e o envelope comum, incluindo preparação, confirmação e replay. Essa verificação não homologa rede externa, proxy/TLS ou entrega Telegram real. A regressão CoS foi executada primeiro em uma cópia isolada; os 16 testes de protocolo/confirmação foram repetidos após aplicar os mesmos arquivos no repo original.

Para repetir o backend, criar um override Compose com o source CoS montado somente para leitura. `RADAR_COS_SOURCE` é obrigatório para que o teste entre repos seja executado; sem ele, esse caso é marcado como skipped.

```yaml
# /tmp/radar-cos-tests.yml
services:
  api-tests:
    environment:
      RADAR_COS_SOURCE: /cos
    volumes:
      - ${RADAR_COS_TEST_SOURCE}:/cos:ro
```

```sh
# Na raiz Plane; requer apps/api/.env e os pré-requisitos do guia de testes.
export RADAR_COS_TEST_SOURCE=/caminho/para/COS_AGENT_V2
docker compose -p radar-cos-contract-tests \
  -f docker-compose-test.yml -f /tmp/radar-cos-tests.yml \
  run --rm --build api-tests pytest plane/radar/tests --migrations
docker compose -p radar-cos-contract-tests \
  -f docker-compose-test.yml -f /tmp/radar-cos-tests.yml down -v

# Na raiz CoS, com o ambiente de desenvolvimento instalado.
.venv/bin/python -m pytest \
  tests/unit/test_radar_command_runtime.py \
  tests/unit/test_radar_config.py \
  tests/unit/test_radar_operation_repository.py \
  tests/unit/test_radar_mutation_audit.py \
  tests/unit/test_radar_service_relation_projection.py \
  tests/unit/test_migrations.py \
  tests/integration/test_radar_read_flow.py \
  tests/integration/test_radar_startup.py \
  tests/integration/test_radar_approval_flow.py \
  tests/integration/test_radar_semantic_telegram.py \
  tests/integration/test_radar_advanced_telegram.py \
  tests/integration/test_radar_vault_operations.py \
  tests/tools/test_radar_mutation_proposals.py \
  tests/tools/test_radar_tools.py \
  tests/agent/test_radar_provenance.py \
  tests/agent/test_radar_surface.py
```

Cobertura: preparação sem alteração de domínio, aprovação/replay, origem agente e humano revisor distintos, quatro operações, catálogo compartilhado, executor/referência obsoleta, escopo/grant/credencial revogados, hash/fonte adulterados, datas de medição, owner obrigatório, compromissos superseded, recibo após reinício/override, perda de resposta e confirmação sem modelo.

Limites explícitos:

- O backend cobre onze tipos e usa **Document válido** como evidência. Meeting, Feedback, Learning e Routine não são homologados nessa superfície. As políticas adicionais de evidência do Plane são mantidas; não se promete equivalência irrestrita com toda interface Evidence do vault.
- As dez operações restantes do pacote `radar-vault`, incluindo `confirm_commitment`, não são publicadas pelo adapter. Não se infere aceite, entrega externa ou execução de trabalho a partir de uma delegação.
- `validate_vault` no port faz diagnóstico de valores de propriedades no escopo PostgreSQL; não reproduz o validador completo do pacote normativo.
- Migrations criam estruturas; não importam nem sincronizam a ABox real. Migração de dados e de histórico exige uma etapa explícita. Propostas antigas do backend vault não podem ser retomadas no backend Command Layer; devem ser encerradas antes da troca.
- O backend default do CoS continua `vault`. Não foram alterados `.env`, credenciais de produção, VPS ou Telegram real. Não foi introduzida uma nova arquitetura Deep Agents.

Fontes: [port HTTP](../../apps/api/plane/radar/api/runtime_views.py), [operações compartilhadas](../../apps/api/plane/radar/commands/operations.py), [provisionamento](../../apps/api/plane/radar/commands/runtime_control.py), [adapter CoS](../../../COS_AGENT_V2/app/integrations/radar_commands.py), [teste entre repos](../../apps/api/plane/radar/tests/test_runtime_contract.py), [documentação CoS](../../../COS_AGENT_V2/docs/development/RADAR_COMMAND_LAYER.md).
