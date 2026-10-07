# Bancada de testes — Fase 1 (1.1–1.7), 05/10/2026

Regressão local de todas as entregas da Fase 1 no Plane e COS_AGENT_V2, sobre o estado atual dos dois checkouts (Plane `8fa56b19d7` + alterações locais; CoS `471ddd8` + alterações locais). Sem alteração de código, commit ou deploy.

## Resultado

**2.243 testes únicos aprovados, zero falhas/erros.** Nove avaliações CoS com provider real desativadas por design (`RUN_LIVE_AGENT_EVAL=0`).

| Suíte                                               | Resultado                                  | Evidência                                                                   |
| --------------------------------------------------- | ------------------------------------------ | --------------------------------------------------------------------------- |
| Backend RADAR + Plane, migrations reais em banco vazio | **967/967** (267 RADAR + 700 Plane), 0 skipped | [log](backend-full.log), [JUnit](../../apps/api/output/phase1-bench-20261005/backend-full.xml) |
| CoS completo, PostgreSQL dedicado                   | **1.184 aprovados**, 9 skipped (provider real) | [log](cos-full.log), [JUnit](cos-full.xml)                                  |
| Frontend RADAR (vitest)                             | **92/92** em 14 arquivos                   | [log](web-tests.log)                                                        |
| Django check / `makemigrations --check`             | sem issues / `No changes detected`         | [log](backend-full.log)                                                     |
| Typegen + tsc (web)                                 | exit 0                                     | [log](web-types.log)                                                        |
| OxLint `--deny-warnings` / Oxfmt, 64 arquivos RADAR | 0 warnings/erros / formatados              | [lint](web-lint.log), [format](web-format.log), [arquivos](web-radar-files.txt) |
| Monorepo `turbo run check`                          | **56/56 tarefas** (12 do cache turbo)      | [log](workspace-check.log)                                                  |
| Ruff check + format (Plane RADAR), Ruff check (CoS) | aprovados                                  | [Plane](backend-ruff.log), [CoS](cos-ruff.log)                              |
| Core 3.2.0                                          | SHA-256 `8ea1a14a…fd6ab7` confere com `JMR_RADAR_ONTOLOGY/ontology/core.yaml` | —                                    |

Diferença em relação às entregas 1.6/1.7: os **quatro testes opt-in antes skipped passaram**. Esta bancada montou o checkout CoS (`RADAR_COS_SOURCE`) e subiu o [servidor CoS scripted](cos-http-server.py) (Deep Agents real, modelo determinístico) em `:8937`:

- `test_runtime_contract::…` — contrato cross-repository Plane ↔ adapter CoS atual.
- `test_agent_runtime::test_real_http_product_cycle` — run pausado → resume → completed → stream → replay idempotente, via HTTP entre processos.
- `test_agent_config::test_configured_http_cycle_preserves_identity_policy_and_scope` — configuração restringe identidade/campos/Objects no run remoto.
- `test_risk_review::test_real_http_skill_and_commands` — skill `risk_review` remota → sugestão → execução pelo Command Layer.

Isso confirma que as alterações locais do CoS posteriores à 1.5 mantêm o contrato com o Plane.

## Cobertura por etapa (casos backend RADAR executados)

| Etapa                         | Arquivos                                                            | Casos |
| ----------------------------- | ------------------------------------------------------------------- | ----- |
| Base 0.3A–0.5 (regressão)     | `test_core`, `test_semantic`, `test_governance`                     | 130   |
| 1.1/1.2 Command Layer/provenance + integração CoS | `test_commands`, `test_runtime_contract`, `test_runtime_provision` | 35    |
| 1.3 Agent Runtime             | `test_agent_runtime`, `test_context_bounds`                         | 16    |
| 1.4 Agent Config              | `test_agent_config`                                                 | 22    |
| 1.5 Risk Review               | `test_risk_review`                                                  | 27    |
| 1.6 Today                     | `test_today`                                                        | 9     |
| 1.7 Colaboração               | `test_collaboration`                                                | 28    |

Frontend: stores/services/componentes de semântica, Agent Config, Risk Review, Today e colaboração (14 arquivos).

## Reprodução

```sh
# Terminal separado, na raiz Plane:
../COS_AGENT_V2/.venv/bin/python output/phase1-bench-20261005/cos-http-server.py

# Backend (projeto Compose descartável próprio):
docker compose -p radar-phase1-bench-20261005 -f docker-compose-test.yml -f output/phase1-bench-20261005/docker-compose.override.yml \
  run --rm api-tests sh -c 'python manage.py check && python manage.py makemigrations --check --dry-run && pytest plane/radar/tests plane/tests --migrations --create-db -q -p no:cacheprovider -o addopts="--strict-markers" --junitxml=output/phase1-bench-20261005/backend-full.xml'

# CoS (no checkout CoS; porta do container dedicado atribuída dinamicamente):
docker run -d --name radar-phase1-bench-cos-db -e POSTGRES_USER=radar_test -e POSTGRES_PASSWORD=radar_test_only -e POSTGRES_DB=radar_test --tmpfs /var/lib/postgresql/data -p 127.0.0.1::5432 postgres:15.7-alpine
RUN_LIVE_AGENT_EVAL=0 TEST_POSTGRES_DATABASE_URL='postgresql+psycopg://radar_test:radar_test_only@127.0.0.1:PORTA/radar_test' .venv/bin/python -m pytest tests -q

# Frontend, a partir de apps/web:
./node_modules/.bin/vitest run --config vitest.radar.config.ts
./node_modules/.bin/react-router typegen && ./node_modules/.bin/tsc --noEmit

# Raiz Plane:
tr '\n' '\0' < output/phase1-bench-20261005/web-radar-files.txt | xargs -0 ./node_modules/.bin/oxlint --deny-warnings
tr '\n' '\0' < output/phase1-bench-20261005/web-radar-files.txt | xargs -0 ./node_modules/.bin/oxfmt --check
CI=1 ./node_modules/.bin/turbo run check --concurrency=2
../COS_AGENT_V2/.venv/bin/ruff check apps/api/plane/radar && ../COS_AGENT_V2/.venv/bin/ruff format --check apps/api/plane/radar
```

`-o addopts` remove `--reuse-db --nomigrations` do `pytest.ini`, forçando o histórico real de migrations (0001–0010 RADAR). O override reutiliza a imagem local `plane-radar-api` e monta o CoS somente leitura; o caminho absoluto deve ser ajustado em outra máquina. A chave do servidor scripted é pública e exclusiva de teste.

Única tentativa descartada: a primeira chamada OxLint/Oxfmt recebeu a lista de arquivos como um só argumento (zsh não divide variáveis) e checou 0 arquivos; refeita via `xargs` acima.

## Limites

Não reexecutados nesta bancada: navegador (as evidências de UI de 1.4–1.7 permanecem as das entregas), upload de anexo pela UI (pendência da 1.7), login/shell completos, provider real, publisher da outbox e piloto (1.8). Suítes unitárias frontend usam mocks e não comprovam persistência. 92 warnings de depreciação na suíte Plane (factory_boy/openpyxl) e dois no CoS (google-genai/Alembic) não são falhas.

## Teardown

Executado: projeto Compose `radar-phase1-bench-20261005` (`down -v`), container `radar-phase1-bench-cos-db`, servidor `:8937` e SQLite temporário. A stack `plane` em execução não foi reiniciada nem alterada. [Log](teardown.log).
