# Evidências — validação geral 0–1.4

Data: 04/10/2026. Validação local e correção do recorte de propriedades autorizadas. Relatório: [GENERAL_VALIDATION_REPORT.md](../../docs/radar/GENERAL_VALIDATION_REPORT.md).

## Ambientes

Projeto Compose exclusivo `radar-general-validation-20261004`, com PostgreSQL, Valkey, RabbitMQ e MinIO descartáveis. Imagem API local `plane-radar-api`. O override monta COS_AGENT_V2 somente para leitura; ajustar o caminho absoluto antes de reproduzir em outra máquina.

Servidor HTTP CoS determinístico na porta 8926, sem provider ou tools pessoais; SQLite próprio em `/private/tmp/radar-general-validation-20261004.sqlite`. O script preservado contém somente a chave pública exclusiva de teste. O PostgreSQL CoS separado usa o container `radar-general-validation-cos-db`, publicação apenas em loopback e credenciais públicas de teste.

## Reprodução

Executar o servidor de teste em um terminal separado:

```sh
../COS_AGENT_V2/.venv/bin/python output/general-validation-20261004/cos-http-server.py
```

Regressão backend com migrations reais em banco vazio:

```sh
docker compose -p radar-general-validation-20261004   -f docker-compose-test.yml   -f output/general-validation-20261004/docker-compose.override.yml   run --rm api-tests sh -c 'python manage.py check && python manage.py makemigrations --check --dry-run && pytest plane/radar/tests plane/tests --migrations --create-db -q'
```

CoS completo com PostgreSQL dedicado (a porta foi atribuída dinamicamente nesta execução):

```sh
docker run -d --name radar-general-validation-cos-db   -e POSTGRES_USER=radar_test -e POSTGRES_PASSWORD=radar_test_only   -e POSTGRES_DB=radar_test --tmpfs /var/lib/postgresql/data   -p 127.0.0.1::5432 postgres:15.7-alpine
docker exec radar-general-validation-cos-db pg_isready -U radar_test -d radar_test
# Copiar a porta exibida para a URL abaixo e executar no checkout CoS.
docker port radar-general-validation-cos-db 5432
RUN_LIVE_AGENT_EVAL=0   TEST_POSTGRES_DATABASE_URL='postgresql+psycopg://radar_test:radar_test_only@127.0.0.1:PORTA/radar_test'   .venv/bin/python -m pytest tests
```

Frontend e checks, a partir do checkout Plane:

```sh
pnpm --filter web test:radar
pnpm --filter web check:types
pnpm exec turbo run check --concurrency=2
../COS_AGENT_V2/.venv/bin/ruff check apps/api/plane/radar
# Executar no checkout CoS: .venv/bin/ruff check app tests
```

O teste red/green usou o banco `test_plane_context_fast` no PostgreSQL CoS separado, criado por Django com `--nomigrations`. Uma tentativa de regressão completa do código corrigido nesse banco foi interrompida pelo encerramento do container compartilhado. O passe definitivo foi refeito em container próprio: `pytest plane/radar/tests --migrations -q`, reutilizando o banco já migrado do projeto Compose. Resultado: 202 RADAR passaram. Os comandos de reprodução acima executam o código atual com migrations reais em uma única suíte.

## Artefatos e tentativas

- `backend-tests.log` / `apps/api/output/general-validation-20261004/plane-tests.xml`: replay real do histórico Django em banco vazio e suíte coletada antes da inclusão dos três novos testes.
- `backend-final-tests.log` / `apps/api/output/general-validation-20261004/radar-final-tests.xml`: regressão definitiva de 202 testes RADAR do código corrigido, incluindo os três novos, sobre banco com migrations reais.
- `backend-full-source-interrupted.log`: tentativa de 902 casos interrompida quando o container da suíte anterior encerrou; não é resultado final e não tem JUnit de conclusão.
- `context-red.log/xml` e `context-green.log/xml`: reprodução funcional e correção. XMLs ficam em `apps/api/output/general-validation-20261004/`.
- `cos-tests.log/xml`: suíte CoS final com PostgreSQL dedicado. `cos-initial-invalid-db-url.xml` registra a primeira tentativa: URL vazia definida incorretamente no comando de teste; corrigida na execução final. Nenhuma alteração de código CoS foi necessária.
- `workspace-check.log`: primeiro check, interrompido pela formatação do teste RADAR. `workspace-check-final.log`: check completo após ajuste.
- `backend-startup-failed.log` e `backend-startup-retry-failed.log`: falhas de cookie/owner do RabbitMQ antes da correção.
- `context-migration-diagnostic.log`: tentativa separada com replay completo, interrompida para diagnosticar o custo de renderização de migrations Django. Não é resultado funcional. `context-initial-db-in-use.log/xml`: tentativa subsequente que encontrou conexão remanescente; o teste funcional foi refeito em outro banco próprio.
- `web-tests.log`, `web-types.log`, `web-radar-lint.log`, `web-radar-format.log`, `backend-lint.log`, `backend-format.log`, `cos-lint.log`, `cos-format.log` e `migrations.log`: checks e regressões.

Não somar tentativas, testes focados ou a suíte anterior à regressão final: há sobreposição. Manifestos/resultados da entrega 1.4 não foram reescritos.

## Resultado final

202 RADAR atuais + 700 Plane + 1.170 CoS + 58 frontend = **2.130 casos únicos aprovados**. Nove avaliações CoS opt-in ignoradas; zero falhas/erros nas suítes finais. Não somar os 199 RADAR anteriores de `plane-tests.xml`, pois foram revalidados no passe de 202. Monorepo: 56 tarefas concluídas; checks estritos RADAR e Ruff aprovados. Ver [result.json](result.json) e [manifest.json](manifest.json).

## Teardown

Somente recursos criados por este passe:

```sh
docker compose -p radar-general-validation-20261004   -f docker-compose-test.yml   -f output/general-validation-20261004/docker-compose.override.yml down -v
docker rm -f radar-general-validation-cos-db
```

Encerrar também o servidor de teste da porta 8926. Nenhuma stack publicada participa desta validação.

Teardown executado ao final: projeto Compose, PostgreSQL CoS e servidor HTTP encerrados; SQLite temporário removido. Stacks existentes permaneceram intactas.
