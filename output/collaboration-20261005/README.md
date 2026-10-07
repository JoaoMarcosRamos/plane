# Validação local — colaboração mínima RADAR (05/10/2026)

Contrato, avaliação de necessidade e pendências: [COLLABORATION.md](../../docs/radar/COLLABORATION.md). Sem deploy; trabalho sobre o worktree existente, com outras alterações prévias preservadas.

## Resultado final

- **263 backend RADAR aprovados, quatro opt-in skipped**, em uma única regressão final: [log](backend-regression-final.log), [JUnit](../../apps/api/output/collaboration-regression-final.xml). Inclui 28 casos novos de colaboração e um caso novo de capabilities human-only. Os quatro skips são integrações runtime/CoS/provider opt-in já existentes; CoS não foi alterado/reexecutado nesta fase.
- **92 frontend aprovados**: [log](web-tests.log). Inclui 15 novos testes de transporte, MobX e markup; mocks isolados frontend não comprovam persistência.
- Typegen + TypeScript exit 0 ([tsc](web-types.log)); OxLint zero warnings/errors ([log](web-lint.log)); Oxfmt dos nove arquivos frontend aprovado ([log](web-format.log)). Ruff em todo `plane/radar` e migration check (`No changes detected`) aprovados no log backend final. Migration 0010 aplicada tanto no banco de testes quanto no banco descartável da fixture HTTP.
- [Upload/replay/download HTTP reais](http-upload-evidence.json), [hash do download UI](browser-download-evidence.json) e [estado confirmado no PostgreSQL](browser-db-evidence.log).

Não somar reexecuções aos números finais. A primeira execução falhou por um NameError introduzido em `run_internal`, corrigido antes da regressão. A segunda teve 22 passes e dois asserts incorretos (campo `evidence_ids` confundido com bytes e 401 esperado como 403), corrigidos. Uma execução de Ruff detectou import não usado após expandir a consulta de provenance, corrigido. [Regressão anterior](backend-regression.log), [28 casos focados](backend-final.log) e [regressão final](backend-regression-final.log) conservam essa evolução; o resultado final é a autoridade.

## Comandos reproduzíveis

```sh
# PostgreSQL/Valkey/RabbitMQ/MinIO separados do stack Plane em uso.
# A imagem local de testes é reutilizada; o código atual é montado em /code.
docker compose -p radar-collaboration-test -f docker-compose-test.yml -f output/collaboration-20261005/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests --junitxml=output/collaboration-regression-final.xml

# A partir de apps/web:
./node_modules/.bin/react-router typegen
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/vitest run --config vitest.radar.config.ts

# A partir da raiz:
./node_modules/.bin/oxlint --deny-warnings apps/web/components/radar/collaboration-panel.tsx apps/web/components/radar/collaboration-panel.test.ts apps/web/components/radar/object-page.tsx apps/web/services/radar/collaboration.types.ts apps/web/services/radar/radar.service.ts apps/web/services/radar/radar.service.test.ts apps/web/store/radar/collaboration.store.ts apps/web/store/radar/collaboration.store.test.ts apps/web/store/radar/provider.tsx
```

Os comandos `pnpm --filter web ...` tentaram reinstalar dependências e abortaram por falta de TTY; usaram-se os binários já instalados correspondentes, sem alterar lockfile/dependências. Typegen ocorreu antes de tsc. A suíte completa Plane fora de RADAR não foi reexecutada nesta fase; a regressão é o conjunto RADAR completo.

## Navegador → sessão → API → PostgreSQL

A [fixture HTTP](plane-ui-server.py) cria usuários/roles/Objects sintéticos no Compose isolado e fornece login **somente de fixture** usando `APIClient.force_login`, gerando sessão Django normal. Requests de produto passam por `BaseSessionAuthentication`, membership e endpoints reais. Nenhuma force-authentication é injetada nas requests de produto e nenhum produto recebeu alteração de permissões para o teste.

O [preview](ui-preview-source/main.tsx) importa Object Page, collaboration panel, provider, services e stores de produto. Editor e hook visual de membership são substituídos somente na fixture; a autorização backend e flags de autoria são reais. Isso não homologa shell/login completo do Plane.

Agent-browser 0.38.2 foi obtido via npm com cache em `/private/tmp`; não conseguiu iniciar Chrome, mesmo em execução permitida fora do sandbox. A verificação prosseguiu pela extensão Chrome/Computer Use com uma aba exclusiva.

Validado na UI:

1. Author criou comentário e editou; reload preservou texto e activity. Object.version permaneceu 1 e comment.revision avançou para 2.
2. Arquivo sintético foi enviado pelo [script HTTP multipart](verify-http-upload.py), replay retornou o mesmo resultado e download HTTP preservou bytes/hash. A UI recarregou o anexo, fez rename para `licenciamento.txt` e iniciou download. A extensão não capturou o evento de download, mas o arquivo apareceu em Downloads e SHA-256 coincidiu com o original.
3. Outro member pôde comentar/download, sem Edit/Rename/Remove para itens alheios; guest teve leitura/download e nenhum controle de mutação.
4. Admin viu remoção, sem direito de editar comentário/filename alheio. Confirm removal ocultou o anexo e adicionou `DeleteAttachment` à activity. [Consulta PostgreSQL](verify-db.py) comprovou author original, admin em updated_by/provenance, bytes íntegros retidos e revision 3.
5. Outsider recebeu Object unavailable/403. Nenhum erro de console foi observado no fluxo bem-sucedido do author; os 403 do outsider são esperados.

Screenshots: [author](ui-author.png), [outro membro](ui-other-member.png), [guest](ui-guest.png), [remoção admin](ui-admin-removal.png), [outsider](ui-outsider.png). [Requests reais](plane-ui-server.log). Não houve chamadas a endpoints de Issue no componente de colaboração.

**Limite explícito:** seleção/submissão de arquivo pela UI não foi homologada. O upload via extensão exigiu “Allow access to file URLs”, ausente; não foi habilitado. O seletor nativo não forneceu caminho utilizável durante a automação. Upload HTTP, falhas/rollback no backend e transporte/estado da UI têm evidência separada, sem alegar E2E de upload visual.

## Pendências e teardown

Antes do piloto: upload em navegador comum e sessão/shell reais; política de arquivo/scanning, quotas, retenção/purge, capacidade/backup do PostgreSQL e proxy/timeouts; loop completo com provider real; aplicação de migrations e release reproduzível Plane/CoS. Não há realtime, threads, presença ou notificações nesta entrega.

O stack `radar-collaboration-test`, preview e aba de teste são encerrados ao final. O stack Plane já aberto não foi reiniciado, migrado nem removido. [Teardown](teardown.log). O download sintético em Downloads foi removido após conferir o hash; o arquivo-fonte e a evidência permanecem neste diretório.
