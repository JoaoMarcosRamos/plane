# Evidências — Core U1, fase 5A

**Data:** 06/10/2026, America/Bahia. **Escopo:** C19. [Relatório](../../docs/radar/CORE_U1_PHASE_05A_REPORT.md), [ADR](../../docs/radar/CORE_U1_PHASE_05A_ADR.md).

## Resultado

- Regressão final: **516 RADAR + 2 Plane aprovados**, 3 opt-ins ignorados, zero falhas/erros. [JUnit](../../apps/api/output/core-u1-phase-05a-final.xml), `backend-final.log`. Inclui 38 casos C19 novos e o adapter de produção do CoS, com transporte in-process.
- Frontend: **132 aprovados em 18 arquivos** (`frontend.log`). `pnpm check`: **56/56 tarefas** (`workspace-check.log`); paridade adicional de estratégias/contextos (`runtime-contract-parity.log`).
- Ruff e formatação aprovados (`backend-lint-final.log`, `backend-format-check.log`); `makemigrations` sem mudanças estruturais (`migrations-check.log`).
- Migration 0015: ida, volta, reaplicação e idempotência (`migration.log`, [JSON](../../apps/api/output/core-u1-phase-05a-migration.json)).

`source-manifest.json` registra o código final; `result.json` consolida os resultados. Os logs intermediários são preservados: a primeira execução não é baseline conclusiva porque o código foi alterado durante o processo; o teste dirigido inicial tinha uma chave de input incorreta na fixture. `backend-regression.log` é a execução intermediária anterior ao teste adicional de criação composta; `backend-final.log` é a confirmação do código final em processo novo.

## Reproduzir

Projeto Docker exclusivo `radar-core-u1-phase05a`, imagem local `plane-radar-api`, banco tmpfs. Não usa nem modifica os serviços do projeto `plane`. Não executar duas suítes simultâneas no mesmo servidor de testes. Não sobrescrever `.env` existente com setup.

```sh
C="docker compose -p radar-core-u1-phase05a -f docker-compose-test.yml -f output/core-u1-phase-05a-20261006/docker-compose.override.yml"

$C run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u1-phase-05a-regression.xml
$C run --rm -e PYTHONPATH=/code api-tests python output/core-u1-phase-05a-verify-migration.py
$C run --rm -e RADAR_COS_SOURCE=/cos -v /Users/joaomarcosramos/Documents/Github/COS_AGENT_V2/app:/cos/app:ro api-tests \
  pytest plane/radar/tests plane/tests/unit/models/test_workspace_model.py --junitxml=output/core-u1-phase-05a-final.xml
$C run --rm api-tests python manage.py makemigrations radar --check --dry-run

pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false --filter web test:radar
pnpm --config.manage-package-manager-versions=false --config.verify-deps-before-run=false check
$C down -v
```

Ruff/formatação: os arquivos de produto alterados estão no manifesto; os logs registram os argumentos exatos. A migration foi testada pela função e pelo executor Django. `core-u1-phase-05a-migration.json` registra preservação de fatos, IDs, timestamps, opt-out, base instalada e revisão.

## Configuração de um tipo customizado

Por `update_metadata`/API `schema` com `operation=edit`, revisão esperada e patch de `rules` completo, preservando as outras seções:

```json
{
  "enabled": true,
  "identity": { "strategy": "dated_token_v1", "prefix": "TKT" },
  "contexts": ["company", "manager"]
}
```

Depois, binding explícito administrativo:

```sh
python manage.py radar_runtime_provision --workspace WORKSPACE --admin-id ADMIN_UUID \
  --context company:CONTEXT --bind-object OBJECT_UUID --external-id TKT-20261006-ABC123 \
  --expected-schema-revision REVISION
```

O descritor não cria grant/credential. `--object-types` seleciona explicitamente os tipos ao emitir uma credencial; sem a opção, o CLI usa a lista dos tipos elegíveis naquele momento, incluindo Person. A lista de um grant existente não muda quando um tipo é criado.

## Limites

Sem UI nova, nova prova de navegador, provider externo, deploy ou mudança no repositório CoS. O adapter CoS real foi validado com HTTPX in-process sobre Django/PostgreSQL. As capturas da fase 4 permanecem históricas. C18, C13 e a homologação integrada não estão encerrados. O teardown elimina apenas o projeto de testes desta entrega.
