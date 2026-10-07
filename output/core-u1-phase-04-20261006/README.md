# Evidências — Core U1, fase 4

**Data:** 06/10/2026, America/Bahia. Criação por metadata (C03), editor por capacidades efetivas (C20) e apresentação/narrativa principal (C21). [Relatório](../../docs/radar/CORE_U1_PHASE_04_REPORT.md), [ADR](../../docs/radar/CORE_U1_PHASE_04_ADR.md).

## Resultados

- Regressão RADAR: **477 aprovados, 4 opt-ins ignorados**, 25 casos novos (`backend-regression.log`, [JUnit](../../apps/api/output/core-u1-phase-04-regression.xml)). O código backend não mudou depois dessa execução; mudaram só scripts de evidência e frontend.
- Contratos dirigidos: **123 aprovados**, com adapter CoS real, gate C16 e casos 3A, 3B/3C e fase 4 (`backend-contracts.log`, [JUnit](../../apps/api/output/core-u1-phase-04-contracts.xml)).
- Migration 0014: ida, volta e reaplicação (`migration.log`, [JSON](../../apps/api/output/core-u1-phase-04-migration.json)).
- Frontend: **132 aprovados em 18 arquivos** (`frontend.log`). Workspace: **56/56 tarefas** (`workspace-check.log`); 538 avisos de lint preexistentes do app, sem alteração, e zero nos diretórios RADAR.
- Ruff/formatação (`backend-style.log`) e `makemigrations radar --check --dry-run` (`migrations-check.log`) aprovados.
- Navegador: cinco fluxos (`browser-steps.json`, `browser-proof.log`, capturas `browser-*.png`) e prova independente do ledger e do banco ([JSON](core-u1-phase-04-browser-proof.json)).

`result.json` consolida contagens e limites; `source-manifest.json` registra hashes dos arquivos desta fase. O worktree já continha alterações das fases anteriores. Não houve commit nem deploy.

## Reproduzir

Na raiz do worktree, com a imagem local `plane-radar-api`. O projeto `radar-core-u1-phase04` é separado do stack `plane`; o banco usa tmpfs. Não execute suítes ou fixtures simultaneamente no mesmo servidor de testes.

```sh
C="docker compose -p radar-core-u1-phase04 -f docker-compose-test.yml -f output/core-u1-phase-04-20261006/docker-compose.override.yml"

$C run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-04-regression.xml
$C run --rm api-tests python output/core-u1-phase-04-style.py check
$C run --rm api-tests python manage.py makemigrations radar --check --dry-run
$C run --rm -e PYTHONPATH=/code api-tests python output/core-u1-phase-04-verify-migration.py
$C run --rm -e RADAR_COS_SOURCE=/cos -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests \
  pytest plane/radar/tests/test_runtime_contract.py::test_actual_cos_http_adapter_prepares_and_replays \
  plane/radar/tests/test_core_u1_phase03.py plane/radar/tests/test_core_u1_phase03bc.py plane/radar/tests/test_core_u1_phase04.py \
  plane/radar/tests/test_core_u1_phase01.py::test_command_modules_do_not_depend_on_api_serializers_or_private_cross_module_interfaces \
  --junitxml=output/core-u1-phase-04-contracts.xml

pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
```

## Navegador

A [fixture WSGI](../../apps/api/output/core-u1-phase-04-browser-fixture.py) cria um workspace descartável e quatro membros (autor, revisor aprovador, admin, guest), além de sessões reais. Ela adiciona o tipo `ticket` pelo upgrade administrativo auditado, com required sem default, lifecycle com carimbo e apresentação. O [harness](ui-preview-source/) renderiza a `RadarObjectPage` e o `RadarCreateObjectDialog` de produção, com store, service e provider reais. Só o editor rico, o seletor de membros e o hook de permissões de UI são stubs. A API real fica em 127.0.0.1:8944 e o Vite em 127.0.0.1:3049.

```sh
$C down -v   # banco limpo
$C run --rm --name radar-phase04-browser-api -p 127.0.0.1:8944:8944 -e PYTHONPATH=/code api-tests python output/core-u1-phase-04-browser-fixture.py
cd apps/web && ./node_modules/.bin/vite --strictPort --config ../../output/core-u1-phase-04-20261006/ui-preview-source/vite.config.ts
node output/core-u1-phase-04-20261006/browser-proof.mjs     # Playwright headless
docker exec radar-phase04-browser-api python output/core-u1-phase-04-browser-proof.py
```

Fluxos:
1. Criação do Ticket pela UI: Create fica bloqueado até o required ser preenchido; o inicial informado é Open; a narrativa é Summary; content aparece como Notes. Depois, transições open→working→closed com carimbo e estado terminal sem opções livres.
2. Risk com score derivado somente leitura e seções Assessment/Response.
3. CompleteAction com evidência escolhida, preview do servidor e confirmação.
4. Decision indisponível ao autor, aprovada e tomada pelo revisor independente.
5. Guest somente leitura, sem ações governadas.

`browser-proof-initial.log`/`browser-api-initial.log` conservam a primeira execução, que encontrou dois defeitos. O formulário aninhado e o conflito de versão de uma dependência tocada por outro command foram corrigidos. `browser-proof-run2.log` conserva a execução seguinte, anterior à humanização dos rótulos. Os arquivos sem sufixo são a execução final, num banco limpo com o código final. Nenhuma credencial foi registrada.

## Encerramento

`teardown.log` registra `down -v` apenas deste projeto de teste; fixture e Vite foram encerrados.
