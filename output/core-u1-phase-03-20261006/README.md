# Evidências — Core U1, entrega 3A

**Data:** 06/10/2026, America/Bahia. Primeira entrega da fase 3: registro de capabilities e plano transacional de efeitos (C09/C17). [Relatório](../../docs/radar/CORE_U1_PHASE_03_REPORT.md), [ADR](../../docs/radar/CORE_U1_PHASE_03_ADR.md). Criação (3B/C02) e lifecycle (3C/C01) permanecem pendentes.

## Resultados

- Baseline do worktree herdado: **356 backend aprovados, 4 opt-ins ignorados**.
- Regressão RADAR: **399 aprovados, 4 opt-ins ignorados**, 43 casos novos. [JUnit](../../apps/api/output/core-u1-phase-03-final.xml).
- Frontend: **115 aprovados em 16 arquivos**, um caso novo de service.
- Workspace: **56/56 tarefas**, incluindo paridade de 11 kinds/5 config keys/3 cardinalidades e nove tipos de campo dos contratos de capability.
- CoS: **27 testes selecionados aprovados**. O adapter real também foi exercitado diretamente contra a API Django com PostgreSQL, usando transporte HTTP em processo. A validação final desse fluxo está em `backend-contracts-final.log`; não soma casos à regressão RADAR.
- Ruff/formatação Python aprovados; migration check sem mudanças estruturais. `git diff --check` aprovado.

O `result.json` consolida as contagens e limites; `source-manifest.json` registra hashes dos arquivos desta entrega. Os sources já incluíam alterações staged/unstaged/untracked das fases anteriores. Nenhum commit ou deploy foi feito.

## Reproduzir

Use a imagem local `plane-radar-api`, com os requisitos já instalados, ou remova o override de imagem para fazer build. O projeto de teste é separado do stack `plane`; o banco usa tmpfs. Nunca execute duas suítes simultaneamente no mesmo banco de testes.

```sh
docker compose -p radar-core-u1-phase03 -f docker-compose-test.yml -f output/core-u1-phase-03-20261006/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-03-final.xml

docker compose -p radar-core-u1-phase03 -f docker-compose-test.yml -f output/core-u1-phase-03-20261006/docker-compose.override.yml run --rm api-tests python output/core-u1-phase-03-style.py

docker compose -p radar-core-u1-phase03 -f docker-compose-test.yml -f output/core-u1-phase-03-20261006/docker-compose.override.yml run --rm api-tests python manage.py makemigrations radar --check --dry-run

pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
```

As flags de pnpm conservam as dependências já instaladas. O primeiro comando sem elas tentou uma reinstalação automática e abortou por ausência de TTY, antes de remover módulos; o teste foi reexecutado com a configuração já usada na fase 2. Os warnings preexistentes de lint/cache/Vite não impediram as 56 tarefas.

Depois de encerrar a suíte principal, executar a prova do adapter real:

```sh
docker compose -p radar-core-u1-phase03 -f docker-compose-test.yml -f output/core-u1-phase-03-20261006/docker-compose.override.yml run --rm -e RADAR_COS_SOURCE=/cos -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests pytest plane/radar/tests/test_runtime_contract.py::test_actual_cos_http_adapter_prepares_and_replays plane/radar/tests/test_core_u1_phase03.py plane/radar/tests/test_core_u1_phase01.py::test_command_modules_do_not_depend_on_api_serializers_or_private_cross_module_interfaces --junitxml=output/core-u1-phase-03-contracts-final.xml
```

Os testes selecionados do CoS foram executados no seu ambiente Python existente com `DATABASE_URL=sqlite://`, sem serviços externos: `tests/unit/test_radar_command_runtime.py`, `tests/unit/test_radar_api.py` e `tests/agent/test_radar_provenance.py`. Logs/JUnit estão nesta pasta; nenhum source CoS foi alterado.

## Cobertura e diagnósticos

O gate novo verifica as 21 capabilities, registro adicional em catálogo/runtime/execução, grants parciais sobre tipos/relações/derivação, referência omitida descoberta pelos efeitos, efeito extra recusado, dependência alterada após review, políticas mínimas, replay com grant atual e ausência de reexecução. Inclui preview sem persistência, datas do caller literais, bytes fora do plano, versões auxiliares de guards e retirada operacional de colaboração com histórico preservado.

`backend-regression-initial.log` conserva a falha de import privado, corrigida sem remover o gate C16. `backend-regression-auxiliary.log` conserva a falha de compatibilidade da transição U0 em Object vinculado, corrigida pela distinção entre versões obrigatórias de escrita e leituras auxiliares. `backend-format-registry-initial.log` é diagnóstico de formatação/sintaxe intermediária; o source final compilou e passou regressão/estilo. Os logs `*-final` são os resultados válidos de fechamento.

O primeiro teste isolado de adapter terminou aprovado, mas coincidiu com o início da suíte principal no banco reutilizado. Não é usado como prova final; o fluxo foi repetido sequencialmente em `backend-contracts-final.log`. Baselines, gates e reexecuções não são somados aos 399 casos aprovados da regressão final.

Não houve alteração de UX/TSX ou teste de navegador nesta etapa. O adapter CoS usa HTTP simulado em processo para a API real, sem Telegram/provider. Não foi homologado ambiente publicado, aplicado schema no stack Plane em uso ou ativado builder.

## Encerramento

```sh
docker compose -p radar-core-u1-phase03 -f docker-compose-test.yml -f output/core-u1-phase-03-20261006/docker-compose.override.yml down -v
```

`teardown.log` registra o encerramento apenas dos recursos desta entrega.
