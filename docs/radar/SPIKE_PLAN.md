# SPIKE_PLAN — Fase 0

A visão permanece: Plane-derived Product Shell + RADAR Core + Object / Type / Relation + Command Layer + Provenance + Human-Agent Loop.

## Sequência confirmada em 2026-10-03

- 0.1: inspeção; evidência em `phase-0/PLANE_MAP.md`, `REUSE_MAP.md`, `DOMAIN_COUPLING.md`.
- 0.2B: shell e seams em runtime; evidência histórica em `phase-0/RUNTIME_SEAM_VALIDATION.md`.
- **0.3A — Core Foundation**: RadarBaseModel → Actor → ObjectType → Object → commands mínimos → API → service/store isolados → Object Page persistida.
- **0.3B — Semantic Model**: PropertyDefinition, PropertyValue, RelationType e Relation. Não implementar em 0.3A; depende da validação completa do vertical slice.

A mudança é de sequência, não de visão. O primeiro write passa por command e recebe Actor explícito. Não há Outbox, eventos, agentes nem grafo em 0.3A.

## Aceitação de 0.3A

Criar Objective “Implantar Governança de IA” pela UI num workspace sem Projects; editar para “Implantar Governança de IA na C3”; verificar PostgreSQL, criador preservado, atualizador e versão 1 → 2, refresh e deep link. Backend cobre isolamento, membership e transações. Resultados em `CORE_VERTICAL_SLICE_REPORT.md`.

## Resultado de 0.3A

Concluído: **PASS WITH CAVEATS**. 43 testes backend e 5 testes unitários frontend passaram; criação/edição pela UI, PostgreSQL, zero Projects, hard refresh, deep link, membership e navegação entre apps validados. Ressalvas são overhead/warnings preexistentes do shell e limites explícitos do slice. Ver [CORE_VERTICAL_SLICE_REPORT.md](./CORE_VERTICAL_SLICE_REPORT.md).

0.3B implementada e validada localmente: models/migration próprios, commands, seed normativo, API e service/store. Ver [SEMANTIC_MODEL_REPORT.md](./SEMANTIC_MODEL_REPORT.md).

## Resultado de 0.4

Concluído localmente: **PASS WITH CAVEATS**. Object Page com edição genérica dos 11 tipos de propriedade, seletor de relações compatíveis, forward links/backlinks e remoção confirmada. Rascunhos preservados durante mutações/erros; guest somente leitura. 42 testes frontend, types/format/lint, navegação e persistência verificadas no navegador e PostgreSQL em workspace dedicado com zero Plane Projects. Ver [SEMANTIC_UI_REPORT.md](./SEMANTIC_UI_REPORT.md).

## Resultado de 0.5

Concluído localmente: **PASS WITH CAVEATS**. Cinco Objects do cenário Governança de IA conectados por advances/contains/creates/threatens; properties dos cinco editadas no navegador e conferidas após refresh/PostgreSQL; navegação nos dois sentidos, isolamento e zero Plane Projects/requests Issues. Carregador opt-in transacional pelo mesmo Command Layer, sem sobrescrever dados existentes. Ver [GOVERNANCE_SCENARIO_REPORT](./GOVERNANCE_SCENARIO_REPORT.md).

## Resultado de 0.6

Encerramento local: **CONDITIONAL GO**, conforme [SPIKE_REPORT](./SPIKE_REPORT.md). 130 testes backend e 42 frontend passaram nesta entrega. Tipo adicional configurado como fixture foi criado/editado pela UI genérica. Inventário: oito touch points upstream (+25/−6), zero novos em 0.5/0.6, duas migrations e seis models concretos. Reuso efetivo UI: 8/17 (47,06%), sem mocks/futuro; alvo amplo >70% não comprovado.

Baseline: login por senha, workspace/Project/WorkItem, editor e comments conferidos; anexo válido/storage isolado/replay pristine permanecem condição antes de release/piloto. Mudanças continuam locais, sem commit/merge/deploy. Próxima implementação recomendada: **Fase 1**, mantendo commands e persistindo provenance/propostas/approval antes de writes de agente. Nenhum runtime/agente foi implementado nesta entrega.
