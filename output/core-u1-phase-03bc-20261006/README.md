# Evidências — Core U1, entregas 3B/3C

**Data:** 06/10/2026, America/Bahia. Criação por capability (3B/C02) e lifecycle declarativo (3C/C01), que concluem a fase 3. [Relatório](../../docs/radar/CORE_U1_PHASE_03BC_REPORT.md), [ADR](../../docs/radar/CORE_U1_PHASE_03BC_ADR.md).

## Resultados

- Baseline do worktree herdado: **399 backend aprovados, 4 opt-ins ignorados** (`backend-baseline.log`, [JUnit](../../apps/api/output/core-u1-phase-03bc-baseline.xml)).
- Regressão RADAR final: **452 aprovados, 4 opt-ins ignorados**, 53 casos novos (`backend-final.log`, [JUnit](../../apps/api/output/core-u1-phase-03bc-final.xml)). `backend-regression.log` é a execução anterior, idêntica em contagem, feita antes de uma limpeza sem efeito de comportamento em `handlers.py`.
- Contratos dirigidos: **98 aprovados**, com adapter CoS real, gate C16, casos 3A e 3B/3C (`backend-contracts.log`, [JUnit](../../apps/api/output/core-u1-phase-03bc-contracts.xml)).
- Migration 0013: ida, volta e reaplicação em banco descartável (`migration.log`, `core-u1-phase-03bc-migration.json`).
- Frontend: **115 aprovados em 16 arquivos** (`frontend.log`). Workspace: **56/56 tarefas** (`workspace-check.log`).
- Ruff/formatação Python aprovados (`backend-style.log`); `makemigrations radar --check --dry-run` sem mudanças (`migrations-check.log`). Docs e `types.ts` verificados com oxfmt.

`result.json` consolida contagens e limites; `source-manifest.json` registra os hashes dos arquivos desta entrega. O worktree já continha alterações staged/unstaged/untracked das fases anteriores. Não houve commit nem deploy.

## Reproduzir

Na raiz do worktree, com a imagem local `plane-radar-api`. O projeto `radar-core-u1-phase03bc` é separado do stack `plane` e usa banco em tmpfs. Não execute suítes simultâneas no mesmo servidor de testes.

```sh
C="docker compose -p radar-core-u1-phase03bc -f docker-compose-test.yml -f output/core-u1-phase-03bc-20261006/docker-compose.override.yml"

$C run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-03bc-final.xml
$C run --rm api-tests python output/core-u1-phase-03bc-style.py check
$C run --rm api-tests python manage.py makemigrations radar --check --dry-run
$C run --rm -e PYTHONPATH=/code api-tests python output/core-u1-phase-03bc-verify-migration.py
$C run --rm -e RADAR_COS_SOURCE=/cos -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests \
  pytest plane/radar/tests/test_runtime_contract.py::test_actual_cos_http_adapter_prepares_and_replays \
  plane/radar/tests/test_core_u1_phase03.py plane/radar/tests/test_core_u1_phase03bc.py \
  plane/radar/tests/test_core_u1_phase01.py::test_command_modules_do_not_depend_on_api_serializers_or_private_cross_module_interfaces \
  --junitxml=output/core-u1-phase-03bc-contracts.xml

pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
```

O script de migration usa o banco padrão descartável `plane`; o pytest usa `test_plane`. Os casos da migration cobrem tipos semeados sem descritores, seção local preexistente, tipo desconhecido, workspace sem estado, fatos/IDs/invariantes, revisão de schema, plano de upgrade vazio com o código atual e reversão.

## Diagnósticos

A primeira execução completa após a implementação teve 27 falhas. A maioria vinha de um default novo em `properties`/`parameters`, que alterava o input normalizado usado pelo Risk Review e pelos intent hashes. Os campos ficaram sem default. Os ajustes restantes alinharam dois testes antigos ao contrato novo. A revisão do planner encontrou a política human-only dependente do estado após o savepoint; ela foi corrigida e coberta por teste. Esses diagnósticos não estão nos logs finais.

Não houve teste de navegador, alteração de UX/TSX, aplicação ao stack Plane em uso, ativação de builder ou homologação de ambiente publicado. Os testes do repositório CoS não foram reexecutados; o contrato consumido mudou só por chaves aditivas.

## Encerramento

```sh
docker compose -p radar-core-u1-phase03bc -f docker-compose-test.yml -f output/core-u1-phase-03bc-20261006/docker-compose.override.yml down -v
```

`teardown.log` registra o encerramento apenas dos recursos desta entrega.
