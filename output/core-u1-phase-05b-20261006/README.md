# Evidências — Core U1 5B / C18

[Relatório](../../docs/radar/CORE_U1_PHASE_05B_REPORT.md) · [ADR](../../docs/radar/CORE_U1_PHASE_05B_ADR.md).

## Resultados

| Verificação                | Resultado                                                                                                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend final              | **542 RADAR + 2 Plane aprovados**, 3 opt-ins de HTTP CoS desativados; **26 casos C18 novos**                                                                          |
| Contratos dirigidos finais | **41 aprovados**, incluindo C18, namespace e adapter CoS real com HTTPX in-process                                                                                    |
| Frontend                   | **147 aprovados em 20 arquivos**, 15 casos novos                                                                                                                      |
| Workspace                  | **56/56 tarefas** de `pnpm check`, incluindo tipos, lint, formato e paridade de contratos                                                                             |
| Python/model/migration     | Ruff/formatação aprovados; `makemigrations radar --check --dry-run` sem mudanças pendentes                                                                            |
| Migration/backfill         | Upgrade real em banco isolado, originais/offset/microssegundos/customização/identidades preservados, idempotência e export verificados; reversão destrutiva bloqueada |
| Navegador/dados            | Fluxos de leitura confirmados sobre API e PostgreSQL reais, capturas inspecionadas e prova independente no banco                                                      |

- `live-inventory-before-migration.json`: probe somente leitura do stack em uso; **tabela legada ausente**, sem alteração de estado. Não prova uma população instalada vazia.
- `apps/api/output/core-u1-phase-05b-migration.json`: upgrade real 0015→0016 em PostgreSQL descartável, preservação de IDs/arquivo/timestamps/customização, idempotência, backfill explícito, export streaming e reversão destrutiva bloqueada.
- `browser-db-proof.log` / `apps/api/output/core-u1-phase-05b-browser-proof.json`: verificação independente de prazos, executores, páginas, medições, autoria desconhecida e vínculos execution/provenance.
- `browser-ui-proof.json`, snapshots e capturas em [`output/playwright`](../playwright): Today; detalhe/delegação; conflito; páginas/filtro; medições; guest/legado; limpeza do painel após perda de acesso. Capturas inspecionadas.
- `api-server.log`: requests reais, filtros/cursor e status 200/403; `browser-final-console.log`: zero erros no Today final. Warnings de módulos externalizados pertencem ao harness Vite; favicon ausente na abertura inicial. Os 403 do teste de perda de acesso são intencionais.
- `source-manifest.json`: hashes SHA256 do código RADAR/contratos usado na entrega; `artifact-manifest.json`: hashes dos resultados e dos documentos.
- A primeira regressão (`backend-initial.log`, XML `core-u1-phase-05b-regression-initial.xml`) encontrou uma expectativa de layout da fase 4 anterior ao novo `due_at`. O teste agora verifica o fallback `other` e a presença desse campo. A regressão final é a evidência de conclusão; o XML dirigido inicial também é histórico e contém uma expectativa de contagem de queries corrigida.

`runtime-namespace-red.log` demonstra a colisão com uma propriedade local `deadline`; o green verifica a correção e o contrato CoS. Projeção de query em `metadata.operation_data.deadline`, sem substituir propriedades. A fixture do teste de definição incompatível foi ajustada para representar metadata legada, pois o editor atual proíbe troca de kind (`backend-fixture.log`, `deadline-metadata.log`). A regressão pré-namespace já havia passado; o resultado final inclui a correção do namespace.

## Reprodução no ambiente descartável

O override usa a imagem local já existente `plane-radar-api`, com código do worktree montado em `/code`. Não reaproveita DB/Redis/MQ/MinIO do stack em uso. CoS é montado somente para leitura; o adapter real usa HTTPX in-process.

```sh
# Executar a partir da raiz do worktree.
dc() { docker compose -p radar-core-u1-phase05b -f docker-compose-test.yml -f output/core-u1-phase-05b-20261006/docker-compose.override.yml "$@"; }
dc run --rm -e RADAR_COS_SOURCE=/cos \
  -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests \
  pytest plane/radar/tests plane/tests/unit/models/test_workspace_model.py \
  --junitxml=output/core-u1-phase-05b-final.xml

# Banco plane descartável, separado de test_plane; testar o upgrade antes de subir o harness.
dc run --rm api-tests python output/core-u1-phase-05b-verify-migration.py
dc run --rm api-tests python manage.py makemigrations radar --check --dry-run
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
```

O script de migration foi executado no banco descartável antes do harness. Depois que 0016 estiver instalada, sua reversão destrutiva é bloqueada; para repetir toda a prova, recrie apenas esse projeto de testes com `dc down -v` e execute novamente. O script mantém a tabela de fatos em vez de demonstrar um rollback que os apagaria.

Harness: `apps/api/output/core-u1-phase-05b-browser-fixture.py` servido na porta 8956; Vite via `ui-preview-source/vite.config.ts` na 3056. Fixture cria commands reais e um arquivo representativo por escrita de teste; login usa sessão Django real. Editor rico, seletor de membros e identificação/permissões visuais são stubs. Nenhum endpoint de produto é mockado. O wrapper `browser-cli.sh` usa Playwright CLI e cache/daemon em `/private/tmp`; iniciar Chrome exigiu execução fora do sandbox. Os snapshots precederam referências de elementos.

```sh
dc run --rm --name radar-phase05b-browser-api -p 8956:8956 api-tests \
  python output/core-u1-phase-05b-browser-fixture.py
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --dir apps/web exec vite \
  --config ../../output/core-u1-phase-05b-20261006/ui-preview-source/vite.config.ts
bash output/core-u1-phase-05b-20261006/browser-cli.sh open http://127.0.0.1:3056/fixture/login/admin/
# GET /fixture/info/ fornece o slug e os IDs da execução, que são aleatórios.
docker exec radar-phase05b-browser-api python output/core-u1-phase-05b-browser-proof.py
# Ao terminar: fechar apenas a sessão core-u1-5b, parar esse harness e executar dc down -v.
```

## Rollout administrativo (não executado no stack em uso)

Após instalar a cadeia de migrations e o schema compatível, faça inventário/export, revise blockers/divergências/hash, aplique e verifique contagens antes de liberar operações novas. O mesmo fuso deve ser usado no dry-run e no apply. O CLI exige administrador. A reason documenta a migração; não inventa autoria dos fatos legados.

```sh
python manage.py radar_operational_backfill --workspace WORKSPACE --admin-id ADMIN_UUID --timezone America/Bahia
python manage.py radar_operational_backfill --workspace WORKSPACE --admin-id ADMIN_UUID --export > operational-export.jsonl
python manage.py radar_operational_backfill --workspace WORKSPACE --admin-id ADMIN_UUID --timezone America/Bahia \
  --apply --reviewed-hash HASH_REVISADO --reason 'Reconciliação revisada dos fatos operacionais'
```

Não há dual-write. Voltar à aplicação antiga sem exportação/restauração preparada ocultaria os fatos novos. O export auxilia a recuperação, sem substituir uma prova completa de restore. Não houve deploy, provider externo, alteração do código CoS ou homologação integral de U1. C13/fase 6 é a próxima implementação.
