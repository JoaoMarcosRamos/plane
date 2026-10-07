# Evidências — Core U1 fase 2

Implementação de C07/C11/C12 e parte estrutural de C17, em 06/10/2026. [Relatório](../../docs/radar/CORE_U1_PHASE_02_REPORT.md), [ADR](../../docs/radar/CORE_U1_PHASE_02_ADR.md).

`baseline-manifest.json` e `baseline/` capturam a base herdada das fases 0/1, sem drift no conjunto observado. `source-manifest.json` registra a entrega e os hashes; `implementation.patch` descreve o delta contra essa base, incluindo novos arquivos. O worktree contém trabalho anterior; HEAD isoladamente não é a base desta fase.

## Reproduzir backend

Usar um projeto Docker descartável separado do stack `plane`. O override reutiliza a imagem local `plane-radar-api`, sem reconstruí-la; ela deve ter os requisitos de `apps/api` instalados. Os sources são montados pelo Compose.

```sh
docker compose -p radar-core-u1-02-test -f docker-compose-test.yml -f output/core-u1-phase-02-20261006/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-02-final.xml
```

Baseline: 319 aprovados/4 ignorados. Regressão final: 356 aprovados/4 ignorados, 360 casos. Depois do ajuste de CORS, os mesmos 5 testes de transporte passaram novamente; não somar à contagem.

O script [verify-migration](../../apps/api/output/core-u1-phase-02-verify-migration.py) usa o banco padrão descartável `plane`; pytest usa `test_plane`. Não executar suites simultâneas no mesmo banco. O teste da migration cobre legado coincidente/divergente, customizado, workspace vazio, IDs/fatos e reverse/forward. Resultado em [JSON](../../apps/api/output/core-u1-phase-02-migration.json).

```sh
docker compose -p radar-core-u1-02-test -f docker-compose-test.yml -f output/core-u1-phase-02-20261006/docker-compose.override.yml run --rm -e PYTHONPATH=/code api-tests python output/core-u1-phase-02-verify-migration.py
```

## Reproduzir frontend e contratos

```sh
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
cd apps/web
./node_modules/.bin/vitest run --config vitest.radar.config.ts
```

114 testes em 16 arquivos, 56/56 tarefas no workspace. O `check` inclui `check:radar-contracts` (11 kinds, 5 config keys, 3 cardinalidades). Manifestos separam arquivos novos e modificados. A extensão do baseline de `package.json` reconstrói apenas as duas alterações observadas de scripts (`check` e novo `check:radar-contracts`); demais campos anteriores foram conservados.

## Navegador

A [fixture WSGI](../../apps/api/output/core-u1-phase-02-plane-ui-server.py) cria dados descartáveis e sessões reais. `ui-preview-source/` renderiza ObjectPage/RootStore/services/provider de produção; notes/picker/shell são stubs de preview. Vite usa 3039, API 8943, ambos loopback. CLI Chrome não abriu no ambiente; a validação ocorreu pelo CUA conectado.

Fluxo: preparar rascunhos → alterar nome de PropertyDefinition pelo comando administrativo real → polling recebe schema 2 → aviso exige revisão e conserva drafts → revisão explícita → PATCH título v1→2 e PUT propriedade v2→3 → reload confirma persistência. Captura `browser-review-required-final.jpg` e `browser-persisted.jpg`; [prova independente do ledger/banco](../../apps/api/output/core-u1-phase-02-browser-proof-final.json). `browser-api.log` conserva requests; nenhuma credencial foi registrada nas evidências.

A indisponibilidade temporária do Docker/controlador ocorreu após a prova principal. O transporte CORS foi validado quando Docker voltou a responder. `teardown.log` registra o encerramento apenas dos recursos desta fase.
