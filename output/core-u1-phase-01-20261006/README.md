# Evidências — RADAR U1, fases 0 e 1

**Data:** 06/10/2026, America/Bahia. Relatório: [CORE_U1_PHASE_01_REPORT.md](../../docs/radar/CORE_U1_PHASE_01_REPORT.md). Decisões: [ADR](../../docs/radar/CORE_U1_PHASE_01_ADR.md).

## Base e inventário

- [baseline-manifest.json](baseline-manifest.json), [baseline-status.txt](baseline-status.txt) e `baseline/`: hashes, status e cópia dos fontes existentes antes da implementação, sem env/credenciais.
- [Inspeção somente leitura do stack em uso](live-stack-read-only-inspection.json).
- [phase0-inventory.json](phase0-inventory.json): imports privados, consumidores, storage operacional e ausência de RADAR no stack em uso.
- [backend-baseline.log](backend-baseline.log): 301 aprovados, 4 ignorados; [JUnit](../../apps/api/output/core-u1-phase-01-baseline.xml).
- [frontend-baseline.log](frontend-baseline.log): 93 aprovados.

## Validação

[Manifesto final](source-manifest.json) e [patch contra baseline](implementation.patch) identificam os arquivos desta entrega.

- [backend-final.log](backend-final.log), [JUnit final](../../apps/api/output/core-u1-phase-01-final.xml): regressão final RADAR.
- [backend-phase1-unit-final.log](backend-phase1-unit-final.log), [JUnit dirigido](../../apps/api/output/core-u1-phase-01-unit.xml): 18 casos U1 novos aprovados.
- [backend-checks-final.log](backend-checks-final.log): Ruff, formatação, migration check e migrations instaladas no banco isolado.
- [migration-roundtrip.log](migration-roundtrip.log), [resultado](../../apps/api/output/core-u1-phase-01-migration.json): round-trip 0010/0011.
- [frontend-final.log](frontend-final.log), [workspace-check-final.log](workspace-check-final.log): Vitest e checks do monorepo.
- [frontend-lint-final.log](frontend-lint-final.log), [frontend-intent-lint.log](frontend-intent-lint.log): lint dirigido, incluindo ajuste ES2022.

Resultado consolidado: [result.json](result.json): **319 backend aprovados/4 ignorados e 106 frontend aprovados; 56/56 tarefas de check aprovadas**. Logs com `initial`, `retry`, `fix` e a primeira regressão ficam como histórico; não substituem o resultado final nem são somados às contagens.

## Reprodução

Pré-requisitos: `apps/api/.env` existente e imagem local `plane-radar-api`, usados pela bancada U0. O override reutiliza essa imagem e monta o código atual. Não executar pytest concorrente contra o mesmo banco de testes; executar cada comando de testes até terminar.

```sh
docker compose -p radar-core-u1-01-test -f docker-compose-test.yml -f output/core-u1-phase-01-20261006/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-01-final.xml
docker compose -p radar-core-u1-01-test -f docker-compose-test.yml -f output/core-u1-phase-01-20261006/docker-compose.override.yml run --rm api-tests sh -c 'ruff check plane/radar && ruff format --check plane/radar && python manage.py makemigrations radar --check --dry-run'

# Banco descartável novo: script usa modelos históricos e produz fixtures na base plane.
docker compose -p radar-core-u1-01-test -f docker-compose-test.yml -f output/core-u1-phase-01-20261006/docker-compose.override.yml run --rm -e PYTHONPATH=/code api-tests python output/core-u1-phase-01-verify-migration.py

pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
```

As flags do pnpm usam o binário/dependências já instalados e evitam instalação/purge automático; não alteram .npmrc ou lockfile. Vitest pode ser executado em `apps/web` com `./node_modules/.bin/vitest run --config vitest.radar.config.ts`.

## Navegador

[Fixture](browser-fixture.json), [PostgreSQL](browser-db-evidence.json), [API log](browser-api.log), [UI log](browser-ui.log), [captura de agente](browser-agent-authorship.jpg) e [edição humana sobre criação por integração](browser-integration-human-edit.jpg).

Scripts: [API/sessão](../../apps/api/output/core-u1-phase-01-plane-ui-server.py) e [configuração Vite](ui-preview-source/vite.config.ts). Portas loopback :8942 e :3038, projeto Compose exclusivo; hook de usuário/permissões, notes editor e member picker da UI são fixtures. Cada actor foi criado por commands reais; a criação do agente teve review independente antes da execução. Não usar esses scripts em configuração de produto.

O servidor de fixture usa a base plane do stack isolado; pytest usa test_plane. O navegador foi controlado por Chrome/Computer Use após agent-browser não conseguir iniciar Chromium neste ambiente. Os IDs desses Objects são apenas fixtures descartáveis desta validação.

## Encerramento

Encerrar o servidor Vite e o container de browser fixture criados para a tarefa, depois:

```sh
docker compose -p radar-core-u1-01-test -f docker-compose-test.yml -f output/core-u1-phase-01-20261006/docker-compose.override.yml down -v
```

Este teardown atinge exclusivamente a bancada desta entrega. O stack `plane` em uso permanece intacto.
