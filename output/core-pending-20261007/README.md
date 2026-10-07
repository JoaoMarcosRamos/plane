# Evidências — pendências Core

[Relatório](../../docs/radar/CORE_PENDING_REPORT.md) · [Audit](../../docs/radar/CORE_AUDIT.md).

**Resultado final:** 557 RADAR + 2 Plane aprovados, 3 opt-ins ignorados; 154 frontend; 56/56 checks. [result.json](result.json). C13/C23 corrigidos; C14 observado/medido, sem alteração da estratégia de locks.

## Reprodução

Stack descartável próprio `radar-core-pending`; DB/Redis/MQ/MinIO separados do stack em uso. Imagem local `plane-radar-api`, código montado em `/code`. Execute testes backend sequencialmente: dois processos pytest deste projeto compartilham `test_plane`.

```sh
dc() { docker compose -p radar-core-pending -f docker-compose-test.yml -f output/core-pending-20261007/docker-compose.override.yml "$@"; }
dc run --rm -e RADAR_COS_SOURCE=/cos \
  -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests \
  pytest plane/radar/tests plane/tests/unit/models/test_workspace_model.py \
  --create-db --junitxml=output/core-pending-final.xml
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
dc run --rm api-tests ruff check plane/radar plane/settings/common.py plane/settings/local.py plane/settings/production.py
dc run --rm api-tests ruff format --check plane/radar
dc run --rm api-tests python manage.py makemigrations radar --check --dry-run
```

`backend-final.log`, `apps/api/output/core-pending-final.xml`: regressão única final. `backend-directed-final.log`: 39 contratos (14 novos e 25 fase 4) antes do último caso de fallback de capability; não somar à regressão. `frontend-final.log`: 154 testes. `workspace-check-final.log`: 56/56. `python-checks-final.log`: Ruff/schema. `migration.log` e `apps/api/output/core-pending-migration.json`: ida/volta/reaplicação de 0017 com fatos preservados. Baselines C13/C14 estão no stdout dos testes dirigidos e finais.

## Navegador

Harness API: `apps/api/output/core-pending-browser-fixture.py`, porta 8957, schema/domínio/commands/sessão reais. Vite: `ui-preview-source/vite.config.ts`, porta 3057 (3058 na validação final, pois o primeiro processo ocupava 3057). Reiniciar Vite após mudar fontes fora do root do harness, para evitar transforms antigos em cache. `browser-cli.sh` usa a sessão exclusiva `core-pending`. A fixture usa IDs aleatórios; `GET /fixture/info/` retorna workspace/IDs de cada execução.

```sh
dc run --rm --name radar-core-pending-browser-api -p 8957:8957 api-tests python output/core-pending-browser-fixture.py
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --dir apps/web exec vite \
  --config ../../output/core-pending-20261007/ui-preview-source/vite.config.ts
bash output/core-pending-20261007/browser-cli.sh open http://127.0.0.1:3057/fixture/login/admin/
# Com uma fixture populada, roundtrip da migration no banco plane deste stack descartável:
docker exec radar-core-pending-browser-api python output/core-pending-verify-migration.py
```

`browser-final-network.log`: apenas detalhe/snapshots e continuação/permissões; nenhuma lista completa ao abrir detalhe. `browser-remove-network.log`: GET do endpoint com versão antes do DELETE. `browser-final-backlinks-first/next/current.txt`: paginação e botões autorizados nas páginas. `browser-objective-first/next/search.txt`: lista filtrada e busca. `browser-home.txt`: nomes/rotas vindos do catálogo. Capturas em `output/playwright/core-pending-*.jpg`; editor rico, hooks visuais de usuário/membership e shell são delimitados no relatório.

A prova independente `apps/api/output/core-pending-browser-proof.py` usa os IDs/workspaces desta execução, não um script genérico de provisioning. `browser-db-proof.log` e `apps/api/output/core-pending-browser-proof.json` verificam fatos, versões, narrativa, relação remota, remoção/provenance e tamanhos de página. A fixture foi reiniciada para carregar o backend mais recente; criação/transição ocorreram no primeiro workspace, paginação/permissões/remoção no segundo. Nenhum endpoint de produto foi mockado.

Os logs iniciais são históricos: a primeira abertura de Chrome no sandbox falhou; a abertura fora dele passou. Favicon 404 inicial foi removido no harness; navegação final sem erros. Warnings de módulos externalizados pertencem ao harness Vite. A tentativa de duas suítes pytest simultâneas gerou dois conflitos de fixture; apenas a execução final sequencial é evidência de regressão.

Ao terminar, fechar somente a sessão `core-pending`, parar seus dois Vites e o container do harness, e executar `dc down -v`. Nunca usar `down` no stack Plane em uso. Sem deploy ou homologação de produção; C14 permanece uma estratégia conservadora agora observada/medida.
