# Validação — correções U0 do RADAR Core

Concluída em 06/10/2026 (America/Bahia); a pasta conserva a data inicial do trabalho. Escopo e decisões: [CORE_U0_REPORT.md](../../docs/radar/CORE_U0_REPORT.md).

## Resultado final

- **301 backend aprovados e 4 integrações opt-in skipped**, em uma única regressão final: [log](backend-final.log), [JUnit](../../apps/api/output/core-u0-final.xml). Inclui 33 casos U0 novos e as fixtures existentes adaptadas à fronteira de escrita.
- **93 frontend aprovados**: [log final](web-tests-final.log), 14 arquivos. O caso novo cobre o máximo 1..1 no seletor, nos dois sentidos.
- Ruff, formatação Python e `makemigrations radar --check --dry-run` passaram no log backend final: `No changes detected`. [TypeScript](web-types-final.log), [OxLint](web-lint.log) e [Oxfmt](web-format.log) passaram com exit 0.
- **Migration 0011:** upgrade, downgrade e novo upgrade em banco isolado; duas regras legadas backfilled, tipo customizado e identidades preservados. [Log](migration-retry.log), [resultado](../../apps/api/output/core-u0-migration.json), [script com modelos históricos](../../apps/api/output/core-u0-verify-migration.py).
- [Manifesto de fontes](source-manifest.json) registra hashes finais e hashes da base local desta tarefa; [arquivos](changed-files.json). A base contém mudanças staged/unstaged/untracked anteriores, portanto o diff contra HEAD não equivale ao diff desta entrega.

## Reprodução

Pré-requisito: `apps/api/.env` já existente e imagem local `plane-radar-api`. O override reutiliza essa imagem e monta o código atual em `/code`. Executar os comandos abaixo na raiz do repositório.

```sh
docker compose -p radar-core-u0-test -f docker-compose-test.yml -f output/core-u0-20261005/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests --junitxml=output/core-u0-final.xml

# Em um stack descartável novo: o script cria fixtures na base plane, separada de test_plane.
docker compose -p radar-core-u0-test -f docker-compose-test.yml -f output/core-u0-20261005/docker-compose.override.yml run --rm -e PYTHONPATH=/code api-tests python output/core-u0-verify-migration.py

# Encerramento exclusivamente do stack de validação.
docker compose -p radar-core-u0-test -f docker-compose-test.yml -f output/core-u0-20261005/docker-compose.override.yml down -v
```

A partir de `apps/web`, usar os binários instalados:

```sh
./node_modules/.bin/vitest run --config vitest.radar.config.ts
./node_modules/.bin/tsc --noEmit
```

## Histórico de validação e limites

A execução inicial foi interrompida após confirmar que fixtures antigas gravavam fora do command. A primeira regressão terminou com 9 falhas: duas fixtures de colaboração ainda diretas e sete fluxos de retomada que reenviavam `rules_contract` como input desconhecido. Essas falhas foram corrigidas; `command_envelope` agora seleciona somente os campos declarados do comando. A [revalidação integrada](backend-integration-final.log) passou com 100 testes e 2 skips, antes da última proteção adicional para writes internos em Objects vinculados. O resultado autoritativo é a regressão final acima.

A primeira chamada do script de migration falhou antes da execução por import path; a reprodução registra `PYTHONPATH=/code`. Execuções intermediárias de lint identificaram import ausente e formatação nas novas fixtures, corrigidos antes dos checks finais. Logs intermediários ficam como histórico, sem serem usados como resultado aprovado.

Os quatro skips da regressão completa são testes de runtime/CoS/provider que exigem opt-in. COS_AGENT_V2 e provider real não foram reexecutados. A suíte completa Plane fora de RADAR e o navegador não foram reexecutados; a mudança visual limita-se ao filtro de candidatos, com teste frontend. Não houve deploy, migração do stack Plane em uso, alteração de credenciais ou dependências.

O helper de escrita histórica existe somente nos testes e envolve chamadas ORM individuais. Requests e commands de produto executam os guards reais; não existe bypass autouse ou flag de produção.
