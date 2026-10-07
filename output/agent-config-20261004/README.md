# Evidências — Fase 1.4 Agent Config

Data: 04/10/2026. Desenvolvimento local no Plane e COS_AGENT_V2, sem ativação de ambiente publicado.

## Escopo

Identity/Soul, Role, Policies e Permissions persistidos em PostgreSQL, com migration RADAR 0007, versão otimista e provenance. UI em RADAR → Agent configuration. Contexto restringido pelo grant vigente e pela configuração; cópia versionada em cada run CoS. Nenhuma tool de mutação ou memória longa adicionada.

## Nota de reexecução

O override abaixo é o artefato histórico da entrega. O passe geral posterior encontrou diferença de UID/GID na imagem RabbitMQ Alpine disponível e corrigiu broker/health check e tmpfs no Compose de testes. Para reexecutar a validação atual, seguir os [comandos e override do passe geral](../general-validation-20261004/README.md), com seu servidor HTTP e banco próprios. O override histórico com UID/GID 999 não deve ser combinado com a configuração atual da imagem Alpine.

## Comandos históricos

O `docker-compose.override.yml` preservado nesta pasta usa a imagem local `plane-radar-api`, monta COS_AGENT_V2 somente para leitura e corrige o owner do tmpfs RabbitMQ para o UID/GID da imagem. Ajustar o caminho absoluto do mount para reproduzir em outra máquina.

```sh
# CoS: servidor de teste temporário com adapter real e geração determinística.
# O script preservado usa SQLite próprio e o token público exclusivo de teste.
../COS_AGENT_V2/.venv/bin/python output/agent-config-20261004/cos-http-server.py

# Plane: banco descartável separado das stacks de desenvolvimento.
docker compose -p radar-agent-config-tests \
  -f docker-compose-test.yml \
  -f output/agent-config-20261004/docker-compose.override.yml \
  run --rm api-tests sh -c 'python manage.py makemigrations --check --dry-run && pytest plane/radar/tests --migrations -q --junitxml=/code/output/agent-config-20261004/plane-tests.xml'

# Frontend.
pnpm --filter web test:radar
pnpm --filter web check:types

# CoS: executar dentro do checkout COS_AGENT_V2.
.venv/bin/python -m pytest \
  tests/unit/test_product_agent_config.py \
  tests/unit/test_agent_runtime_product.py \
  tests/agent/test_product_runtime_engine.py \
  tests/unit/test_radar_api.py \
  tests/unit/test_radar_command_runtime.py \
  tests/unit/test_radar_config.py \
  tests/unit/test_radar_operation_repository.py \
  tests/unit/test_migrations.py \
  tests/integration/test_radar_approval_flow.py \
  tests/agent/test_radar_surface.py -q

# Plane: teardown somente da stack temporária criada para esta fase.
docker compose -p radar-agent-config-tests \
  -f docker-compose-test.yml \
  -f output/agent-config-20261004/docker-compose.override.yml down -v
```

A configuração Compose monta o CoS em `/cos`; o servidor HTTP usa porta 8915, endereço `host.docker.internal` e arquivo SQLite em `/private/tmp`. `cos-http-server.py` conserva os caminhos da máquina desta validação; ajustar antes de reproduzir. Não usa provider, Telegram ou dados reais.

## Artefatos

- `backend-tests.log` e `apps/api/output/agent-config-20261004/plane-tests.xml`: regressão backend final, com migrations e HTTP entre processos.
- `cos-regression.log/xml`: regressão final selecionada CoS; `cos-tests.log/xml` é o subconjunto inicial de 28 testes.
- `web-tests.log`, `web-types.log`, `web-lint.log`, `web-format.log`: testes e checks frontend.
- `manifest.json` e `result.json`: hashes dos 37 arquivos capturados no encerramento da implementação e resultado final verificável. O manifesto é histórico; revisões posteriores de documentação não reescrevem seus hashes. A revisão documental subsequente está registrada em [documentation-update.json](documentation-update.json).
- `migration-generation.log`: geração de 0007; o teste inicial aplicou o histórico de migrations ao banco vazio.
- `backend-config-tests.log` e `config-tests.xml`: execução inicial; encontrou fixture Risk sem description obrigatória. Fixture corrigida e revalidada na regressão final, incluindo HTTP configurado.
- `ui-saved.png`, `ui-permissions-saved.png`, `ui-readonly.png` e snapshots `.txt`: formulário real e store MobX em fixture isolada.
- `ui-preview-source/`: fonte da fixture temporária removida de `apps/web` após verificação. Para reproduzir, copiar index/main para `apps/web/.agent-config-preview/`, config para `apps/web/agent-config-preview.config.ts` e executar `pnpm --filter web exec vite --config agent-config-preview.config.ts`.

## Verificação de UI

Chrome via Computer Use, após o CLI agent-browser não conseguir iniciar um Chrome no sandbox. A fixture importa o formulário e store de produção e persiste dados sintéticos em localStorage, simulando versão concorrente; não substitui o backend autoritativo.

Verificado: os quatro blocos renderizam com primitives reais; save incrementa versão e mostra confirmação; refresh mantém Identity/Role/guidelines; seleção de Object é salva; uma segunda aba com versão antiga recebe conflito e mantém rascunho; reload restaura a versão vigente; modo viewer desabilita inputs/checkboxes e oculta save. Console sem erros. O teste unitário de rendering também usa a entrada observável real do store para cobrir clonagem de Proxy.

Backend e transporte foram verificados separadamente contra PostgreSQL e o adapter HTTP real. Não houve homologação do shell completo com login real, provider real, TLS remoto ou piloto.

Contrato: [AGENT_CONFIG.md](../../docs/radar/AGENT_CONFIG.md).

## Resultado final

- Backend RADAR: **199 passaram**, zero falhas/erros/skips; 22 testes de configuração incluídos.
- CoS selecionado: **67 passaram**, zero falhas/erros/skips; os 28 iniciais são um subconjunto.
- Frontend RADAR: **58 passaram**, em 8 arquivos.
- TypeScript, lint sem warnings nos arquivos da fase, formatação, Ruff e migration check aprovados.
- Formulário no Chrome: save, refresh, Object scope, conflito/reload e viewer aprovados; console sem erros.
- Serviços temporários encerrados; fixtures sintéticas e chave de transporte exclusiva de teste, sem chamadas a provider/Telegram ou dados de produção.

Não houve commit ou deploy. Ativação exige atualizar ambos os serviços e aplicar migration 0007/provisionamento no ambiente escolhido.
