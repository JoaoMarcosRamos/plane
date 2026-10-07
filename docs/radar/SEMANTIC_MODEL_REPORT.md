# 0.3B — Semantic Model

Implementado e validado localmente em **03/10/2026**. Resultado: **PASS WITH CAVEATS**. Próxima etapa: **0.4 — UI de propriedades, relações e backlinks**. Não constitui merge ou release; a Fase 0 permanece aberta.

## Resultado

PropertyDefinition, PropertyValue, RelationType e Relation têm tabelas e migration próprias (`radar.0002`), sem herança ou FKs para Project/Issue do Plane. Todas as mutações passam por commands transacionais com Actor humano explícito, membership, isolamento por workspace e auditoria. PostgreSQL continua mestre.

[Decisões anteriores à migration](./SEMANTIC_MODEL_ADR.md) descrevem JSONB tipado por PropertyValue, índices, cardinalidade, locks, exclusão e compatibilidade. [Snapshot Core 3.2.0](../../apps/api/plane/radar/ontology/core-3.2.0.json) contém o subconjunto estrutural e SHA-256 da fonte. O gerador `python -m plane.radar.ontology.snapshot /path/to/ontology/core.yaml` reproduz exatamente a snapshot; o carregador de runtime usa apenas JSON versionado, sem depender do diretório externo.

## Entrega

- Quatro models genéricos e uma migration adicional; seis models concretos e duas migrations RADAR cumulativos.
- Seed lazy/idempotente: seis ObjectTypes (cinco do spike + Person para owned_by), 35 PropertyDefinitions e 14 RelationTypes. Status, vocabulários, limites e defaults vêm da ontologia.
- Commands: initialize_semantic_model, initialize_object_properties, set_property_value, remove_property_value, create_relation, remove_relation. CreateObject materializa defaults atomicamente; UpdateObject bloqueia troca de tipo incompatível com dados existentes.
- Valores string/string_list/number/integer/boolean/enum/date/datetime/email/uri/user. Sem coerção de boolean para número; referências user exigem humano ativo membro. Owner é owned_by → Person; Person é Object RADAR, não User do Plane.
- Domain/codomain, allowed_pairs de creates, self-link e cardinalidade outgoing 0..1/0..n. Backlinks consultam a mesma aresta. Duplicação idempotente preserva identidade/versões; hard delete bloqueado; soft delete mantém tombstones/autoria e recriação usa novo UUID.
- RADAR-E011 (datas de Objective) e RADAR-E013 (score de Risk): validação nas duas direções de data e score derivado atomicamente ao editar fatores.
- Service tipado e store MobX isolado: snapshots incluem Object.version; respostas antigas não sobrescrevem alterações recentes. Mutação de aresta atualiza os dois endpoints; snapshots em versão anterior ficam indisponíveis até recarregar.

## API interna de sessão

Prefixo: `/api/workspaces/{slug}/radar/`.

| Método | Caminho                                  | Resultado                                                  |
| ------ | ---------------------------------------- | ---------------------------------------------------------- |
| GET    | property-definitions/?object_type={uuid} | Definições ativas do workspace/tipo                        |
| GET    | objects/{id}/properties/                 | Object + valores persistidos/defaults efetivos             |
| POST   | objects/{id}/properties/                 | Materializar defaults de Object legado; payload vazio      |
| PUT    | objects/{id}/properties/{definition_id}/ | SetPropertyValue; body `{ "value": ... }`                  |
| DELETE | objects/{id}/properties/{definition_id}/ | Soft delete de valor opcional sem default                  |
| GET    | relation-types/                          | Configuração de relações ativas                            |
| GET    | objects/{id}/relations/?direction=both   | Snapshot forward/reverse; outgoing/incoming também aceitos |
| POST   | relations/                               | CreateRelation; body relation_type/source/target (UUIDs)   |
| DELETE | relations/{id}/                          | Soft delete; Object snapshots dos endpoints                |

GET de propriedades não persiste defaults nos Objects legados. Inicialização de configuração pode ocorrer em GET, seguindo o contrato lazy de 0.3A. Membro guest pode ler/inicializar configuração, mas não mutar Objects/valores/relações. Identidade/auditoria não vêm do payload. Required/defaulted properties não podem ser removidas; definições obrigatórias sem default impedem criação incompleta.

## Validação executada

[Resultados estruturados dos checks](./semantic-runtime/checks.json).

| Verificação                                               | Resultado                                 |
| --------------------------------------------------------- | ----------------------------------------- |
| pytest plane/radar/tests --migrations, PostgreSQL isolado | 118 passed (43 Core + 75 Semantic)        |
| pnpm --filter web test:radar                              | 13 passed (store e transporte do service) |
| pnpm --filter web check:types                             | PASS                                      |
| pnpm --filter web check:format                            | PASS                                      |
| pnpm --filter web check:lint                              | 0 erros; 538 warnings preexistentes       |
| OxLint estrito somente RADAR                              | 0 erros/warnings                          |
| Ruff check / format --check plane/radar                   | PASS                                      |
| Django check / makemigrations radar --check --dry-run     | PASS; sem drift                           |
| Snapshot comparada à fonte normativa e SHA-256            | Correspondência exata                     |
| migrate radar no stack plane-radar                        | 0002 aplicada com sucesso                 |

Os testes incluem valores inválidos, bounds, enums, required, null/remoção, payloads falsificados e não-objeto, defaults/Objects legados, rollback de todas as mutações semânticas, autoria com segundo humano, unique constraints, soft delete/recriação, cross-workspace, inativos/excluídos, guest/nonmember/anônimo, sessão cookie, forward/reverse, pares proibidos e versões. Concorrência real com duas conexões cobre seed inicial, propriedade única, duplicação, cardinalidade 0..1 e relações em direções opostas sem deadlock.

Stack de teste: project Compose `radar-semantic-tests`, serviços de docker-compose-test.yml e imagem local já existente `plane-radar-api:latest` via override da imagem. Código do worktree montado em /code; migrations habilitadas. Não foram executados testes no banco principal. Comando equivalente:

```sh
docker compose -p radar-semantic-tests -f docker-compose-test.yml -f /private/tmp/radar-test-image.yml run --rm api-tests pytest plane/radar/tests --migrations
```

Override da imagem usado neste ambiente:

```yaml
services:
  api-tests:
    image: plane-radar-api:latest
    pull_policy: never
```

[Prova persistida por APIs com sessão](./semantic-runtime/validation-evidence.json): workspace `radar-semantic-validation`, zero Plane Projects, quatro Objects e três relações. Datas/status salvos e relidos; Project advances Objective; Risk threatens Objective; Project owned_by Person. Backlinks retornam advanced_by/threatened_by; score derivado 20; Objective.version=6; retry da mesma aresta preserva identidade. Dados de demonstração permanecem no stack isolado. A prova usa Django APIClient com sessão real, não navegador, e não substitui o cenário visual 0.5.

## Métricas e ressalvas

Nenhum novo touch point upstream; os oito arquivos alterados (+25/−6) continuam pertencendo ao shell/0.3A, conforme `git diff --stat`. Código 0.3B fica no namespace RADAR; nenhuma alteração em stores/services/models de Issue/Project. A migration acrescenta quatro tabelas, três índices compostos explícitos e seis constraints (quatro uniques parciais e dois checks).

SUPPORTS corresponde ao alias normativo advances. Decision AFFECTS Project não existe no Core 3.2.0; o affects do pack technology tem outro domínio. O seed preserva a ontologia: contains permite Project→Decision, reverso contained_in. Essa alternativa está documentada para 0.5; uma extensão affects gerencial exigiria decisão normativa futura.

Workspace permanece o boundary de 0.3A; company/manager scopes, policies/grants, action_types, rules/findings, pacotes TI, builders, provenance completa, Graph, Events/Outbox e agentes não foram implementados neste slice. Identidade UUID foi preservada; nenhuma migração automática de ABox Markdown. Cardinalidades mínimas 1..1 pertencem a tipos fora do subconjunto, como Learning/Commitment, e não são expostas como configuração suportada.

Não houve validação visual nova: propriedades/relações/backlinks na Object Page continuam pendentes em 0.4, assim como cenário conectado 0.5 e Go/No-Go 0.6. Lista sem paginação, edição last-write-wins, warnings do shell e Drawer continuam dívida conhecida. Alterações locais anteriores foram preservadas; não foi criado commit nem merge.
