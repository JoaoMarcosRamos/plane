# Evidências — Fase 1.3 RADAR Agent Runtime

Data: 04/10/2026. Destino: COS_AGENT_V2. Desenvolvimento local, sem ativação de produção.

- `manifest.json`: lista fechada de 22 arquivos CoS com SHA-256 anterior e preparado.
- `before/`: cópia anterior dos arquivos existentes, capturada após conferir a baseline.
- `prepared/`: implementação validada e preparada para transferência.
- `cos-runtime.patch`: diff revisável entre essas duas versões.
- `cos-prepared-tests.xml` e `cos-agent-runtime-final-tests.log`: regressão de 95 testes na preparação.
- `plane-tests.xml` e `radar-agent-backend-final-tests.log`: suíte RADAR final em PostgreSQL isolado.
- `radar-agent-final-facade-tests.log`: 13 testes da fachada, incluindo HTTP entre processos.
- `cos-destination-tests.xml`, `cos-destination-tests.log`, `result.json`: validação após aplicar ao destino real.

O manifesto protege contra alterações concorrentes no destino. Nenhum `.env`, conteúdo pessoal, banco existente, `.venv` ou arquivo Git é transferido.

Comando backend utilizado:

```sh
docker compose -p radar-agent-runtime-tests \
  -f docker-compose-test.yml -f /private/tmp/radar-agent-runtime-tests.yml \
  run --rm api-tests sh -c 'python manage.py makemigrations --check --dry-run && pytest plane/radar/tests --migrations -q --junitxml=/code/output/agent-runtime-20261004/plane-tests.xml'
```

O override usa a imagem existente `plane-radar-api`, monta o CoS preparado somente para leitura e aponta o teste HTTP para um servidor temporário com o adapter real, SQLite separado e geração determinística. O grafo Deep Agents real é verificado separadamente com modelo scripted. Sem provider, Telegram ou dados de produção.

Contrato e limites: [AGENT_RUNTIME.md](../../docs/radar/AGENT_RUNTIME.md).
