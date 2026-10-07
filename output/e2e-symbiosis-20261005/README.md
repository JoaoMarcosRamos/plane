# Evidências — E2E da simbiose 1.8 (05/10/2026)

Relatório, achados e limites: [E2E_SYMBIOSIS.md](../../docs/radar/E2E_SYMBIOSIS.md). Sem deploy; stack local `plane-radar` deste worktree.

## Resultado

- **Execução limpa e única (`all`), workspace `radar-e2e-clean`: 68/68 verificações aprovadas** — [log](e2e-clean-run.log), [estado](e2e-state-radar-e2e-clean.json), [screenshots](radar-e2e-clean/), [PostgreSQL](radar-e2e-clean/db-evidence.json). Modelo scripted no Deep Agents real.
- **Provider real** (`anthropic:claude-sonnet-4-6`), workspace `radar-e2e`: uma execução validada pelos dois serviços e decidida pelo humano; 9 verificações — [estado](e2e-state.json) (`provider`), [log CoS](cos-runtime-provider.log), screenshots 13–15.
- Workspace `radar-e2e` também guarda a execução incremental em que o script foi desenvolvido (screenshots 01–12, [banco](db-evidence.json)). Uma entrada FAIL ali é uma expectativa de teste incorreta, anotada como `superseded_by` no próprio estado.
- Regressão backend após a correção de CORS: **972/972** (272 RADAR + 700 Plane), zero skipped, com o [servidor de integração](../phase1-bench-20261005/cos-http-server.py) em :8937 — [log](backend-regression.log), [JUnit](../../apps/api/output/e2e-symbiosis-20261005/backend-regression.xml). Comando: o da [bancada da Fase 1](../phase1-bench-20261005/README.md) com projeto `radar-e2e-regression-20261005`.

## Componentes

| Camada | Execução |
| --- | --- |
| Navegador | Chromium headless (Playwright embutido no `playwright-cli`), login e-mail/senha real do Plane |
| Web | `react-router dev --port 3000` em `apps/web`; shell completo, App Rail, editor e seletores reais |
| API/banco | `docker compose -p plane-radar … -f docker-compose.e2e.yml`; API :8001, PostgreSQL :5434, migrations RADAR 0001–0010 |
| Runtime | [cos-runtime-server.py](cos-runtime-server.py): router `agent_runtime` e `DeepAgentsAdapter` do COS_AGENT_V2 em :8940 (loopback); modo `scripted` ou `provider` |
| Transporte | URL/chave em `.secrets/radar-e2e-runtime.env` (gitignored, gerada por ambiente), injetadas no API por [docker-compose.e2e.yml](docker-compose.e2e.yml) |

Contas de teste e senhas aleatórias ficam em `.secrets/` (gitignored); sessões do navegador em `.secrets/e2e-auth/`, apagadas no teardown.

## Reprodução

```sh
# Raiz do worktree. 1) chave de transporte (uma vez) e stack
python3 -c "import secrets;print('RADAR_AGENT_RUNTIME_URL=http://host.docker.internal:8940/agent-runtime/v1');print('RADAR_AGENT_RUNTIME_TOKEN='+secrets.token_urlsafe(48))" > .secrets/radar-e2e-runtime.env
docker compose -p plane-radar -f docker-compose-local.yml -f docker-compose.radar.yml -f output/e2e-symbiosis-20261005/docker-compose.e2e.yml up -d
(cd apps/web && ./node_modules/.bin/react-router dev --port 3000)

# 2) runtime CoS (outro terminal); trocar scripted por provider para o modelo configurado no CoS
set -a; . ./.secrets/radar-e2e-runtime.env; set +a
../COS_AGENT_V2/.venv/bin/python output/e2e-symbiosis-20261005/cos-runtime-server.py scripted /tmp/radar-e2e-ledger.sqlite

# 3) provisionamento administrativo (contas, workspace, Person, binding plane, grant + CreateAction)
set -a; . ./.secrets/radar-e2e-users.env; set +a
docker exec -i -e RADAR_E2E_SLUG=radar-e2e-clean -e RADAR_E2E_MEMBER_PASSWORD -e RADAR_E2E_GUEST_PASSWORD -e RADAR_E2E_OUTSIDER_PASSWORD \
  plane-radar-api-1 python manage.py shell --settings=plane.settings.local < output/e2e-symbiosis-20261005/provision.py

# 4) E2E completo: login create bind review decide object-page verify-db permissions
cd output/e2e-symbiosis-20261005 && RADAR_E2E_SLUG=radar-e2e-clean node e2e.mjs all
# Provider real (opt-in, consome completions): servidor em modo provider, depois
node e2e.mjs provider provider-decide
```

`.secrets/radar-e2e-users.env` contém `RADAR_E2E_{MEMBER,GUEST,OUTSIDER}_PASSWORD`; o login do tester vem de `.secrets/radar-dev-login.md`. O script lê credenciais dos arquivos e nunca as imprime. `RADAR_E2E_CHROMIUM` permite apontar outro executável Chromium.

## Tentativas registradas

O desenvolvimento do script expôs o bloqueio CORS (primeira criação falhou com `Request header field idempotency-key is not allowed`; ver [log de rede](browser-network.log)). Depois da correção, ajustes foram apenas de seletores do script (agente sem pré-seleção, checkbox Base UI) e do verificador (aprovação termina `consumed`; status `executed` também quando só a aprovação é consumida). Nenhuma alteração de produto além da correção de CORS.

## Teardown

Ver [E2E_SYMBIOSIS.md](../../docs/radar/E2E_SYMBIOSIS.md#teardown). Os workspaces `radar-e2e` e `radar-e2e-clean` permanecem no banco local da stack `plane-radar` como evidência consultável.
