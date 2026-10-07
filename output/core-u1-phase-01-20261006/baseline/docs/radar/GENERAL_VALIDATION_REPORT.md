# RADAR — Validação geral das fases implementadas

Data: 04/10/2026. Escopo: checkout local do Plane e COS_AGENT_V2, fases 0–1.4. A Fase 1.2 tem backend entregue; a experiência de revisão de propostas continua pendente na 1.5.

**Validação técnica local concluída: 2.130 testes únicos aprovados, zero falhas/erros; nove avaliações CoS opt-in com provider real desativadas.** O recorte de propriedades foi corrigido e revalidado. Os gates de release/piloto continuam pendentes; a próxima implementação é 1.5.

O backend foi validado em dois recortes: 899 testes sobre banco vazio com migrations reais (199 RADAR + 700 Plane), e 202 RADAR atuais sobre esse mesmo schema migrado, incluindo três regressões novas. Há 199 testes sobrepostos; o total backend único é 902, não 1.101.

## Escopo por fase

| Fase                                       | Cobertura deste passe                                                                                     | Limites                                                             |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 0.0–0.2 — baseline e shell                 | Regressão backend Plane, tipos/lint/format do monorepo e inspeção de rotas/provider por workspace         | Navegador/login/storage da baseline não foram homologados novamente |
| 0.3A — Core Foundation                     | Commands, auditoria, versão, membership, tenant, soft delete e independência de Project/Issue             | Não transforma o fork local em release                              |
| 0.3B — Semantic Model                      | Tipos de propriedades, relações, cardinalidade, backlinks, seeds e isolamento                             | Builders completos continuam futuros                                |
| 0.4 — UI semântica                         | Testes de service/store e formulários; checks dos componentes e APIs de propriedades/relações             | Evidência visual anterior permanece histórica                       |
| 0.5 — Governança de IA                     | Cenário conectado, cinco Objects/quatro relações normativas, persistência, zero Projects e isolamento     | Qualidade de sugestões não faz parte desse cenário humano           |
| 0.6 — Go/No-Go                             | Conferência de gates e inventário de ressalvas                                                            | CONDITIONAL GO continua sem readiness de produção                   |
| 1.1/1.2 — Command Layer/provenance backend | Catálogo compartilhado, grants, intenção salva, approvals, replay, versões, provenance e outbox           | Accept/Edit/Reject na UI e publisher operacional pendentes          |
| Integração CoS → commands                  | Adapter real, port comum, identidade/provenance e execução da intenção salva                              | Sem Telegram ou contas externas reais                               |
| 1.3 — Agent Runtime                        | Fachada Plane, DTOs, isolamento, ledger, eventos, pausa/reinício, revogação, harness scripted e HTTP real | Executor somente leitura; sem provider real                         |
| 1.4 — Agent Config                         | Persistência/versão, autoria, grants, escopo, DTO, UI unitária, snapshot por run e contexto limitado      | Browser fixture da entrega não substitui E2E do produto             |

O hash do snapshot Core 3.2.0 confere com `JMR_RADAR_ONTOLOGY/ontology/core.yaml`: `8ea1a14a17c25ff1e6a4945bf75f51982b7ce2243b3509df18a5f74a3bfd6ab7`. Nenhuma alteração normativa foi feita. As migrations RADAR não adicionam FKs para Plane Project/Issue; o provider frontend permanece remontado pela chave de workspace.

## Correções encontradas pelo passe

### Contexto: campos autorizados antes do orçamento

O carregador lia as primeiras 41 PropertyValues e só depois aplicava a permissão de campos. Isso permitia que 42 campos ocultos excluíssem um campo autorizado do snapshot. Outra situação marcava truncamento quando havia exatamente 20 campos permitidos seguidos de um campo oculto.

A consulta agora filtra as permissões antes do recorte. Carrega no máximo 21 valores autorizados, usa o último como sentinela e inclui até 20 no snapshot. Valores com mais de 500 caracteres JSON continuam omitidos com truncamento explícito. O ajuste não reescreve snapshots históricos de runs.

Três testes cobrem 42 ocultos + 1 permitido, exatamente 20 permitidos e 21 permitidos. A reprodução inicial teve dois testes falhando e um passando; após a correção os três passaram. Evidências: [red](../../output/general-validation-20261004/context-red.log), [green](../../output/general-validation-20261004/context-green.log), [teste](../../apps/api/plane/radar/tests/test_context_bounds.py).

### Infraestrutura e qualidade

RabbitMQ da stack isolada falhava ao ler seu cookie Erlang. O Compose agora executa broker e health check como `rabbitmq`, com tmpfs pertencente ao UID/GID 100/101 da imagem Alpine usada. A configuração foi conferida na imagem instalada e a stack ficou healthy. Esse ajuste afeta somente a infraestrutura de testes.

Também foram corrigidos a formatação de `create-object-input.test.ts` e o comprimento da linha de fonte de evidência em `test_runtime_contract.py`, sem mudança de comportamento.

## Resultados finais

- Backend atual: **202 RADAR passaram**, incluindo 22 de configuração, 13 da fachada e três de orçamento de propriedades. Os **700 testes Plane** também passaram na suíte ampliada de 899; nenhum arquivo de código do Plane upstream mudou nesta correção. Ambas as suítes backend terminaram sem falhas, erros ou skips.
- CoS completo: **1.170 passaram, 9 skipped**, zero falhas/erros. Inclui dois testes PostgreSQL em banco separado. Os skips são avaliações opt-in com provider real. Dois warnings de depreciação permanecem em dependências/Alembic. A suíte ampliada Plane registrou 92 warnings, principalmente de factory_boy/openpyxl; eles não foram tratados como falhas nem como corrigidos.
- Frontend RADAR: **58 passaram em 8 arquivos**.
- Monorepo: **56 tarefas de check concluídas**, cobrindo tipos, lint e format nos pacotes/apps configurados. Warnings upstream permanecem dentro dos limites existentes; lint estrito RADAR passou sem warnings.
- Ruff backend RADAR/CoS, formatação de Python e frontend RADAR aprovados.
- Django check/makemigrations aprovados. Banco vazio recebeu o histórico completo e as sete migrations RADAR; `migrate --check` e `showmigrations radar` conferidos.

Comandos e logs deste passe: [evidências](../../output/general-validation-20261004/README.md). Os resultados da entrega 1.4 e seus manifestos continuam históricos; este passe tem [resultado estruturado](../../output/general-validation-20261004/result.json) e [manifesto](../../output/general-validation-20261004/manifest.json) próprios. As stacks e o servidor HTTP temporários foram encerrados após a validação.

## Ressalvas e próxima etapa

Não foram reexecutados navegador/login completos, upload/download real da baseline, provider real, Telegram, TLS remoto ou piloto. Os testes frontend são unitários; a evidência de Chrome da entrega 1.4 usa fixture isolada. Não houve commit, merge, deploy ou alteração de ambiente publicado.

Continuam os gates do [SPIKE_REPORT](SPIKE_REPORT.md): storage/anexos, replay pristine e versão reproduzível antes de release/piloto compartilhado. Eventos/outbox persistidos não equivalem a publisher/consumidores operacionais. Today, colaboração, Risk Review e revisão humana na UI permanecem pendentes conforme o [roadmap](../../../DOCS_PROJETO_RADAR_COMPLETO/RADAR_ROADMAP.md).

O próximo incremento continua **1.5 — Risk Review e revisão humana**, com os critérios de [prontidão](NEXT_PHASE_READINESS.md). Este passe não implementa a 1.5 nem encerra o MVP Human–Agent Loop.
