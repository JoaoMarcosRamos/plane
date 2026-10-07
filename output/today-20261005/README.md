# Validação local — Today (05/10/2026)

Contrato e comportamento: [TODAY.md](../../docs/radar/TODAY.md).

## Checks executados

- `pnpm --filter web test:radar`: **77 aprovados** ([log](web-tests.log)).
- `pnpm --filter web check:types`: exit 0, incluindo typegen + tsc; output acompanhado na sessão de implementação.
- OxLint com `--deny-warnings` nos componentes/services/stores/routes RADAR: zero warnings/errors ([log](web-lint.log)).
- Oxfmt dos 11 arquivos frontend alterados: aprovado ([log](web-format.log)).
- Ruff check dos cinco arquivos backend alterados: aprovado ([log](backend-style.log)).
- Backend completo: [log inicial](backend-tests.log), 238 coletados, 231 aprovados, quatro opt-in skipped, três fixtures novos com falha inicial.
- Reexecução após corrigir os fixtures: [log final Today](today-final-tests.log), **9/9 aprovados**. Total combinado: **234 backend únicos aprovados**; os seis casos Today que já passaram na execução inicial não são somados duas vezes.

Os skips pertencem à integração HTTP/provider e adapter CoS opt-in, sem montagem/configuração do CoS neste stack. A primeira execução também registrou falha de criação do build cache Docker antes de testes; usou-se em seguida a imagem de testes local `plane-radar-api`, com código atual montado em `/code`. Nenhuma configuração de produto foi modificada para contornar o ambiente.

```sh
docker compose -f docker-compose-test.yml -f output/today-20261005/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests -q
docker compose -f docker-compose-test.yml -f output/today-20261005/docker-compose.override.yml run --rm api-tests pytest plane/radar/tests/test_today.py -q
```

## Navegador e persistência

O [servidor de fixture](plane-ui-server.py) aplica migrations ao PostgreSQL descartável do stack de teste e provisiona Objects/grants/run/propostas sintéticos. Modelo remoto substituído somente na fixture; `save_review` e os endpoints de produto são reais. Autenticação sintética pertence exclusivamente ao wrapper WSGI de teste. O [preview](ui-preview-source/main.tsx) importa Today, Risk Review, Object Page e os stores de produto; substitutes de editor/membership vêm da fixture anterior. Nenhuma dessas substituições entra nas routes de produto.

Validações realizadas com agent-browser/Chrome isolado:

- Quatro seções, um risco relevante, uma decisão pendente, uma ação vencida e duas propostas pendentes inicialmente.
- Risco fechado e ação concluída excluídos.
- Link da sugestão abriu o run/proposta corretos, com Accept/Edit/Reject e evidências.
- Reject de relação sintética confirmado por POST 200; retorno a Today mostrou somente a ação sugerida pendente.
- Link de risco abriu sua Object Page com score 20 e propriedades persistidas.
- Mobile 390 × 844 sem overflow horizontal; desktop sem overlay/erros na tela populada.
- Workspace vazio real mostrou quatro mensagens de vazio; workspace indisponível mostrou alert + Atualizar sem listas obsoletas.

Screenshots: [desktop](today-desktop.png), [mobile](today-mobile.png), [vazio](today-empty.png), [erro](today-error.png). [Requests HTTP reais](plane-ui-server-final.log). O preview foi reiniciado para aplicar a troca de workspace da fixture, pois o watcher não atualizou a fonte sob `output/`.

Limites: shell/login/provider reais e piloto não homologados, sem deploy. Não houve reexecução da suíte CoS nem alteração de schema. Os servidores de preview, Chrome isolado e stack descartável são encerrados ao final da validação.
