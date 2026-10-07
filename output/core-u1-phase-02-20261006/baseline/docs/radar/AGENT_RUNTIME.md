# RADAR Agent Runtime — contrato 1.0

Destino do motor: COS_AGENT_V2. Plane autentica o usuário, constrói o contexto permitido e mantém domínio/commands. A API de simulação e o canal Telegram mantêm seus contratos.

## Escopo da Fase 1.3

Execução somente leitura e isolada por workspace, usuário, agente e vínculo administrativo. Nenhuma tool de mutação, memória pessoal, Notion, filesystem ou subagente é publicada nesse executor. A skill diagnóstica `context_summary` exercita invoke_skill; Risk Review e revisão de propostas foram entregues na [Fase 1.5](RISK_REVIEW.md), preservando o executor somente leitura. As aprovações de domínio continuam exclusivamente no Command Layer.

## Interface RadarAgentRuntime

- `run`: recebe intenção idempotente e snapshot autorizado; retorna run durável.
- `stream`: entrega eventos persistidos em SSE, com sequência/cursor para reconexão; cada resposta é um lote finito, não streaming de tokens.
- `invoke_skill`: executa somente uma skill registrada, `risk_review` e o diagnóstico legado `context_summary`.
- `load_context`: Plane constrói um snapshot de Objects/Relations com escopo e limites explícitos; o runtime usa somente esse snapshot.
- `interrupt`: pausa em fronteira de execução. Se a inferência já começou, termina em background e guarda o resultado sem publicá-lo como conclusão.
- `resume`: retoma de queued/interrupted; se já há resultado salvo, publica sem chamar modelo novamente. Contexto ou autorização alterados exigem nova intenção, não rebase.
- `cancel`: extensão explícita; encerra logicamente o run e descarta qualquer resultado tardio.

A interrupção é cooperativa. Não é um checkpoint arbitrário do LangGraph e não promete interromper o request do provider no meio. Uma queda durante inferência termina como unknown ao expirar o lease; não reexecuta automaticamente. Runs enfileirados podem ser retomados por nova chamada. A aplicação não introduz um worker/broker adicional neste slice.

## Transporte e autoridade

UI → sessão Plane → fachada `/api/workspaces/{slug}/radar/agent-runtime/` → Bearer servidor a servidor → COS_AGENT_V2 `/agent-runtime/v1/`.

Credencial configurada com canal plane vincula agente, User e Person ao contexto. IDs do payload selecionam esse vínculo, mas não escolhem outro revisor ou escopo. O host do runtime confia somente no token configurado para Plane; esse token nunca é devolvido ao navegador. Em ambiente remoto, usar HTTPS. O serviço começa desabilitado sem configuração explícita.

O snapshot carrega origem plane.session, usuário/workspace/agente, vínculo, versão do grant, versões dos Objects, fontes e indicação de truncamento. Não fabrica IDs Telegram. Cada acesso pela fachada revalida usuário ativo, membership, Person ativa, grant, vínculo e objetos do snapshot. Mudança invalida acesso ao run antigo. O usuário pode criar nova intenção com contexto atualizado.

## Persistência e limites

Plane guarda a referência e intenção idempotente; CoS guarda estado, resultado e eventos do run em tabela dedicada com migration. Nenhum objeto de domínio é alterado. APIs e DTOs públicos não contêm BaseMessage, RunnableConfig ou estado LangGraph.

O contexto é um snapshot pequeno (até 21 Objects, 40 relações, conteúdo por objeto truncado e orçamento total explícito). Truncamento não é completude; a resposta deve informar lacunas. O contrato usa orçamento de caracteres, não contagem exata de tokens.

Estados: queued, running, pause_requested, interrupted, completed, failed, cancelled, unknown. Terminal não é retomável. O mesmo run/idempotency key com outro payload é conflito. Compare-and-swap impede execução duplicada e resultados de workers obsoletos. Eventos são limitados por run; não aceitar ciclos ilimitados de pause/resume.

## Critérios de validação

Testar replay, conflito de payload, dois escopos, revogação, contexto obsoleto, reinício em pausa, resultado salvo sem novo LLM, cancelamento e resultado tardio, lease expirado e falhas de transporte. Validar o adapter real com modelo determinístico e HTTP entre processos isolados. Não utilizar Telegram, provider ou dados de produção nos testes.

## Ativação

Entrega local concluída em 04/10/2026. A ativação em um ambiente escolhido exige:

1. COS_AGENT_V2: aplicar `alembic upgrade head` (migration 0014, tabela `radar_agent_runs`) e definir `RADAR_AGENT_RUNTIME_TOKEN` com pelo menos 32 caracteres ASCII. O Compose encaminha essa variável ao serviço.
2. Plane: aplicar `python manage.py migrate` (migration RADAR 0006, canal do vínculo e tabela `radar_agent_runtime_runs`) e definir `RADAR_AGENT_RUNTIME_URL` apontando para a base `/agent-runtime/v1`, além do mesmo token. Em Docker, usar um endereço acessível ao container, não o localhost do host.
3. Provisionar os vínculos canônicos da Person e dos Objects no contexto e um vínculo de canal `plane` para o usuário/agente. O provisionamento exige autoridade administrativa; seu retorno é o UUID de `binding_id`.

```sh
python manage.py radar_runtime_provision --channel plane \
  --workspace <slug> --admin-id <admin-uuid> --context company:<contexto> \
  --agent-id <agent-uuid> --reviewer-id <user-uuid> --person-id <person-object-uuid>
```

O provisionamento atual reutiliza os grants administrativos existentes; o executor deste slice continua sem tools de mutação. A configuração estruturada e a seleção de permissões pela UI foram entregues na [Fase 1.4](AGENT_CONFIG.md), com versionamento e interseção do grant vigente. Nenhuma migration, credencial privada ou configuração de ambiente publicado foi aplicada nesta entrega.

## Uso pela fachada Plane

Todos os endpoints abaixo são POST e exigem sessão autenticada no workspace:

| Caminho relativo à fachada                     | Corpo / retorno                                                                                                                          |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `context/`                                     | `binding_id`, `root_ids`; retorna snapshot autorizado e limitado                                                                         |
| `runs/`                                        | `binding_id`, `root_ids`, `prompt`, `skill` opcional, `start_paused` opcional; header `Idempotency-Key` obrigatório; retorna 202 com run |
| `runs/{uuid}/status/`                          | `after` opcional; snapshot, resultado e eventos posteriores ao cursor                                                                    |
| `runs/{uuid}/stream/`                          | `after` opcional; lote SSE com eventos e snapshot final                                                                                  |
| `runs/{uuid}/interrupt/`, `resume/`, `cancel/` | `after` opcional; estado persistido após controle                                                                                        |

O resultado contém texto, IDs/versões dos objetos disponibilizados como fontes e indicação de truncamento. As fontes identificam o snapshot fornecido, não são uma validação factual de cada frase do modelo. DTOs fechados rejeitam campos extras e fontes externas ao snapshot. Os eventos têm sequência e timestamp; `after` é o cursor para consulta seguinte.

503 indica runtime/configuração/transporte indisponível; 404 indica vínculo/run/contexto indisponível para o usuário; 409 indica intenção, autorização, contexto ou estado incompatível. Autoridade revogada pode produzir 403. Falhas de geração usam código estável sem expor mensagem do provider. `unknown` exige nova intenção explícita.

## Evidências históricas da entrega 1.3

- Suíte completa RADAR final: **177 testes passaram**, incluindo os **13 testes da fachada** e o ciclo HTTP real Plane → CoS com servidor atualizado.
- Regressão selecionada COS_AGENT_V2: **95 testes passaram** na preparação e novamente no destino real após transferência dos 22 arquivos, incluindo concorrência, retomada após reinício, descarte de resultado tardio, fontes inválidas e o grafo Deep Agents real com modelo determinístico. Os hashes finais conferem com o manifesto.
- Migrations: banco CoS vazio atualizado até head; Django sem migrations pendentes. Ruff dos arquivos alterados e `git diff --check` passaram.
- Serviços de teste isolados; sem chamadas a provider real, Telegram ou dados pessoais. Não houve homologação em navegador, TLS remoto ou ambiente publicado.

A regressão da 1.4 passou posteriormente em 199 testes RADAR, 67 CoS selecionados e 58 frontend, com formulário em fixture de navegador isolada; ver [evidências da configuração](../../output/agent-config-20261004/README.md). Essas suítes têm escopos diferentes e não devem ser somadas às contagens históricas acima.

Os logs, manifesto de hashes, cópia revisável e resultado da transferência ficam em `output/agent-runtime-20261004/`. A documentação do motor é [043 — Agent Runtime](../../../COS_AGENT_V2/docs/development/043-radar-agent-runtime.html). A [Fase 1.4 — Agent Config](AGENT_CONFIG.md) foi entregue localmente. A [Fase 1.5 — Risk Review](RISK_REVIEW.md) foi entregue em 05/10/2026, com revisão humana de propostas; as contagens acima são evidências históricas.
