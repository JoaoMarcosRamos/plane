# 0.5 — Cenário conectado Governança de IA

Validado localmente em **03/10/2026**. Resultado: **PASS WITH CAVEATS**. Encerramento técnico da Fase 0 e decisão em [SPIKE_REPORT](./SPIKE_REPORT.md).

## Entrega e contrato normativo

O cenário usa os models, commands, API, store e Object Page genérica de 0.3A–0.4. A única nova operação é um carregador demonstrativo opt-in, `radar_governance_scenario`, com Actor humano explícito, autorização de membership e transação única. Não há migration, model gerencial específico, alteração upstream ou nova tela nesta etapa.

| ObjectType | Object real                | Edição feita no navegador e conferida após refresh                          |
| ---------- | -------------------------- | --------------------------------------------------------------------------- |
| objective  | Implantar Governança de IA | progress = 25                                                               |
| project    | Sandbox IA                 | description = Sandbox controlado para validar a Governança de IA            |
| decision   | Adotar GitHub Enterprise   | rationale = Acesso centralizado e licenciamento governado para o Sandbox IA |
| action     | Negociar licenças          | due_date = 2026-11-03                                                       |
| risk       | Licenciamento pode atrasar | likelihood = 4; impact = 4; score derivado = 16                             |

| Source                     | RelationType / label forward | Target                     | Label reverse |
| -------------------------- | ---------------------------- | -------------------------- | ------------- |
| Sandbox IA                 | advances / Advances          | Implantar Governança de IA | Advanced by   |
| Sandbox IA                 | contains / Contains          | Adotar GitHub Enterprise   | Contained in  |
| Adotar GitHub Enterprise   | creates / Creates            | Negociar licenças          | Created by    |
| Licenciamento pode atrasar | threatens / Threatens        | Implantar Governança de IA | Threatened by |

`SUPPORTS` é alias normativo de `advances`. O par Decision AFFECTS Project do plano original foi substituído por **Project contains Decision**, conforme o roadmap vigente e o Core 3.2.0. O `affects` do domain pack technology não permite esse par. Nenhuma ontologia foi alterada.

Snapshot do subconjunto regenerado a partir de `JMR_RADAR_ONTOLOGY/ontology/core.yaml` e comparado integralmente com `core-3.2.0.json`: igualdade confirmada, SHA-256 da fonte `8ea1a14a17c25ff1e6a4945bf75f51982b7ce2243b3509df18a5f74a3bfd6ab7`. Rules/policies, scopes company/manager e runtime completo continuam fora da Fase 0; esta evidência cobre o subconjunto estrutural declarado em SEMANTIC_MODEL_ADR.

## Reproduzir o cenário

Usar o stack isolado `plane-radar`, migrations aplicadas, um workspace dedicado existente e um humano ativo membro/admin. O comando exige que não haja nenhum Object RADAR, inclusive tombstones, nesse workspace. Não cria usuário, workspace ou Plane Project.

```sh
docker compose -p plane-radar -f docker-compose-local.yml -f docker-compose.radar.yml exec api \
  python manage.py radar_governance_scenario \
  --workspace SEU_WORKSPACE_DEDICADO \
  --actor UUID_DO_HUMANO_MEMBRO \
  --reason 'Demonstrar Governança de IA — Fase 0.5'
```

A saída JSON contém os cinco UUIDs e URLs de Object Page. O comando aplica todas as propriedades e as quatro relações pelos commands existentes. Uma falha tardia reverte schema/Objects/valores/relações da execução inteira. Reexecução é rejeitada antes de alterar os dados: não há identidade por título, sobrescrita de edições ou limpeza automática. Para repetir, usar outro workspace dedicado. O comando é uma ferramenta local de fixture; não é endpoint de produto, auto-seed ou execução de agente.

Nesta execução: workspace `radar-governance-zero`, **cinco Objects e zero Plane Projects**. A [manifestação inicial](./governance-runtime/manifest.json) registra identidades e links. O navegador usa web:3000 e API:8001.

## Validação executada

- Percurso real nos dois sentidos das quatro arestas: Objective ↔ Project ↔ Decision ↔ Action e Objective ↔ Risk. Labels reversos representam a mesma aresta persistida.
- Uma propriedade de cada Object editada pela UI, salva e verificada após hard refresh; Risk.score recalculado pelo command. Criador/atualizador continuam o humano da fixture. Versões finais: Objective 9, Project 6, Decision 10, Action 5 e Risk 6.
- Object de outro workspace, em um workspace em que o humano também é membro, mostra `Object unavailable` sem Properties. Após remover a sessão, deep link redireciona ao login.
- [Rede do cenário](./governance-runtime/browser-network.txt): **zero chamadas `/issues/` ou `/work-items/`**. Consultas de Projects ainda são feitas pelo wrapper do shell e retornam listas vazias; não são dependência do Core.
- [Assertions PostgreSQL e valores finais](./governance-runtime/validation-evidence.json). O script [verify_persistence.py](./governance-runtime/verify_persistence.py) reproduz as assertions após as mesmas edições de navegador, via `docker exec -i plane-radar-api-1 python manage.py shell < docs/radar/governance-runtime/verify_persistence.py`.

| Check atual                     | Resultado / evidência                                                                                             |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Backend RADAR completo          | **130 PASS**, incluindo 12 novos testes de cenário/extensibilidade; [log](./governance-runtime/backend-tests.log) |
| Frontend RADAR                  | **42 PASS**; [log](./governance-runtime/frontend-tests.log)                                                       |
| Web types / format              | PASS; [types](./governance-runtime/frontend-types.log), [format](./governance-runtime/frontend-format.log)        |
| OxLint estrito RADAR            | Zero errors/warnings; [log](./governance-runtime/radar-lint.log)                                                  |
| Ruff nos arquivos backend novos | Lint e format PASS                                                                                                |
| Migrations / diff               | `makemigrations radar --check --dry-run`: nenhuma mudança; `git diff --check`: PASS                               |

Os testes novos cobrem arestas forward/reverse por API, autoria/defaults, score derivado, edições persistidas, rejeição atômica de valor inválido, isolamento em todos os endpoints, actors não humanos, guest/non-member, reexecução preservando identidade/edições, rollback da última aresta, erros/saída do comando e tipo adicional pela mesma API. Os 118 testes anteriores foram reexecutados, não apenas citados como evidência histórica.

Execução backend: `docker compose -p plane-radar-tests -f docker-compose-test.yml -f /tmp/radar-test-image.yml run --rm api-tests pytest plane/radar/tests -q`. O override temporário selecionou a imagem local existente `plane-radar-api:latest` (`pull_policy: never`), com o código atual montado em `/code`; não houve rebuild da imagem nesta execução. O runner instalou requirements/test.txt e usou os serviços isolados do compose de testes. Ao terminar, `down -v` removeu apenas o projeto `plane-radar-tests`; o stack demonstrativo foi preservado.

## Evidência visual

- [Objective — propriedades e backlinks](../../output/playwright/radar-governance/01-objective.png).
- [Project — advances e contains](../../output/playwright/radar-governance/02-project.png).
- [Decision — creates e contained_in](../../output/playwright/radar-governance/03-decision.png).
- [Action — due date e created_by](../../output/playwright/radar-governance/04-action.png).
- [Risk — score e threatens](../../output/playwright/radar-governance/05-risk.png).
- [Isolamento — Object indisponível](../../output/playwright/radar-governance/07-isolation.png).

## Ressalvas

Hydration/MobX warnings e consultas de Projects do shell persistem. O editor inicializa HTML e pode indicar rascunho mesmo sem alteração humana; nesta validação foram salvas apenas propriedades, e os títulos permaneceram exatamente os do cenário. Lista sem paginação, edição last-write-wins e ausência de histórico persistido de Actor/provenance permanecem dívida conhecida. Não foram implementados agente, Graph, Outbox, builders, comments ou attachments RADAR. Nenhum commit, merge ou deploy foi feito.
