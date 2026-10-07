# Backend RADAR Command Layer

Implementado em 04/10/2026. `RADAR_BACKEND=command-layer` seleciona um port HTTP para o PostgreSQL RADAR. Leitura e escrita usam esse backend; nenhuma tool escreve no banco ou no vault. O valor default `vault` preserva instalações existentes.

O contrato completo, os endpoints e o provisionamento estão em [COS_INTEGRATION.md](../../../plane-radar-phase-0-spike/docs/radar/COS_INTEGRATION.md).

## Configuração

```dotenv
RADAR_ENABLED=true
RADAR_BACKEND=command-layer
RADAR_COMMAND_URL=https://<host>/api/workspaces/<slug>/radar/runtime/v1/
RADAR_COMMAND_TOKEN=<token-emitido-pelo-RADAR>
RADAR_CONTEXT=company:<contexto>
RADAR_PERSON_ID=PER-20261004-ABC123
RADAR_ALLOWED_TBOX_VERSIONS=3.2.0
TELEGRAM_ALLOWED_USER_ID=<id-do-autor-vinculado>
RADAR_WRITES_ENABLED=true
RADAR_WRITE_OPERATIONS=capture_issue,delegate,review,record_measurement
RADAR_APPROVAL_TTL_SECONDS=900
```

Aplicar `.venv/bin/alembic upgrade head` antes de iniciar. A revisão `20261004_0013` acrescenta `execution_context` ao ledger de propostas. Não é necessário `RADAR_VAULT_PATH` nesse backend. O token usa SecretStr na configuração e não é exposto como argumento de tool.

## Fluxo

- `RadarCommandRuntime` verifica contrato `1.0`, Core/hash, contexto e Person no handshake. Capabilities desconhecidas falham antes da publicação das tools.
- As quatro tools de proposta continuam usando os guards de seleção do CoS. Actor e provenance são construídos pelo host a partir da execução e da mensagem autenticada.
- Preparação salva uma CommandExecution agente/CommandApproval no RADAR sem mudar objetos de domínio. O CoS conserva recibo, hash dos parâmetros, versão, run e chave, sem colocá-los na apresentação ao usuário.
- “sim”/“não” enviam a intenção salva e a fonte da confirmação. A resposta é resolvida fora do modelo; o backend registra o humano vinculado como revisor e mantém o agente como autor da mutação.
- Timeout/5xx usa `persistence_failure` e preserva estado incerto. Reconciliação usa a mesma chave e recibo; se bloqueada, permanece incerta. Alterar parâmetros ou revisão de uma proposta é recusado.
- O ledger e o override semântico preservam o recibo após reinício. O TTL local desse backend é limitado a 30 minutos; o default é 15 minutos.

| Operação CoS | Comando RADAR |
| --- | --- |
| `capture_issue` | `CaptureIssue` |
| `delegate` | `DelegateAction` |
| `review` | `ReviewObject` |
| `record_measurement` | `RecordMeasurement` |

O adapter também oferece `prepare_command`/`resolve_command` para o envelope comum dos comandos da UI, sujeito a grants e regras human-only. Esse port não é publicado como tools CRUD genéricas ao modelo.

## Compatibilidade e ativação

IDs canônicos precisam de vínculo explícito com UUIDs no RADAR. Revisões são versões nativas do backend, sem conversão aritmética das revisões do vault. Toda referência é fixada na preparação; a confirmação não atualiza o snapshot.

São homologadas as quatro operações acima no subconjunto de onze tipos do backend, com Document válido como evidência. O catálogo completo de 14 operações e as demais implementações da interface Evidence do pacote não são equivalentes automaticamente. O diagnóstico de `validate_vault` no port cobre valores de propriedades; não substitui a validação normativa completa.

Antes de trocar o backend, encerrar propostas pendentes do vault e executar uma migração explícita de dados/vínculos quando necessária. As migrations não copiam a ABox. Esta entrega não mudou configuração de produção nem operou Telegram/VPS reais.

Testes: regressão CoS e cadeia Alembic; recibo após reinício/override; origem/run da mensagem; payload adulterado; handshake incompatível; timeout e replay; confirmação/recusa sem chamar agente. O teste entre repos em `plane/radar/tests/test_runtime_contract.py` carrega este adapter real e executa as quatro operações contra a API Django e banco isolado.
