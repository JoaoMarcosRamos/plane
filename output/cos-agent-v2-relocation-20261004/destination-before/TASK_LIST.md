# TASK_LIST.md — Personal Chief of Staff

Este arquivo é o acompanhamento executável do [PLAN.MD](PLAN.MD). O plano continua sendo a fonte de verdade para escopo, ordem e critérios; esta lista apenas transforma o plano em tarefas rastreáveis e registra o estado observado no repositório.

Última revisão: 2026-10-01 (integração RADAR portada ao JMR_Personal-CoS)

## Legenda

- `[x]` implementado ou verificado no repositório;
- `[~]` parcialmente implementado ou aguardando validação prática;
- `[ ]` pendente.

## Estado atual

| Área | Estado |
| --- | --- |
| Fase atual | Integração RADAR no ar na VPS (ADR-027, página 041): agente do JMR com o vault real, pacote `radar-vault` 0.5.0; escritas aprovadas liberadas, ainda sem validação de ponta a ponta |
| Próxima fase | Validar uma escrita aprovada de ponta a ponta e decidir `RADAR_MANAGER_CONTEXTS` para delegar ações de outras pessoas |
| Sequência definida pelo plano | Integração RADAR no JMR → deploy do agente → vault inicializado → leituras → escritas aprovadas → aceitação live |
| Suíte de testes | 1.128 testes passaram e 11 opt-in foram ignorados em 2026-10-01 (`pytest`, `ruff check` limpo, uma só head Alembic `20260927_0012`). Abrange a integração RADAR, a API sintética do M10 e as superfícies Notion/Calendar/Gmail |
| Superfície do board | Tarefas: 13 colunas mapeadas (título, status, prazo, projeto, prioridade, macro-contexto, lista, pessoas, departamentos, delegação, periodicidade, inbox, próxima ação). Projetos: 7 (nome, status, tipo, prioridade, setor, responsável, % concluído) |
| Modelo em uso | Definido por `AGENT_MODEL=provider:modelo`; providers suportados: Anthropic e OpenAI |
| Superfície pronta para o agente | O Chief publica Reminders, Memory e `read_url` sempre; e, quando cada integração está configurada, as cinco tools do Notion mais `save_reference` e o fallback MCP, `list_events`/`create_event`/`update_event`/`find_available_slots`, e `search_email`/`read_email`/`draft_email` — nunca `send_email`. Cada filho (`task-agent`, `calendar-agent`, `email-agent`) só é compilado quando o domínio dele está ativo, e recebe apenas leituras do domínio, filesystem read, scratch sob `/tmp/subagents/**`, memória/lembretes read-only, `read_url` e MCP Notion read-only |
| Entrada do agente | `app.agent.run_agent()` → `AgentRun(run_id, status, reply, tool_calls, execution_error, messages)` |
| Ambiente publicado | VPS Contabo, stack `jmr-personal-cos` em `~/apps/jmr-personal-cos` (agente ainda parado; PostgreSQL em `127.0.0.1:5436`), `PUBLIC_HOST=jmr-personal-cos.kqfrop.easypanel.host`, porta do agente 8002. O Personal-CoS de desenvolvimento segue em `personal-cos` e o `radar-cos-v1` em `radar-cos-v1`, ambos intactos |
| Comando de operação na VPS | `cd ~/apps/jmr-personal-cos && docker compose -f docker-compose.yml -f docker-compose.prod.yml …`; o build exige `GITHUB_TOKEN` (secret do BuildKit) com leitura em `JMR_RADAR_ONTOLOGY`. Deploy por `git archive HEAD \| ssh contabo 'tar -x -C ~/apps/jmr-personal-cos'` |
| Canal Telegram | Pendente: criar um bot novo para o JMR (o `@JMR_deepagents_bot` do Personal-CoS atual não deve ser compartilhado) e registrar o webhook em `https://jmr-personal-cos.kqfrop.easypanel.host/webhooks/telegram` |

## Pendências abertas

Itens marcados `[~]` nas fases já percorridas, reunidos aqui para não se perderem no meio da lista:

| Pendência | Fase | Bloqueio |
| --- | --- | --- |
| Revalidar os nove comportamentos do agente com provider real e Notion falso | Fases 3–4 | Avaliação opt-in, incluindo “amanhã”, “sexta” e ISO com relógio fixo: `RUN_LIVE_AGENT_EVAL=1 pytest tests/agent/test_agent_live_evaluation.py` |
| Revalidar um fluxo controlado contra o workspace real, incluindo prazo relativo | Fases 1–4 | Exige credenciais e cria/atualiza dados reais; não foi executado automaticamente nesta revisão |
| Revalidar pelo Telegram os campos novos do board | Marco M1 | Continua aberta: os quatro cenários da Fase 15 exercitam título, prazo e status, mas não classificação. Filtrar por pessoa ou prioridade e usar a inbox pedem uso real, e é isso que o M1 propõe. O mapeamento já foi conferido contra o schema vivo |
| Campos deixados de fora por decisão | Decidida | `DATA DE EXECUÇÃO` e `Data lembrete` continuam fora do alcance do agente, por pertencerem ao fluxo manual. As demais colunas não expostas são fórmulas, rollups e relations auxiliares |
| Versionar o projeto em Git e trocar o `rsync` por `git clone`/`git pull` no deploy | Fase 13 | O diretório local não é um repositório Git, então a Fase 13 publicou por `rsync`. Nada mais no deploy depende dessa escolha |
| Validar uma escrita aprovada de ponta a ponta via MCP pelo Telegram | ADR-012 | Três defeitos encontrados no uso real e já corrigidos/publicados: (1) `HOME=/nonexistent` em `appuser` impedia o `npx` de enxergar o pacote pré-instalado; (2) `SYSTEM_PROMPT` não dizia ao modelo que as tools MCP existem nem que uma recusa por `approval_required` exige parar, causando `GraphRecursionError`; (3) `_approved_writes_context` (o replay do "sim") injetava um `ToolMessage` sem `AIMessage.tool_calls` correspondente — a Anthropic recusa isso com 400 (`BadRequestError`). Este terceiro bug **não é específico do MCP**: afeta qualquer replay de aprovação, incluindo `write_file`/`edit_file`/`delete`, e só agora foi exercitado contra o modelo real pela primeira vez. Busca, leitura, recusa e o replay do "sim" já foram confirmados em produção contra a API real. Falta só conferir no Notion que o payload aprovado foi de fato escrito. Ver `docs/development/020-notion-mcp-fallback.html` §8–12 |
| Executar aceitação live de Calendar, Gmail e do fluxo cross-domain | M4–M6 | A implementação, os testes herméticos e o smoke Docker/PostgreSQL estão concluídos; esta execução não recebeu refresh tokens nem autorização para criar dados na conta Google real |
| Mover busca sem diacríticos para o `radar-vault` | RADAR pós-0.3 | O host usa uma varredura autorizada de até 100 resumos para complementar a busca literal do pacote 0.3.0; uma release futura deve normalizar no índice do pacote e eliminar a observação extra e o limite de cobertura |

Fechada na Fase 13: construir/subir a imagem, validar `/health` e o `ZoneInfo("America/Bahia")` e executar a suíte dentro do Docker — o smoke de timezone passa no build e a suíte rodou no container contra PostgreSQL real.

## Definition of Done

Aplicar a cada fase e funcionalidade, conforme o [Definition of Done geral do PLAN.MD](PLAN.MD#2-definition-of-done-geral):

- [ ] Implementação completa e coerente com `SPEC.MD`.
- [ ] Type hints adicionados ao novo código.
- [ ] Tratamento de erros implementado.
- [ ] Testes essenciais criados e passando.
- [ ] Execução validada através do Docker.
- [ ] Nenhum secret incluído no código ou nos logs.
- [ ] Logging adequado para a operação.
- [ ] Funcionalidades existentes preservadas.
- [ ] Documentação HTML criada ou atualizada quando a unidade de desenvolvimento for relevante.
- [ ] `docs/index.html` atualizado quando uma nova página de documentação for criada.

### Estado do Definition of Done nas fases concluídas

| Critério | Fase 0 | Fase 1 | Fase 2 | Fase 3 | Fase 4 |
| --- | :---: | :---: | :---: | :---: | :---: |
| Implementação coerente com o `SPEC.MD` | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Type hints no novo código | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Tratamento de erros | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Testes essenciais passando | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Execução validada via Docker | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Nenhum secret no código ou nos logs | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Logging adequado | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Funcionalidades existentes preservadas | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |
| Documentação HTML | `[x]` 001 | `[x]` 002 + 005 | `[x]` 003 + 005 | `[x]` 004 + 005 | `[x]` 006 |
| `docs/index.html` atualizado | `[x]` | `[x]` | `[x]` | `[x]` | `[x]` |

A tabela acima nasceu cobrindo as Fases 0–4 e nunca foi estendida às Fases 5–12; o estado dessas fases continua registrado item a item nas seções correspondentes. A Fase 13 é auditada abaixo.

| Critério | Fase 13 | Evidência |
| --- | :---: | --- |
| Implementação coerente com o `SPEC.MD` | `[x]` | `docker-compose.prod.yml` sobrepõe o contrato existente sem alterar o `docker-compose.yml` |
| Type hints no novo código | `[x]` | não houve código novo de aplicação; a correção em `claim()` preservou a assinatura `(int) -> bool` |
| Tratamento de erros | `[x]` | `restart: unless-stopped`, healthcheck nos dois serviços e Compose que falha sem `POSTGRES_PASSWORD` |
| Testes essenciais passando | `[x]` | 301 no Docker com PostgreSQL 16 real; o teste opt-in de persistência foi o que expôs o bug do claim |
| Execução validada via Docker | `[x]` | build e `up -d` na VPS, containers `healthy` |
| Nenhum secret no código ou nos logs | `[x]` | `.env` criado no servidor com permissão `600`, fora do repositório e excluído da imagem pelo `.dockerignore` |
| Logging adequado | `[x]` | migrações e startup visíveis em `docker compose logs agent`, sem secret |
| Funcionalidades existentes preservadas | `[x]` | suíte completa verde após a correção do claim |
| Documentação HTML | `[x]` | `docs/development/013-vps-deployment.html`, com rollback e diagnóstico |
| `docs/index.html` atualizado | `[x]` | navegação, diário e mapa do projeto |

## Fases de implementação

### Extensão RADAR — Fase 1: fundação sem tools

[Referência no PLAN.MD](PLAN.MD#40-extensão-radar) ·
[Roteiro detalhado](docs/plans/radar-integration-roadmap.md#4-fase-1--fundação-da-integração-no-personal-cos)

- [x] Fixar `radar-vault 0.2.0` no commit imutável da tag `v0.2.0`.
- [x] Adicionar `RADAR_ENABLED`, vault, contexto, pessoa e allowlist de TBox ao `Settings`, Compose e `.env.example`.
- [x] Implementar gate completo, factory lazy thread-safe e lifecycle no lifespan.
- [x] Carregar Core, regras e políticas somente pela API pública do pacote.
- [x] Abrir apenas a ABox configurada e construir `Principal` a partir do usuário Telegram autorizado.
- [x] Executar preflight de TBox, schema legível, estrutura, pessoa/contexto e permissão de auditoria.
- [x] Degradar sem importar o pacote quando desligado/incompleto e sem publicar qualquer tool RADAR.
- [x] Montar `radar_abox` em `/data/radar-vault`, preparar ownership do runtime, provar que a imagem não copia ABox nem path local e validar persistência local após restart/rebuild com um container novo.
- [x] Cobrir flag off, configuração parcial, incompatibilidades, vault ausente/inválido/read-only, logs seguros e contrato de container.
- [x] Documentar configuração, permissões, backup, restore, rollback e os conceitos da fase em `028-radar-foundation.html`.
- [x] Validar na VPS que o bind mount sincronizado sobrevive a restart/rebuild e restaurar um snapshot em diretório isolado antes da Fase 2.
- [ ] Fixar a identidade do host no overlay de produção antes de trocar o volume nomeado pelo bind mount: o `appuser` da imagem (uid 100) não escreve no vault sincronizado, que pertence ao usuário do host.
- [ ] Definir cifragem, retenção e local do snapshot da ABox na VPS, e decidir o serviço de Obsidian Headless Sync, hoje fora de execução.

Critério de conclusão da fase:

- [x] `/health` e as demais integrações permanecem disponíveis em estado disabled/degraded.
- [x] Um vault descartável compatível chega a `ready` com pacote 0.2.0, TBox 3.1.0 e ABox 0.2.0.
- [x] O contrato Docker e o volume foram validados localmente e na VPS: preflight `ready` (pacote 0.2.0, TBox 3.1.0, ABox 0.2.0, 18 entidades), `/health` 200 e probe persistente após restart, recriação e rebuild. Na VPS o teste rodou em projeto Compose isolado sobre o vault sincronizado por Obsidian Sync, com restore de snapshot em diretório isolado e `diff -r` limpo; o vault vivo terminou sem alteração de conteúdo.

### Extensão RADAR — Fase 2: consultas específicas somente leitura

[Referência no PLAN.MD](PLAN.MD#fase-radar-2--consultas-somente-leitura) ·
[Roteiro detalhado](docs/plans/radar-integration-roadmap.md#5-fase-2--ferramentas-somente-leitura)

- [x] Criar `radar_search_entities`, `radar_read_entity`, `radar_get_context`, `radar_list_action_types` e `radar_validate_context`.
- [x] Manter `context`, identidade, grants, autonomia, paths e payload de operação fora dos schemas expostos ao modelo.
- [x] Limitar query, page/result size, profundidade de contexto, relações, action types e diagnósticos.
- [x] Projetar respostas sem paths, frontmatter arbitrário, histórico ou relações não visíveis.
- [x] Publicar nomes apenas quando o preflight RADAR estiver `ready`; manter scheduler e filhos sem RADAR.
- [x] Tratar conteúdo ABox como dado não confiável e recusar IDs RADAR na memória.
- [x] Persistir projeções de auditoria por tool, sem query livre, descrição, evidência, corpo ou histórico completos.
- [x] Cobrir tools, surface/behaviour do agente, isolamento de contexto, auditoria e fluxo de leitura contra ABox descartável que preserva os Markdown byte a byte.
- [x] Documentar a unidade em `029-radar-read-tools.html` e atualizar índice, arquitetura e ADR-020.

Critério de conclusão da fase:

- [x] Com RADAR disabled/degraded, o agente não vê tools RADAR; com `ready`, vê somente as cinco leituras.
- [x] Um id fora do contexto retorna indisponibilidade genérica e não revela existência.
- [x] Nenhum Markdown canônico muda após consultas; `.radar/audit` pode registrar observações.

### Extensão RADAR — Fase 3: consultas gerenciais compostas

[Referência no PLAN.MD](PLAN.MD#fase-radar-3--consultas-gerenciais-compostas) ·
[Roteiro detalhado](docs/plans/radar-integration-roadmap.md#6-fase-3--consultas-gerenciais-compostas)

- [x] Criar `radar_get_risk_report` para riscos por objetivo/projeto e ações mitigadoras.
- [x] Criar `radar_list_action_attention` para ações atrasadas ou com revisão vencida, calculadas no fuso confiável da aplicação.
- [x] Criar `radar_get_decision_evidence` para decisões, evidências e vínculos relacionados.
- [x] Criar `radar_get_person_commitments` para compromissos aceitos por pessoa, ação e termos projetados.
- [x] Criar `radar_get_management_context` para contexto de dois saltos de reunião/caso.
- [x] Reusar `radar_validate_context` e aceitar códigos reais como `RADAR-M001`, apresentando finding como observação e não corrupção automática.
- [x] Manter contexto, identidade, grants, paths e parâmetros de operação fora de todos os schemas.
- [x] Limitar itens, grafo, varredura de ações e conteúdo textual; sinalizar truncamento explicitamente.
- [x] Projetar auditoria dos cinco relatórios em ids, tipos, estados, datas, contagens e códigos, sem prosa da ABox.
- [x] Cobrir os seis cenários, superfície condicional, seleção de tool, argumentos, auditoria e imutabilidade byte a byte dos Markdown.
- [x] Medir a baseline determinística: a consulta de risco da Fase 2 exigia duas calls do mesmo domínio; cada consulta composta usa uma call depois de o id estar identificado.
- [x] Não criar `management-agent`: não há mistura cross-domain nem responsabilidade própria observada; scheduler e filhos continuam sem RADAR.
- [x] Documentar em `docs/development/030-radar-management-queries.html`, ADR-021, README, SPEC, PLAN, overview e índice.
- [x] Criar `scripts/radar_phase3_report.py` para medir somente traces Telegram: cobertura, sucesso, truncamento, chamadas RADAR por run e uso cross-domain, sem selecionar prompt, resposta ou prosa da ABox.
- [x] Observar um período de uso real e testar o deployment, confirmando a utilidade da superfície composta e a ausência de necessidade de um `management-agent`; priorizar as mutações da Fase 4 pela evidência coletada.

Critério de conclusão da fase:

- [x] Critério técnico: as cinco consultas compostas e a validação respondem cenários gerenciais concretos em ABox descartável sem alterar Markdown canônico.
- [x] O Chief publica as dez leituras apenas com preflight `ready`; scheduler e os três subagentes não recebem RADAR.
- [x] Critério de produto: deployment e testes operacionais concluídos; as mutações candidatas da Fase 4 devem ser escolhidas pela evidência desse uso.

### Extensão RADAR — Fase 4: primeiras mutações com aprovação

[Referência no PLAN.MD](PLAN.MD#fase-radar-4--primeiras-mutações-com-aprovação) ·
[Roteiro detalhado](docs/plans/radar-integration-roadmap.md#7-fase-4--primeiras-mutações-com-aprovação)

- [x] Criar no pacote a API pública `prepare()` que valida parâmetros, alvo, contexto, regras, políticas e transições em estágio descartável.
- [x] Limitar o piloto a `capture_issue`, `delegate` e `review`, com schemas que aceitam somente termos de negócio.
- [x] Adicionar `RADAR_WRITES_ENABLED`, allowlist de operações, manager contexts e TTL; manter escrita desligada por padrão e indisponível sem `prepare()` público.
- [x] Persistir proposta imutável, revisão, TTL, chave de idempotência, status e resultado seguro em `pending_radar_operations` com uma proposta ativa por thread.
- [x] Fazer a tool retornar `approval_required` somente depois da persistência; projetar auditoria sem prosa da ABox.
- [x] Resolver “sim”/“não” no Telegram sem chamar o LLM: claim single-use, reautorização atual, execução do payload salvo e resposta determinística.
- [x] Rejeitar sem tocar runtime; tratar expiração, duplicata, conflito e incerteza de persistência sem nova chave automática.
- [x] Manter scheduler, subagentes e approval genérico sem acesso às propostas/executores RADAR.
- [x] Cobrir preparação sem escrita, argumentos persistidos, alteração de proposta, expiração, consumo único, webhook duplicado, conflito e reconciliação.
- [x] Documentar em `031-radar-approved-mutations.html`, ADR-022, README, SPEC, PLAN, roadmap e índice.

Critério de rollout:

- [x] Fixar `radar-vault 0.3.0` pelo commit imutável da release em `requirements.txt`.
- [ ] Publicar esta revisão do RADAR-CoS e executar o piloto com `RADAR_WRITES_ENABLED=true`.

### Extensão RADAR — endurecimento da interação humana

- [x] Traduzir tipos, estados, relações, action types e motivos de atenção para rótulos em português.
- [x] Remover IDs, revisões e deep links internos da resposta, salvo pedido técnico explícito.
- [x] Aceitar busca e escolha sem acento, além de número, ordinal ou título único.
- [x] Persistir seleção RADAR com papel, pedido original e TTL; retomar o pedido após a escolha.
- [x] Garantir atomicamente uma única lista numérica pendente entre RADAR e Notion.
- [x] Pedir contexto humano quando título, tipo e estado não distinguem candidatos; nunca desempatar por sufixo de ID.
- [x] Persistir referências somente de resultados RADAR confirmados, expirá-las e impedir que autorizem escrita.
- [x] Injetar seleção/referências como pares AI/tool; nenhum título da ABox entra em `SystemMessage`.
- [x] Bloquear busca ambígua → leitura escolhida pelo modelo → proposta; permitir leitura como proveniência apenas quando o usuário digitou o ID no turno atual.
- [x] Renderizar confirmação e recibo pelo snapshot persistido; descrever `delegate` como proposta dependente de aceite.
- [x] Cobrir middleware, colisões, dupla seleção, TTL, prompt injection, humanização e preparação real com pacote 0.3.0.
- [x] Criar migration `20260912_0009` para `pending_radar_selections` e `radar_thread_referents`.
- [x] Documentar em `032-radar-human-interaction.html`, ADR-023, SPEC, PLAN, roadmap e índice.

Critério de conclusão:

- [x] Um humano identifica e escolhe itens por nome e atributos de negócio, sem precisar interpretar códigos.
- [x] Nenhum atalho conversacional amplia autoridade de mutação.
- [ ] Validar a conversa completa no Telegram publicado com ABox real controlada.

### Plano RADAR pós-testes avançados — Fase 0: baseline e observabilidade

[Plano detalhado](docs/plans/radar-advanced-telegram-improvements.md#4-fase-0--fixar-a-linha-de-base-e-a-observabilidade)

- [x] Declarar T01–T14 numa matriz automatizada que usa vault temporário e não toca a ABox operacional.
- [x] Comparar snapshots lógicos de entidades, campos, relações, histórico e corpo antes/depois dos cenários.
- [x] Medir passos do grafo, total de tools, chamadas RADAR, repetições por hash e causa terminal sem persistir prosa.
- [x] Persistir as métricas em `agent_runs.metrics` por migration `20260913_0010`.
- [x] Traduzir `GraphRecursionError` para `agent_step_limit` com resposta pública que sugere dividir o pedido.
- [x] Manter os cenários determinísticos de leitura e segurança sem escrita na ABox descartável.
- [~] Reproduzir os contratos dos achados A, B, D e E como pontos de partida das Fases 2–6; suas correções deliberadamente não foram antecipadas.

### Plano RADAR pós-testes avançados — Fase 1: consultas compostas resilientes

[Plano detalhado](docs/plans/radar-advanced-telegram-improvements.md#5-fase-1--eliminar-a-exaustão-do-grafo-em-consultas-compostas)

- [x] Publicar `radar_resolve_entities` para até oito referências, preservando zero/um/vários candidatos e sem autoridade de escrita.
- [x] Publicar `radar_get_operational_brief` para rotina, projeto, objetivo ou caso com grupos limitados, contagens e `truncated`.
- [x] Classificar itens abertos, decisões vigentes/substituídas, riscos, ações, bloqueios, compromissos, indicadores e evidências no `RadarService`.
- [x] Elevar `MAX_STEPS` para 50 somente com `ToolBudgetMiddleware` configurável: 16 tools e duas chamadas idênticas.
- [x] Auditar argumentos das novas tools por projeção mínima, sem título, consulta, body ou texto da ABox.
- [x] Cobrir superfície, middleware, persistência, snapshots e três execuções determinísticas de T04/T10/T12.
- [~] Rodar T04, T10 e T12 três vezes no Telegram de homologação com provider real; esse aceite ainda depende de credenciais e autorização operacional.

### Plano RADAR pós-testes avançados — Fase 4: linguagem pública e causas seguras

[Plano detalhado](docs/plans/radar-advanced-telegram-improvements.md#8-fase-4--linguagem-pública-causas-seguras-e-formatação)

- [x] Reescrever o prompt de propostas em termos de capacidade de negócio, sem nomes nem contagem da superfície interna.
- [x] Aplicar scrub determinístico de `radar_*`, registries e contagens a toda resposta, inclusive negação e pedido técnico.
- [x] Transportar somente códigos públicos allowlisted entre `radar-vault`, host, auditoria e conversa.
- [x] Diferenciar executor inativo, ator divergente, aceite repetido, evidência ausente, operação indisponível, leitura, escrita e limite do agente.
- [x] Renderizar `*itálico*` como `<i>` no inline compartilhado, preservando matemática, listas, negrito e markup desbalanceado.
- [x] Cobrir humanização, respostas de erro e os dois renderers com testes determinísticos.
- [ ] Publicar uma nova release imutável do `radar-vault` com os códigos e atualizar o pin do host.

### Plano RADAR pós-testes avançados — Fase 5: integridade contínua e sync seguro

[Plano detalhado](docs/plans/radar-advanced-telegram-improvements.md#9-fase-5--integridade-contínua-da-abox-e-sync-seguro)

- [x] Reusar `Vault.validate()` no startup, na mudança de geração e na CLI operacional.
- [x] Detectar mudança por manifest barato e revalidar antes de leitura, preparação e execução.
- [x] Degradar com `vault_changed_invalid`, bloquear writes e expor somente versões, códigos e contagens.
- [x] Cobrir duplicata no startup e depois dele sem path, título ou ID em log; reload de geração corrigida volta a `ready`.
- [x] Criar `scripts/radar_vault_ops.py` com `validate`, `backup`, `promote` e `restore`, recusando falhas com exit code não zero.
- [x] Exigir staging separado, confirmação de `Fully Synced`, agente parado, snapshot estável e candidate válido antes da promoção.
- [x] Preservar `.radar` na promoção, no backup e no restore; rollback restaura o ativo quando a troca falha.
- [x] Documentar o runbook em `039-radar-public-language-integrity.html`, README, SPEC, PLAN e ADR-025.
- [ ] Configurar o Obsidian Headless para staging e executar a primeira promoção controlada na VPS com backup criptografado.

### Fase 0 — Bootstrap do projeto

[Referência no PLAN.MD](PLAN.MD#3-fase-0--bootstrap-do-projeto)

Objetivo: criar um projeto Python executável, testável e containerizado.

- [x] Criar a estrutura inicial do repositório.
- [x] Manter `README.md`, `SPEC.MD`, `PLAN.MD`, `.gitignore` e `.env.example`.
- [x] Criar `pyproject.toml` e `requirements.txt` com a stack inicial prevista.
- [x] Criar `app/`, `tests/` e `scripts/`, incluindo os submódulos arquiteturais.
- [x] Centralizar configuração em `app/config.py` com `Settings`.
- [x] Implementar `GET /health` com resposta `{"status":"ok"}`.
- [x] Criar `Dockerfile` e `docker-compose.yml` para `agent` e `postgres`.
- [x] Adicionar healthcheck do PostgreSQL no Compose.
- [x] Verificar `docker compose up` sem erros no ambiente oficial — executado na VPS na Fase 13.
- [x] Verificar `curl http://localhost:<PORT>/health` dentro do ambiente Docker — 200 pelo healthcheck do container e por `127.0.0.1:8000` no host.

Critério de conclusão da fase:

- [x] `docker compose up` inicia a aplicação e o PostgreSQL — ambos `healthy`, com as migrações Alembic aplicadas no start.
- [x] O endpoint `/health` retorna HTTP 200 e `{"status":"ok"}`.

### Fase 1 — Integração com Notion sem IA

[Referência no PLAN.MD](PLAN.MD#4-fase-1--integração-com-notion-sem-ia)

Objetivo: garantir que as operações fundamentais funcionem deterministicamente antes de envolver o agente.

- [x] Implementar `app/integrations/notion_client.py`.
- [x] Centralizar autenticação, versão da API, timeouts, paginação, retries, rate limits e erros HTTP no client.
- [x] Implementar `TaskService.create_task()`.
- [x] Implementar `TaskService.search_tasks()`.
- [x] Implementar `TaskService.get_task()`.
- [x] Implementar `TaskService.update_task()`.
- [x] Implementar `TaskService.complete_task()`.
- [x] Implementar `ProjectService.search_projects()`.
- [x] Implementar `ProjectService.get_project()`.
- [x] Centralizar o mapeamento do schema real do Notion em `notion_schema.py`.
- [x] Criar o script manual `scripts/test_notion.py` para o fluxo completo sem LLM.
- [x] Criar o script `scripts/notion_schema.py` para inspecionar o schema configurado.
- [x] Criar testes unitários para client, schema e services.
- [x] Executar o CRUD manual com credenciais e databases reais do Notion.
- [x] Confirmar que o fluxo real funciona sem LLM: projects → create → search → get → update → complete.
- [x] Validar e canonicalizar IDs do Notion como UUID antes de compor URLs.
- [x] Verificar que tarefas e projetos pertencem ao data source configurado antes de read/write.
- [x] Validar estruturalmente respostas 2xx, páginas e cursores de paginação.
- [x] Classificar retry por efeito: reads/PATCH idempotente podem repetir; create/append ambíguos não.
- [x] Representar resposta perdida como `unknown` e update multipart como `partial`.
- [x] Fazer o script de schema conferir nomes, tipos, opção de conclusão e destino da relação.
- [x] Fazer o script CRUD usar título único, seleção exata e cleanup em <code>finally</code>.

Critério de conclusão da fase:

- [~] Todo o CRUD necessário funciona sem LLM nos testes e já foi validado historicamente no Notion; a implementação endurecida ainda precisa de um novo smoke live controlado.

### Fase 2 — Tools

[Referência no PLAN.MD](PLAN.MD#5-fase-2--tools)

Objetivo: criar a fronteira controlada entre o agente e a aplicação.

- [x] Criar `app/tools/tasks.py`.
- [x] Criar `app/tools/projects.py`.
- [x] Expor `create_task`.
- [x] Expor `search_tasks`.
- [x] Expor `update_task`.
- [x] Expor `complete_task`.
- [x] Expor `search_projects`.
- [x] Definir schemas de entrada tipados para cada tool em `app/schemas/tool_inputs.py`.
- [x] Fazer cada tool chamar somente o service correspondente.
- [x] Capturar erros de domínio e retornar estruturas compreensíveis (`app/tools/base.py`).
- [x] Registrar cada tool call sem expor secrets.
- [x] Testar as tools diretamente, sem Telegram e sem LLM (`tests/tools/`).
- [x] Registrar a decisão de não usar o MCP do Notion como camada de tools.
- [x] Documentar a fase em `docs/development/003-tools.html` e atualizar `docs/index.html`.
- [x] Recusar coerções silenciosas de datas numéricas, datetimes, booleanos como limites e ranges invertidos.
- [x] Alinhar a superfície ao SPEC: `search_projects.query` obrigatório e sem `status` em `update_task`.
- [x] Retornar outcomes discriminados `succeeded`, `failed`, `unknown` e `partial`.
- [x] Redigir conteúdo e secrets dos logs, preservando evento, duração, status e correlação.
- [x] Tornar o singleton de services atômico, compartilhar um único client e fechá-lo no lifespan.
- [x] Revalidar via Docker — na Fase 13 a imagem foi construída e a suíte inteira, incluindo `tests/tools`, rodou dentro dela.

Critério de conclusão da fase:

- [x] Cada tool aceita input estruturado e produz resultado previsível em testes Python.

Entregas:

| Arquivo | Papel |
| --- | --- |
| `app/schemas/tool_inputs.py` | Um schema Pydantic estrito por tool: UUID, ISO date, ranges e `extra="forbid"` |
| `app/tools/base.py` | Envelope com `ok` + `outcome`, tradução de falha/unknown/partial e logging seguro |
| `app/tools/dependencies.py` | Resolução atômica, client compartilhado e lifecycle explícito |
| `app/tools/tasks.py` | `create_task`, `search_tasks`, `update_task`, `complete_task` |
| `app/tools/projects.py` | `search_projects` |
| `app/tools/__init__.py` | `ALL_TOOLS`, na ordem de apresentação ao modelo |
| `tests/tools/` | Testes por ferramenta, schemas, observabilidade, concorrência e lifecycle |

Decisões registradas (detalhadas em [003 — Tools](docs/development/003-tools.html)):

- Não usar o MCP do Notion como camada de tools: ferramentas genéricas dariam escrita em todo o
  workspace e moveriam o mapeamento de colunas do `notion_schema.py` para o prompt. Se surgir a
  necessidade de busca exploratória, MCP entra depois como canal somente leitura e separado.
- Tools como funções Python puras, sem decorador de framework. A ligação com o LangChain é
  responsabilidade da Fase 3, para que o domínio continue testável sem o agente (`AGENTS.MD §9`).
- Texto relativo bruto ("amanhã") continua recusado com `invalid_input`; desde a Fase 4, o agente deve resolvê-lo para ISO antes da tool.

### Fase 3 — Deep Agent básico

[Referência no PLAN.MD](PLAN.MD#6-fase-3--deep-agent-básico)

Objetivo: permitir que o agente interprete solicitações e selecione as tools corretas.

Ponto de partida já pronto: `app.tools.ALL_TOOLS` expõe as cinco ferramentas com docstring e schema
de entrada tipado, e nenhuma delas levanta exceção — o agente sempre recebe `ok` e `outcome`.

- [x] Consultar a skill oficial [`deep-agents-orchestration`](https://github.com/langchain-ai/langchain-skills/blob/main/config/skills/deep-agents-orchestration/SKILL.md).
- [x] Criar `app/agent/agent.py`.
- [x] Configurar o system prompt inicial com regras de confirmação, ambiguidade e respostas operacionais.
- [x] Envolver `ALL_TOOLS` no formato do framework, sem mover lógica para dentro do agente.
- [x] Publicar ao modelo os schemas de `app/schemas/tool_inputs.py` como descrição de argumentos.
- [x] Disponibilizar somente as tools de tarefas e projetos previstas.
- [x] Não criar subagentes nesta fase sem um domínio próprio que justifique delegação.
- [x] Criar dataset de prompts manuais para criação, consulta, atualização e conclusão de tarefas.
- [x] Verificar, nos testes, tool escolhida, argumentos e resultado — não apenas o texto final.
- [x] Testar comportamento quando uma tool falha ou não confirma sucesso.
- [x] Criar o script manual `scripts/test_agent.py` para o fluxo real sem Telegram.
- [x] Documentar a fase em `docs/development/004-deep-agent.html` e atualizar `docs/index.html`.
- [x] Desabilitar o subagente `general-purpose` pelo perfil oficial dos providers suportados.
- [x] Bloquear built-ins e tools desconhecidas antes do handler, nos caminhos sync e async.
- [x] Não revelar o registry em mensagens de tool desconhecida e rejeitar lotes mistos sem side effects.
- [x] Exigir proveniência de busca única/correspondente para IDs usados em mutações.
- [x] Preservar chamadas solicitadas e trace parcial quando o grafo aborta após uma escrita.
- [x] Derivar `AgentRun.status` das tools e substituir prosa de falso sucesso em `failed`/`partial`/`unknown`.
- [x] Fazer o script manual falhar quando a tool esperada não foi confirmada ou o status é inseguro.
- [x] Criar avaliação opt-in do modelo real usando `FakeNotionClient`.

Critério de conclusão da fase:

- [~] O fluxo `Prompt → Deep Agent → Tool → Service → Notion` funciona sem Telegram nos testes determinísticos. Houve validação real em 2026-08-08 antes do hardening; o código atual precisa de nova avaliação opt-in com provider e de um smoke controlado no workspace.

Entregas:

| Arquivo | Papel |
| --- | --- |
| `app/agent/prompt.py` | O system prompt, isolado para ser diffável |
| `app/agent/model.py` | Resolução do modelo por spec `provider:modelo`, com falha traduzida em `ConfigurationError` |
| `app/agent/tools.py` | `ALL_TOOLS` + `tool_inputs.py` no formato do framework, com o envelope de falha preservado |
| `app/agent/middleware.py` | Visibilidade + contenção de execução + não divulgação do registry + proveniência |
| `app/agent/agent.py` | Perfil sem GP subagent, snapshots, trace completo, `run_id`, status e reply protegida |
| `app/config.py` | Carrega o `.env` no ambiente do processo, para que o SDK do provider ache a credencial |
| `tests/agent/` | Dataset, superfície, built-ins diretos, proveniência, abortos, falso sucesso e live eval opt-in |
| `tests/unit/test_config.py` | 3 testes da ponte `.env` → ambiente, cuja falha seria silenciosa |
| `scripts/test_agent.py` | Execução manual com `--expect-tool`, status/trace e exit code confiável |

Decisões registradas (detalhadas em [004 — Deep Agent](docs/development/004-deep-agent.html)):

- O resultado de uma execução é `AgentRun`, não uma string. Ferramenta, argumentos pedidos e
  normalizados, resultado e status permanecem no trace; o gate impede que a frase do modelo
  transforme `failed`, `partial` ou `unknown` em sucesso.
- As ferramentas embutidas do `deepagents` foram contidas por defesa em profundidade nesta fase e
  reabertas de forma seletiva depois (ver a seção seguinte). O que não mudou: `wrap_tool_call` e
  `awrap_tool_call` bloqueiam qualquer nome fora da allowlist antes do handler, e modelos injetados
  continuam protegidos pelo middleware.
- IDs de escrita precisam ter vindo da busca correspondente com exatamente um resultado no mesmo
  run, ou de uma seleção explícita persistida pela Application a partir de uma busca ambígua.
- O provider do modelo é configuração (`AGENT_MODEL`, forma `provider:modelo`), não código. Nenhum
  SDK de provider é importado fora de `app/agent/model.py`, e a aplicação não nomeia nenhuma chave
  de provider: o `.env` inteiro é carregado no ambiente do processo (`app/config.py`) e cada SDK
  encontra a sua. `override=False` mantém a variável real ganhando do arquivo.
- A memória entre mensagens e a seleção explícita pertencem às Fases 8 e 9; antes delas o agente
  não simula lembrar nem transforma linguagem natural em autorização de escrita.

### Revisão transversal — Hardening das fases 1–3

Objetivo: transformar os gaps da revisão em invariantes testadas sem expandir o escopo funcional.

- [x] Bloquear path traversal e IDs não UUID antes do client HTTP.
- [x] Autorizar páginas e relações pela pertença ao data source configurado.
- [x] Evitar retry automático de create/append quando o efeito é incerto.
- [x] Distinguir falha confirmada, resultado desconhecido e operação parcial.
- [x] Rejeitar respostas 2xx e paginações incompletas como dados inválidos.
- [x] Tornar schemas de tools estritos e coerentes com o SPEC.
- [x] Eliminar conteúdo livre e secrets dos logs; habilitar INFO e correlação por `run_id`.
- [x] Remover race do singleton e fechar o client compartilhado no lifecycle.
- [x] Conter built-ins do Deep Agents no ponto de execução e desabilitar o subagente padrão.
- [x] Exigir proveniência de busca para mutações por ID.
- [x] Preservar trace em abortos e impedir falso sucesso na resposta final.
- [x] Corrigir contrato Docker, providers, IDs canônicos, bind de portas e build context.
- [x] Fixar dependências diretas e adicionar smoke de imports dos providers à imagem.
- [x] Atualizar scripts, README, decisões arquiteturais e documentação HTML 002–005.
- [x] Validar suíte local (242 passed, 5 skipped), lint/formatação, dependências, imports e configuração do Compose.
- [~] Construir/subir Docker e repetir validações live controladas — o lado Docker foi feito na Fase 13; as validações live contra provider e workspace reais continuam pendentes (ver pendências abertas).

Documentação: [005 — Hardening das fases 1–3](docs/development/005-hardening-phases-1-3.html) e [decisões arquiteturais](docs/architecture/decisions.html).

### Fase 4 — Datas e contexto temporal

[Referência no PLAN.MD](PLAN.MD#7-fase-4--datas-e-contexto-temporal)

Objetivo: interpretar e normalizar linguagem temporal de forma consistente.

- [x] Definir `America/Bahia` como timezone padrão em configuração.
- [x] Criar `app/utils/datetime.py`.
- [x] Implementar acesso centralizado ao timezone.
- [x] Normalizar datas para o formato ISO esperado pela aplicação e pelo Notion.
- [x] Disponibilizar a data atual ao agente como parte do contexto.
- [x] Validar o valor final em código, sem transferir essa garantia ao prompt.
- [x] Evitar um parser temporal complexo até existir necessidade real.
- [x] Criar testes para timezone, normalização e limites de data.

Critério de conclusão da fase:

- [x] Datas como “amanhã”, “sexta” e datas ISO chegam ao service de forma normalizada nos testes determinísticos; a escolha do provider real possui avaliação opt-in.

Entregas:

| Arquivo | Papel |
| --- | --- |
| `app/utils/datetime.py` | Resolve o timezone IANA, converte o instante para a data local e normaliza/formata ISO sem coerção |
| `app/agent/prompt.py` | Orienta a interpretação temporal e gera os fatos confiáveis de cada execução |
| `app/agent/agent.py` | Injeta um `SystemMessage` temporal novo antes da mensagem do usuário em cada run |
| `app/schemas/tool_inputs.py` | Reutiliza a normalização central e preserva a fronteira ISO estrita |
| `app/integrations/notion_schema.py` | Formata prazos e filtros pelo mesmo caminho canônico antes do Notion |
| `tests/unit/test_datetime.py` | Cobre timezone inválido, meia-noite UTC/Bahia, ano bissexto, limites e entradas com perda |
| `tests/agent/temporal_dataset.py` + `test_agent_temporal.py` | Cobre contexto por run, “amanhã”, “sexta”, ISO, busca de um dia e payload do Notion |
| `docs/development/006-temporal-context.html` | Ensina o fluxo, as decisões, testes, limites e diagnóstico da fase |

Decisões registradas:

- O modelo interpreta linguagem relativa; código aceita e valida somente o valor final ISO.
- O contexto temporal é um snapshot calculado uma vez por `run_agent()`, não no import nem em `build_agent()`.
- `zoneinfo` da biblioteca padrão substitui uma dependência/parser temporal; a imagem verifica o timezone padrão durante o build.
- O domínio atual armazena somente data. Horário relevante não pode ser descartado silenciosamente pelo agente.

### Fase 5 — Telegram

[Referência no PLAN.MD](PLAN.MD#8-fase-5--telegram)

Objetivo: transformar o Telegram na interface principal do assistente.

- [x] Criar o bot através do BotFather — `@JMR_deepagents_bot`, confirmado por `getMe`.
- [x] Configurar `TELEGRAM_BOT_TOKEN` — presente no `.env` local e no `.env` da VPS, nunca versionado.
- [x] Configurar `TELEGRAM_ALLOWED_USER_ID` — definido nos dois ambientes.
- [x] Implementar `app/integrations/telegram_client.py`.
- [x] Implementar `send_message()`.
- [x] Reservar `get_file()` para o suporte futuro a áudio.
- [x] Criar `POST /webhooks/telegram`.
- [x] Implementar o pipeline Receive → Validate → Authorize → Deduplicate → Extract → Invoke → Respond.
- [x] Rejeitar, ignorar ou responder genericamente a usuários não autorizados.
- [x] Garantir que usuário não autorizado não consuma LLM nem integrações.
- [x] Testar o webhook com payloads válidos, inválidos e não autorizados.
- [x] Documentar a fase em `docs/development/007-telegram-webhook.html` e atualizar `docs/index.html`.

Critério de conclusão da fase:

- [~] O fluxo determinístico do webhook funciona localmente e o endpoint já está publicado em HTTPS; falta registrar o webhook no Telegram (Fase 14) e validar uma mensagem real. `getWebhookInfo` reporta `url` vazia e 3 updates aguardando na fila.

- [~] Uma mensagem autorizada do Telegram chega ao agente e recebe resposta — coberto por testes locais; validação live pendente.

### Fase 6 — Idempotência

[Referência no PLAN.MD](PLAN.MD#9-fase-6--idempotência)

Objetivo: impedir que reentregas do webhook criem ações duplicadas.

- [x] Extrair `telegram_update_id` de cada update.
- [x] Criar o registro de update recebido antes do processamento.
- [x] Verificar se o `update_id` já existe antes de chamar o agente.
- [x] Ignorar reentregas sem repetir a operação no Notion.
- [x] Registrar `received_at`, `processed_at` e `status`.
- [x] Testar retry do Telegram e falhas parciais do processamento.
- [x] Criar claim atômico com chave primária e `ON CONFLICT DO NOTHING`.
- [x] Inicializar a tabela no primeiro claim e liberar o pool no shutdown.
- [x] Documentar a fase em `docs/development/008-telegram-idempotency.html` e atualizar `docs/index.html`.

Critério de conclusão da fase:

- [x] O mesmo `update_id` nunca cria duas tarefas nem executa duas vezes a mesma ação.

### Fase 7 — Persistência das execuções

[Referência no PLAN.MD](PLAN.MD#10-fase-7--persistência-das-execuções)

Objetivo: permitir reconstruir cada execução posteriormente.

- [x] Configurar Alembic e migration inicial de banco.
- [x] Criar a tabela `agent_threads`.
- [x] Criar a tabela `agent_runs`.
- [x] Criar a tabela `tool_calls`.
- [x] Criar a tabela `telegram_updates`.
- [x] Criar a tabela `errors`.
- [x] Gerar um `run_id` por execução de `run_agent()` e aceitar um id externo.
- [x] Propagar `run_id` para agente, tools, logs e erros do fluxo Telegram.
- [x] Persistir argumentos e resultados de tools sem secrets.
- [x] Testar migrations e constraints no PostgreSQL; migration aplicada em `db_chiefofstaff` e tabelas verificadas.

Critério de conclusão da fase:

- [x] Uma execução pode ser reconstruída a partir de `run_id`, incluindo tool calls e erros; contrato, SQLite e PostgreSQL validados.

### Fase 8 — Conversational threads

[Referência no PLAN.MD](PLAN.MD#11-fase-8--conversational-threads)

Objetivo: manter contexto básico entre mensagens.

- [x] Associar inicialmente a thread ao `telegram_user_id`.
- [x] Criar ou recuperar uma thread principal para o usuário único.
- [x] Persistir o contexto necessário para a próxima mensagem.
- [x] Preparar a evolução para um `thread_id` explícito.
- [x] Testar o contexto: “Estou trabalhando no projeto Builders” → criação de tarefa sem repetir o projeto.
- [x] Garantir que contexto não substitua validação determinística.

Critério de conclusão da fase:

- [x] O agente considera contexto anterior sem inventar projeto, tarefa ou identificador.

### Fase 9 — Tratamento de ambiguidade

[Referência no PLAN.MD](PLAN.MD#12-fase-9--tratamento-de-ambiguidade)

Objetivo: evitar ações arbitrárias quando houver mais de um recurso compatível.

- [x] Detectar pedidos que podem corresponder a várias tarefas e persistir seus candidatos na thread.
- [x] Consultar tarefas antes de concluir ou alterar um item por ID.
- [x] Apresentar opções relevantes ao usuário.
- [x] Pedir confirmação/seleção antes de executar a operação.
- [x] Não executar mutação quando a busca retornou zero, múltiplos ou ID divergente.
- [x] Testar o caso de conclusão/alteração com múltiplos resultados, sem side effects.

Critério de conclusão da fase:

- [x] Nenhuma tarefa ambígua é concluída ou alterada sem identificação suficiente.

### Fase 10 — Logging estruturado

[Referência no PLAN.MD](PLAN.MD#13-fase-10--logging-estruturado)

Objetivo: tornar a execução observável e auditável.

- [x] Usar `logging` no runtime; `print()` permanece apenas em scripts manuais.
- [x] Configurar logger JSON estruturado por `LOG_LEVEL` (padrão INFO).
- [x] Incluir `timestamp`.
- [x] Incluir `level`.
- [x] Incluir `run_id` quando aplicável.
- [x] Incluir `thread_id` quando aplicável, inclusive nos runs da thread conversacional.
- [x] Incluir `tool` quando aplicável.
- [x] Incluir duração e status.
- [x] Remover secrets, conteúdo do usuário e texto cru de exceção dos logs.
- [x] Testar logs de sucesso, falha e comportamento de retry, incluindo evento específico de retry.

Critério de conclusão da fase:

- [x] Runs, tools, Telegram, threads e persistência podem ser acompanhados pelos logs sem depender do texto final.

### Fase 11 — Error handling

[Referência no PLAN.MD](PLAN.MD#14-fase-11--error-handling)

Objetivo: comunicar falhas com honestidade e segurança.

- [x] Criar `TelegramAPIError`.
- [x] Manter erros específicos já existentes para Notion e domínio.
- [x] Criar `UnauthorizedUserError`.
- [x] Manter `TaskNotFoundError` e `ProjectNotFoundError`.
- [x] Criar `AmbiguousTaskError`.
- [x] Criar `AgentExecutionError`.
- [x] Traduzir falhas técnicas em mensagens curtas e úteis para o Telegram.
- [x] Nunca afirmar sucesso quando o trace da tool/integration registra falha, partial ou unknown.
- [x] Não expor stack traces, conteúdo bruto de provider ou registry de tools ao usuário/modelo.
- [x] Preservar detalhes técnicos seguros nos logs e na persistência de auditoria.
- [x] Testar timeout, erro de API, falha do agente e usuário não autorizado.

Critério de conclusão da fase:

- [x] Falhas não geram falsos positivos nem vazam detalhes internos ao Telegram.

### Fase 12 — Testes automatizados

[Referência no PLAN.MD](PLAN.MD#15-fase-12--testes-automatizados)

Objetivo: validar cada camada sem depender do Telegram ou de um LLM real.

- [x] Manter testes unitários para client, schema, services e healthcheck.
- [x] Organizar testes por camada: `unit`, `tools`, `agent` e `integration`.
- [x] Testar validators, schemas, date utilities e security nas fases correspondentes.
- [x] Criar testes de integração das camadas com Notion mockado.
- [x] Criar teste de integração com PostgreSQL isolado por schema e opt-in por `TEST_POSTGRES_DATABASE_URL`.
- [x] Criar testes do Telegram com client/mock.
- [x] Criar dataset de testes de seleção de tools.
- [x] Validar tool escolhida e campos esperados.
- [x] Validar quantidade e sequência de chamadas.
- [x] Validar ambiguidade, contenção, proveniência e comportamento em erro.
- [x] Criar avaliação opt-in com modelo real e Notion falso.
- [x] Executar a suíte completa no ambiente Docker — executada na VPS durante a Fase 13, dentro da imagem `personal-cos-agent` e contra um PostgreSQL 16 efêmero: 301 passaram e 9 avaliações live continuam opt-in. `ruff check` e `ruff format --check` limpos no mesmo container.

Critério de conclusão da fase:

- [x] A hierarquia Unit → Integration → Tool → Agent → End-to-end está coberta pelos testes relevantes, incluindo a camada PostgreSQL/Docker real.

### Fase 13 — Deployment na VPS

[Referência no PLAN.MD](PLAN.MD#16-fase-13--deployment-na-vps)

Objetivo: executar o assistente em infraestrutura própria.

- [x] Confirmar VPS com Docker, Docker Compose e Git — Ubuntu 24.04, Docker 29.1.3, Compose v5.0.0, Git 2.43.
- [x] Configurar HTTPS e reverse proxy — reaproveitado o Traefik do EasyPanel já instalado no host, via `docker-compose.prod.yml` com labels e a rede overlay externa `easypanel`.
- [x] Publicar o código na VPS em `~/apps/personal-cos` — por `rsync`, porque o projeto ainda não tem repositório Git; troque por `git clone` quando houver remoto.
- [x] Criar `.env` na VPS sem versionar secrets — arquivo com permissão `600`, gerado fora do repositório e excluído da imagem pelo `.dockerignore`.
- [x] Executar `docker compose build`.
- [x] Executar `docker compose up -d` — migrações Alembic aplicadas até `20260808_0003` no start.
- [x] Expor somente o endpoint necessário — apenas `PUBLIC_HOST` pelo Traefik; a porta da aplicação é publicada só em `127.0.0.1:8000`.
- [x] Manter PostgreSQL inacessível publicamente — rede privada do projeto e publicação em `127.0.0.1:5433`; conexão externa à porta é recusada.
- [x] Validar healthcheck e logs dos containers — ambos `healthy`; `/health` responde 200 por HTTPS com certificado Let's Encrypt válido e HTTP redireciona com 302.
- [x] Documentar rollback e diagnóstico básico — `docs/development/013-vps-deployment.html`.

Critério de conclusão da fase:

- [x] A aplicação está acessível via HTTPS em `https://personal-cos.kqfrop.easypanel.host` e o banco não está exposto à Internet.

Correção disparada por esta fase: com Docker finalmente disponível, a suíte rodou contra PostgreSQL real e revelou que `TelegramUpdateRepository.claim()` decidia o claim por `rowcount`, que o psycopg reporta como `-1` em `INSERT ... ON CONFLICT DO NOTHING`. A linha era gravada e o método retornava `False`, então o webhook descartaria **todo** update como duplicado em produção. O claim passou a ser decidido por `RETURNING`, exato em PostgreSQL e SQLite.

### Fase 14 — Configurar webhook Telegram

[Referência no PLAN.MD](PLAN.MD#17-fase-14--configurar-webhook-telegram)

Objetivo: conectar o bot Telegram ao endpoint HTTPS da VPS.

- [x] Confirmar HTTPS funcional no domínio do agente — validado na Fase 13: 200 em `/health`, certificado Let's Encrypt e HTTP redirecionando com 302.
- [x] Registrar `https://personal-cos.kqfrop.easypanel.host/webhooks/telegram` no Telegram — `getWebhookInfo` confirma a URL, `ip_address=157.173.107.221`, `pending_update_count=0` e `last_error_message=None`.
- [x] Configurar secret do webhook quando suportado — `secret_token` informado no `setWebhook`; conferido que `.env` local, `.env` da VPS e o valor carregado pelo container são idênticos (64 caracteres, charset aceito pelo Telegram).
- [x] Validar assinatura/secret no endpoint — POST sem cabeçalho e POST com secret errado retornam 401 antes de qualquer parsing; com o secret correto a requisição passa da camada de transporte.
- [x] Confirmar entrega de updates autorizados — 16 updates reais entregues pelo Telegram e todos com status `processed` em `telegram_updates`, `pending_update_count=0` e `last_error_message=None` no `getWebhookInfo`; cada um gerou o `agent_run` correspondente com `tool_calls` registrados.
- [x] Confirmar rejeição/ignorância de updates não autorizados — update com secret válido e usuário estranho retorna `{"status":"ignored"}`, registra `telegram.update.unauthorized` com apenas o `error_type` e não gera claim (`telegram_updates`) nem execução (`agent_runs`).

Decisões do registro: `allowed_updates=["message"]` porque a aplicação só entende mensagens de texto; `drop_pending_updates=true` para descartar três saudações antigas que dispararia execuções simultâneas do agente no instante do registro; `max_connections=20` porque o agente é síncrono e roda no worker pool.

Documentação: [014 — Registro do webhook Telegram](docs/development/014-telegram-webhook-registration.html).

Critério de conclusão da fase:

- [x] O Telegram entrega updates ao webhook HTTPS e o sistema processa apenas a origem esperada — comprovado nos dois eixos, transporte e usuário, com 16 entregas reais sem nenhum erro de entrega.

### Ampliação da superfície do board (08/08, depois da Fase 14)

O uso real mostrou que o agente enxergava 4 das 24 colunas de tarefa e 2 das 16 de projeto, o que o impedia de responder "o que faço agora" em vez de apenas "o que existe".

- [x] **Tarefas** — `PRIORIDADE`, `MACRO_CONTEXTO`, `LISTA`, `CONTEXTO-PESSOA`, `Departamento`, `Assigned_status`, `Periodicidade`, `Inbox` e `Próxima ação` passaram a ser lidos, filtrados em `search_tasks` e escritos em `create_task`/`update_task`. (`CONTEXTO-PESSOA` foi substituída pela relation `PESSOAS` em 13/08; ver a entrada correspondente no marco M1.)
- [x] **Projetos** — `TIPO`, `Prioridade`, `Setor`, `Responsável` e `% Concluído` passaram a ser lidos, com filtro por tipo, prioridade e setor em `search_projects`. Projetos seguem somente leitura.
- [x] **Busca padrão** — sem `status` explícito, `search_tasks` exclui as tarefas `Feito`. A ordenação é por prazo ascendente, então antes disso "as próximas tarefas" significava "as mais antigas já concluídas", devolvendo itens de 2022. `include_completed=true` alcança o histórico.
- [x] **Vocabulário fechado** — cada coluna de escolha virou um `Literal`, então o modelo recebe as opções válidas no schema da tool. Isso vale principalmente para os `multi_select`: um nome inventado não seria recusado pelo Notion, viraria uma opção nova no board.
- [x] **Rede de proteção do drift** — `scripts/notion_schema.py` agora confere todas as listas declaradas contra o schema vivo, não só a opção de conclusão. Executado contra o workspace real: `Mapping matches the live schema`.
- [x] Colunas deixadas de fora de propósito: `DATA DE EXECUÇÃO` e `Data lembrete`, que pertencem ao fluxo manual, além de fórmulas, rollups e relations auxiliares.

### Correções disparadas pelo uso real da Fase 14

Os 16 updates reais expuseram três defeitos que os testes locais não pegavam. Todos foram corrigidos, com teste de regressão, e estão publicados na VPS.

- [x] **Proveniência restrita à última busca** — `_single_search_result_matches` percorria as mensagens ao contrário e decidia na primeira busca encontrada, tornando qualquer busca anterior inalcançável. Bloqueou 7 das 9 chamadas de `update_task`: pedidos com duas tarefas eram impossíveis. Agora qualquer busca do run com exatamente um resultado casando o id autoriza a mutação; a garantia é a mesma, o id continua tendo de vir de uma busca inequívoca. `tests/agent/test_agent_provenance.py` ganhou o cenário exato de produção e o contra-exemplo — verifiquei que o primeiro falha com a lógica antiga.
- [x] **`agent_runs` com duração zero** — `started_at` e `completed_at` recebiam o mesmo `now` do momento da persistência, então todo run parecia instantâneo apesar de levar de 2 a 16 segundos. A janela real da execução passou a ser medida em `app/application/telegram.py` e enviada ao `save()`; o `duration_ms` do log de auditoria virou explicitamente a duração da escrita.
- [x] **`search_tasks` aceitava status inexistente** — o agente chutou `status="Inbox"` (que neste workspace é um checkbox, não um status) e levou `notion_error`. `TaskStatus` foi declarado em `app/schemas/task.py` com as sete opções reais da coluna `STATUS`, então o modelo recebe um `enum` no schema da tool e um valor inventado é recusado antes de chegar ao Notion.

### Ampliação da superfície do Deep Agent (09/08)

Objetivo: ativar as funções nativas do `deepagents` que a Fase 3 havia fechado, sem devolver
nenhuma das garantias que aquele fechamento comprou.

- [x] Declarar a superfície habilitada em um só lugar (`app/agent/builtins.py`), com a capacidade a
      que cada nome pertence.
- [x] Habilitar planejamento (`write_todos` via `TodoListMiddleware` — em `deepagents==0.7.5` ele só
      vem por padrão no perfil Codex, então é adicionado explicitamente).
- [x] Habilitar o filesystem virtual sobre o `StateBackend` padrão: `ls`, `read_file`, `glob`,
      `grep`, `write_file`, `edit_file` e `delete`. Nenhum arquivo toca o disco do container.
- [x] Manter `execute` permanentemente desligado: excluído no harness profile (o framework nem
      constrói a tool) e ausente da allowlist (segunda linha, caso o perfil não case com o modelo).
- [x] Habilitar delegação com um spec explícito de subagente em vez do GP automático. O
      `deepagents` entrega ao subagente as tools do pai mas monta a stack de middleware dele à
      parte: sem a allowlist injetada no spec, `create_task`/`update_task`/`complete_task` rodariam
      lá sem o guard de proveniência e fora do trace que deriva o status do run.
- [x] Tornar o subagente somente leitura (`search_projects`, `search_tasks` e leitura de arquivos):
      uma escrita feita dentro dele não apareceria em `AgentRunRepository` nem em
      `_derive_run_status`.
- [x] Exigir autorização do usuário para `write_file`, `edit_file` e `delete`, pelo mesmo padrão de
      duas voltas já usado por `PendingTaskSelection`: recusa com `approval_required`, pergunta
      determinística no Telegram, e a autorização reinjetada como *resultado* de tool — canal que o
      modelo não escreve.
- [x] Persistir a autorização pendente em `pending_write_approvals` (migração `20260809_0004`),
      junto com a mensagem recusada, já que um "sim" isolado não carrega instrução.
- [x] Ensinar a camada de trace a ler built-ins: elas não falam o envelope `{"ok", "outcome"}`, e
      lê-las como envelope fazia um `write_file` bem-sucedido virar `unknown`. O trace guarda o
      tamanho da resposta, nunca o corpo — `tool_calls.result` é coluna durável de auditoria.
- [x] Novo status `awaiting_approval`, distinto de falha: nada foi tentado e nada pode ter sido
      aplicado pela metade.

### Workspace durável entre turnos (09/08)

Objetivo: fazer o filesystem virtual sobreviver de uma mensagem para a seguinte, sem checkpointer.

O `StateBackend` guarda os arquivos na chave `files` do estado do grafo, e o próprio `deepagents`
documenta a entrada `invoke({"messages": [...], "files": {...}})`. Isso basta: a aplicação lê os
arquivos do último snapshot do stream, guarda, e reinjeta no run seguinte. Um checkpointer não foi
usado de propósito — anexar um ao `thread_id` atual duplicaria o histórico, que já é reenviado a
cada run por `threads.history()`.

- [x] `run_agent` recebe `workspace=` e devolve `AgentRun.workspace` com o estado final.
- [x] Distinguir `{}` (o agente esvaziou) de `None` (nenhum snapshot foi observado). Só o primeiro
      sobrescreve o que está guardado; um abort antes do primeiro snapshot não apaga arquivos que
      um turno anterior gravou legitimamente.
- [x] Capturar os arquivos a cada snapshot, pelo mesmo motivo das mensagens: uma exceção depois de
      uma escrita confirmada não pode apagar o arquivo que ela produziu.
- [x] Persistir em `agent_thread_files` (migração `20260809_0005`), uma linha por thread, sempre
      substituída. Workspace vazio remove a linha.
- [x] Limitar o que é carregado (`MAX_WORKSPACE_FILES = 32`, `MAX_WORKSPACE_BYTES = 256 KiB`): o
      workspace é a única parte do thread cujo tamanho o modelo controla, e ele é lido, reenviado
      ao provider e regravado a cada turno. Os mais recentes ficam; um arquivo grande demais é
      pulado sem evictar as notas pequenas atrás dele. Só contagens vão para o log — um caminho é
      escolhido pelo modelo e pode citar palavras do usuário.

Limite conhecido: o workspace é por thread, e a aplicação tem uma thread principal por usuário do
Telegram. Não há isolamento por assunto nem expiração por idade.

### Fase 15 — Teste end-to-end

[Referência no PLAN.MD](PLAN.MD#18-fase-15--teste-end-to-end)

Objetivo: validar o fluxo completo pelo canal real.

- [x] Criar uma tarefa chamada “testar agente” para amanhã pelo Telegram — `create_task{title:"Testar agente", due_date:"2026-08-10"}`, resposta em 5,96 s.
- [x] Consultar as tarefas de amanhã pelo Telegram — `search_tasks{due_after:"2026-08-10", due_before:"2026-08-10"}` devolveu as 4 esperadas (as 3 da linha de base mais a nova), com `include_completed=false` aplicado por padrão.
- [x] Adiar “testar agente” para sexta-feira — `search_tasks{query:"Testar agente"}` seguido de `update_task{due_date:"2026-08-14"}` com o id vindo da própria busca.
- [x] Concluir “testar agente” — `search_tasks` seguido de `complete_task`; o `result` da tool traz `status:"Feito"` confirmado pelo Notion.
- [x] Verificar os resultados no Notion — lido por fora do agente: `status='Feito'`, `due=2026-08-14`; a busca padrão deixou de encontrá-la e `include_completed` a alcança.
- [x] Verificar logs da execução — cadeia completa por `run_id`/`thread_id`, de `telegram.update.accepted` a `telegram.update.responded`, sem nenhum `WARNING`, `ERROR` ou traceback. O título aparece como `{"length":13,"redacted":true}`.
- [x] Verificar registros no PostgreSQL — 4 updates `processed`, 4 runs `succeeded` sem `execution_error`, todos na mesma thread, tabela `errors` vazia e nenhuma seleção pendente. Durações entre 5,6 s e 8,5 s, confirmando a correção da janela de execução.
- [x] Verificar `tool_calls` e seus argumentos/resultados — 6 chamadas, todas `succeeded`, com argumentos pedidos, argumentos normalizados e o payload íntegro do Notion registrados.
- [x] Registrar problemas encontrados durante o uso real — nenhum defeito novo nos quatro cenários. O reenvio byte a byte do quarto update devolveu `{"status":"duplicate"}` em 0,69 s sem gerar segundo run, validando em produção o `claim()` por `RETURNING`.

Forma de entrega: os quatro updates foram entregues por `POST` direto ao webhook de produção, com o secret real e o `user_id` autorizado, em payload idêntico ao de uma mensagem privada de texto. Da validação do secret em diante nada muda, e a resposta saiu pela Bot API real para o chat do dono; o único trecho não exercitado é Telegram → webhook, comprovado na Fase 14 com 16 entregas reais. Os `update_id` usados ficaram na faixa `999000001–999000004`, longe da sequência real do bot, para não colidir com a chave de idempotência de mensagens futuras.

Antes de disparar, foi conferido que a imagem em execução contém o código atual: `sha256` idêntico entre a máquina local, `~/apps/personal-cos` e `/app` dentro do container.

Documentação: [016 — Teste end-to-end](docs/development/016-end-to-end-test.html).

Critério de conclusão da fase:

- [x] O fluxo real Telegram → FastAPI → Application → Deep Agent → Tools → Notion é confiável nos quatro cenários — criar, consultar, adiar e concluir passaram com o rastro conferido em quatro eixos independentes.

## Marcos após o fluxo principal

### Marco M1 — MVP

[Referência no PLAN.MD](PLAN.MD#19-marco-m1--mvp)

- [ ] Usar diariamente o fluxo Telegram → Deep Agent → Notion Tasks.
- [ ] Confirmar Create, Read, Update e Complete.
- [ ] Confirmar vinculação a projetos.
- [ ] Confirmar contexto conversacional.
- [ ] Parar novas funcionalidades por alguns dias.
- [ ] Registrar fricções observadas no uso real antes de expandir o sistema.

#### Fricções corrigidas durante o uso

- [x] Formatação das respostas no Telegram — `parse_mode="HTML"` escolhido sobre `MarkdownV2` (três caracteres a escapar contra dezoito), com renderização determinística de um subconjunto Markdown em `app/integrations/telegram_format.py`, corte no limite de 4096 caracteres, reenvio em texto puro quando o Telegram recusa a marcação com `400` e preview de link desligado. Documentado em `docs/development/017-telegram-formatting.html`.
- [x] Legibilidade das listas longas, a partir da primeira tela real — negrito aninhado no rótulo do link (título clicável e em negrito), `<blockquote expandable>` decidido pelo renderizador acima de `EXPANDABLE_QUOTE_LINES` linhas, e regra 10 do prompt: agrupar por prazo com cabeçalho, nunca escrever a ausência de um dado, citar responsável só quando distinguir o item, e resumir acima de quinze tarefas.
- [x] `sendRichMessage` e `sendRichMessageDraft` (Bot API 10.1) — `app/integrations/telegram_rich.py` renderiza títulos, listas nativas, listas numeradas, checkboxes, tabelas com alinhamento, divisores e seções recolhidas em `<details>` pelo próprio renderizador, dentro dos limites de 32768 caracteres e 500 blocos. O campo `html` do `InputRichMessage` foi escolhido sobre `markdown` justamente porque `markdown` aceita HTML arbitrário do modelo, o que apagaria a garantia da fase anterior. A entrega virou uma escada de três degraus — rico, HTML clássico, texto puro — em que só `400` desce e o que não foi entregue é repassado ao degrau de baixo, sem perder nem duplicar pedaço. O rascunho `<tg-thinking>` é transmitido ao aceitar o update e engole toda falha: uma cortesia nunca custa a resposta. `TELEGRAM_RICH_MESSAGES_ENABLED` volta ao comportamento da Fase 16 sem tocar em código. Documentado em `docs/development/018-telegram-rich-messages.html`.
- [x] **A coluna de pessoas virou relação e ninguém percebeu** (13/08) — `CONTEXTO-PESSOA` (multi_select) foi substituída no board por `PESSOAS`, uma relation para a base *PESSOAS* (25 linhas). A leitura tolerante a coluna ausente devolvia lista vazia, então nada falhou: só a escrita quebraria, e o filtro por pessoa devolveria vazio, que se lê como "essa pessoa não tem tarefas". Correção: mapeamento para `relation`, `app/services/people_directory.py` traduzindo nome ↔ página com cache de 10 min, casamento por prefixo de qualquer palavra ignorando caixa e acento, recusa com `PersonNotFoundError` e `candidates` no envelope quando o nome não identifica exatamente uma pessoa, `NOTION_PEOPLE_DATA_SOURCE_ID` opcional (sem ele, todo o resto funciona e tarefas não mostram pessoas), e o `TaskPerson` literal de 39 nomes removido — uma tabela viva não cabe num `Literal`. `scripts/notion_schema.py` foi refeito: quatro bases (incluindo pessoas e referências), três níveis de achado, checagem de vocabulário declarado nos dois sentidos, destino de cada relação, colunas não mapeadas listadas, base opcional sem id é pulada e não reprovada, e `--json`. Documentado em `docs/development/021-people-relation.html`.
- [x] **Arquivo mandado no chat era recusado por código, não pelo modelo** (16/08) — `_extract_update` lia só `text` e `voice`/`audio`, e `_UNSUPPORTED_KINDS` chegava a nomear `document` e `photo` apenas para produzir uma recusa mais educada; o `return` acontecia antes do balão, da thread e de `run_agent`. A investigação mostrou que a metade cara já estava resolvida a montante: com `FileData(encoding="base64")`, o `read_file` do `deepagents` devolve um bloco multimodal e deduz o media type da extensão do caminho — imagem e PDF chegam ao modelo como o documento de verdade. Faltava só onde guardar. Correção: `app/integrations/document_text.py` (classificação por tipo declarado e depois por extensão, decode com fallback, extração OOXML com `zipfile` + `xml.etree` e guarda contra zip bomb), `app/application/attachments.py` espelhando `voice.py` (checagens baratas antes do download, nome reconstruído por lista de permitidos, colisão vira `-2`, toda falha respondida e nunca levantada), `/anexos/` com orçamento próprio de 4 arquivos / 8 MB em `bounded_workspace`, a `caption` finalmente lida como instrução — com pedido o agente executa, sem pedido confirma e pergunta — e o conteúdo do arquivo marcado como dado não-confiável com o mesmo aviso do `read_url`. **Nenhuma dependência nova, nenhuma migração, nenhuma tool nova.** Vídeo, figurinha, enquete e localização mantêm a recusa educada, e a regra do incidente das quatorze horas segue intacta: responder, marcar `processed`, devolver `200`. Documentado em `docs/development/024-telegram-attachments.html`.
- [x] Toda tarefa nova nasce na inbox — a triagem do board acontece lá, e uma tarefa criada fora dela é uma tarefa que nenhuma revisão olha. A regra vive em `TaskService.create_task` (`DEFAULT_TASK_INBOX`), e não no prompt, porque o que precisa valer sempre é enforçado em código (§16): o campo omitido vira `Inbox = true`, enquanto `inbox=False` continua sendo uma decisão respeitada. `update_task` não recebe padrão nenhum — lá, campo ausente segue significando "não mexer". A descrição publicada em `CreateTaskInput` conta ao modelo qual é o padrão e como sair dele.

### Marco M2 — Áudio

[Referência no PLAN.MD](PLAN.MD#20-marco-m2--áudio)

- [x] Receber voice message do Telegram — `TelegramAudio.from_message` lê `voice` e `audio`, aplica `audio/ogg` como padrão da nota de voz e ignora qualquer outro anexo; `_extract_update` decide entre áudio, anexo e texto antes de qualquer trabalho ser reivindicado — foto e documento passaram a ser lidos na fricção de 16/08 registrada no M1, e vídeo, figurinha e enquete continuam recusados ali mesmo.
- [x] Baixar o arquivo — `TelegramClient.download_file` faz stream de `/file/bot<token>/<path>` com orçamento de bytes conferido duas vezes: contra o `Content-Length` anunciado e contra os bytes recebidos.
- [x] Converter voz em texto — `app/integrations/transcription.py` fala com qualquer endpoint compatível com `/audio/transcriptions`; `STT_API_KEY` cai para `OPENAI_API_KEY`. Duração, tipo e tamanho são recusados antes do download, e cada falha vira resposta no chat em vez de erro HTTP, para o Telegram não reenviar o mesmo áudio.
- [x] Enviar a transcrição ao Deep Agent — a transcrição substitui o texto da mensagem e segue pelo fluxo já existente, depois da deduplicação para um update reenviado não ser pago duas vezes no endpoint de fala. A thread guarda a transcrição; o log guarda só o tamanho dela.
- [ ] Detectar múltiplas tarefas.
- [ ] Mostrar resumo e pedir confirmação antes de criar várias tarefas.

### Marco M9 — Briefing de pessoa

[Referência no PLAN.MD](PLAN.MD#27-marco-m9--briefing-de-pessoa)

Vem antes do M3 na ordem de execução, apesar do número.

- [ ] `retrieve_block_children` no `NotionClient`, com paginação — hoje existe só a escrita (`append_block_children`).
- [ ] Schema próprio para o briefing, separado de `Person`: cargo e setor entram, telefone fica fora.
- [ ] `app/services/person_service.py` juntando linha, corpo da página e tarefas abertas relacionadas.
- [ ] Tool `read_person(name)` com o envelope `{"ok", "outcome"}`, em uma chamada só.
- [ ] Nome ambíguo recusado com `candidates`, reusando `PersonNotFoundError`.
- [ ] Página longa truncada com aviso explícito; página vazia respondida como vazia.
- [ ] Somente leitura: sem `append_person_note` e sem escrita por MCP nessa base.
- [ ] `docs/development/023-person-briefing.html` e ADR-015.

### Marco M3 — Long-term memory

[Referência no PLAN.MD](PLAN.MD#21-marco-m3--long-term-memory)

- [x] Tabela `agent_memories` com `UNIQUE (thread_id, normalized_content)` como deduplicação do banco, migration `20260815_0007` e índice `(thread_id, created_at)`. A normalização ignora caixa, acento e espaçamento, então repetir uma preferência devolve sucesso — o usuário se repetir é o que este marco existe para tolerar.
- [x] Bloco de memória injetado como mensagem de sistema, congelado por execução, ao lado do contexto temporal. `build_memory_context` renderiza inclusive o store vazio: “nada registrado ainda” é uma resposta; uma seção ausente é silêncio a interpretar.
- [x] `remember(kind, content, replaces=None)` e `forget(memory_id)`; nenhuma tool de leitura, porque o bloco já está no contexto. `replaces` faz remoção e inserção na mesma transação, que é como se abre espaço com o orçamento cheio.
- [x] Orçamento de caracteres como erro com as entradas atuais, terminal após três recusas na mesma execução. O contador vive no service, com chave no `run_id` e limite de 64 runs lembrados — nada avisa este módulo quando um run termina.
- [x] Recusar na escrita id do Notion, URL de página e caractere invisível ou de controle. É a recusa que sustenta “memória é contexto, nunca autoridade”: uma entrada que não consegue nomear uma página não pode ser confundida com permissão para escrever nela.
- [x] Teste de destino: pessoa, projeto, tarefa e referência ficam no Notion; só o que não tem board vira registro. Está no prompt, com a lista do que não guardar, e o `kind` `context` foi definido estreitamente para não virar a porta dos fundos disso.
- [x] Linha determinística na resposta a cada escrita aceita, montada pela aplicação a partir do trace. Uma duplicata não anuncia nada — não mudou nada — e uma falha anuncia uma vez por execução, por mais que tenha se repetido.
- [x] Escrita de memória fora da evidência que deriva o status do run (`_without_memory_writes`): sem isso um `remember` recusado por orçamento trocaria uma resposta correta por “não consegui concluir o pedido”. A anotação é efeito colateral, não o pedido.
- [x] `build_scheduled_agent` e o subagente sem as duas tools; a execução agendada lê a memória e não escreve nela. Memória viaja para onde o histórico de conversa deliberadamente não vai: um briefing que não resolve “Builders” é um briefing sobre nada, enquanto histórico deixaria o último assunto conduzir uma execução sem ninguém presente.
- [x] Mapear aliases como “Builders” para o projeto correto sem inventar correspondências — o id continua vindo de busca.
- [x] `docs/development/022-long-term-memory.html`, ADR-014, `docs/index.html` e a seção do README.

Desvio consciente do plano: os números de documentação trocaram. O plano previa `022` para o briefing de pessoa (M9) e `023` para este marco, porque esperava M9 primeiro; a ordem de execução foi outra, e as páginas de desenvolvimento são um registro cronológico. Este marco ficou com `022`/ADR-014 e o M9 com `023`/ADR-015.

Critério de conclusão do marco:

- [~] O usuário diz “Builders” sem explicar, a tarefa nasce no projeto certo com id vindo de busca, o que foi registrado apareceu na resposta que o registrou, e uma preferência revogada some da execução seguinte. As quatro propriedades estão provadas por teste — incluindo o round trip completo em `tests/integration/test_telegram.py` —; a verificação contra o ambiente publicado, com o assistente reconhecendo um apelido real, continua aberta.

### Marco M4 — Calendar Agent

[Referência no PLAN.MD](PLAN.MD#22-marco-m4--google-calendar-no-chief)

- [x] Congelar o DDL de todas as migrations históricas e provar <code>alembic upgrade head</code> em banco vazio sem importar o metadata vivo. O teste SQLite cobre regressão estrutural; o smoke Docker com PostgreSQL vazio chegou à revision <code>20260815_0007</code>.
- [x] Criar <code>GoogleOAuthTokenProvider</code> compartilhado, com access token em memória, refresh antecipado e uma repetição após <code>401</code>.
- [x] Criar <code>scripts/google_oauth.py calendar|gmail</code> com navegador, loopback, <code>state</code>, PKCE e acesso offline; o script imprime o refresh token uma vez e não edita configuração nem banco.
- [x] Adicionar flags e grants separados; integração incompleta ou desabilitada não publica tools.
- [x] Implementar <code>GoogleCalendarClient</code> sobre calendário <code>primary</code>, com paginação, FreeBusy, ETag e escrita sem retry cego.
- [x] Implementar <code>CalendarService</code>: RFC3339 com offset, all-day inclusivo, limite de 31 dias, disponibilidade em <code>APP_TIMEZONE</code> e reconciliação por id gerado antes do create.
- [x] Implementar <code>list_events</code>, <code>create_event</code>, <code>update_event</code> e <code>find_available_slots</code>, com schemas e envelopes.
- [x] Exigir busca única do Chief para <code>update_event</code>; id de filho, memória ou arquivo não concede proveniência.
- [x] Manter Calendar diretamente no Chief durante o M4; o <code>calendar-agent</code> nasce somente no M6.
- [x] Documentar em <code>docs/development/025-google-calendar.html</code>, ADR-016, README, SPEC, PLAN e índice.
- [~] Aceitação live: listar, criar e atualizar evento de teste e limpar pelo harness privado. O código e os testes herméticos estão concluídos; faltam grant/credenciais reais no ambiente desta execução.

### Marco M5 — Email Agent

[Referência no PLAN.MD](PLAN.MD#23-marco-m5--gmail-readdraft-only-no-chief)

- [x] Implementar <code>GmailClient</code> sem método de send nem endpoint de attachment: busca paginada, metadata, MIME full e <code>drafts.create</code>.
- [x] Implementar <code>EmailService</code> com query estruturada/escapada, datas locais convertidas para epoch e MIME plaintext-first com HTML fallback.
- [x] Paginar corpo em até 12 mil caracteres e retornar apenas metadata de anexos, sem download.
- [x] Implementar <code>search_email</code>, <code>read_email</code> e <code>draft_email</code> com schemas estritos.
- [x] Exigir proveniência do run do Chief para read e reply draft; relatório de filho não satisfaz o gate.
- [x] Validar CRLF, endereços, até 20 destinatários e corpo de até 50 mil caracteres.
- [x] Fixar produto como DRAFT sem SEND. Pedido de envio é tratado pelo prompt como oferta de draft; não existe confirmação que possa habilitar uma tool ausente.
- [x] Projetar auditoria antes do insert: endereços, query, subject, snippet e body nunca são persistidos em claro; ficam ids, contagens, flags, tamanhos e hashes.
- [x] Manter Gmail diretamente no Chief durante o M5; o <code>email-agent</code> nasce somente no M6.
- [x] Documentar em <code>docs/development/026-gmail-drafts.html</code>, ADR-017, README, SPEC, PLAN e índice.
- [~] Aceitação live: buscar/ler mensagem conhecida, criar/confirmar draft, provar ausência de envio e limpar pelo harness. Falta grant Gmail real nesta execução.

### Marco M6 — Subagentes

[Referência no PLAN.MD](PLAN.MD#24-marco-m6--subagentes)

- [x] Confirmar três domínios concretos e remover o <code>general-purpose</code>: <code>task-agent</code>, <code>calendar-agent</code> e <code>email-agent</code>.
- [x] Dar a cada filho somente leituras do domínio; compartilhar filesystem read, <code>list_memories</code>, <code>list_reminders</code>, <code>read_url</code> e <code>NOTION_MCP_READ_TOOLS</code>.
- [x] Manter mutations de tarefas/eventos/drafts/memória/lembretes/referências, MCP write, <code>execute</code> e <code>task</code> ausentes e bloqueadas antes do handler.
- [x] Implementar <code>list_memories</code> restrita ao <code>thread_id</code> autenticado, com projeção de auditoria por contagem/tipo/hash.
- [x] Propagar somente origens web autorizadas pela aplicação; origem nova volta em <code>requested_read_origins</code> e o Chief usa o fluxo normal ADR-013.
- [x] Criar scratch isolado sob <code>/tmp/subagents/**</code>, com permissions + gate, teto de 16 arquivos/256 KiB e cópia independente por delegação.
- [x] Remover <code>files</code> do retorno do filho, descartando scratch e resultados offloaded antes de <code>agent_thread_files</code>.
- [x] Normalizar o retorno para <code>DomainReport</code> e auditar <code>task</code> sem briefing nem relatório livre em claro.
- [x] Exigir que o Chief refaça a busca mínima antes de mutar um recurso encontrado pelo filho.
- [x] Testar workspace/anexo read-only, scratch CRUD, path recusado, quotas, isolamento, memória/lembretes, web, MCP read/write, prompt injection e proveniência.
- [x] Documentar em <code>docs/development/027-domain-subagents.html</code>, ADR-018, README, SPEC, PLAN, overview e índice.
- [~] Aceitação live cross-domain: localizar e-mail de orçamento, consultar disponibilidade/referências e criar apenas o draft depois de o Chief refazer a proveniência. Falta ambiente Google real nesta execução.

### Marco M7 — Deployment automatizado

[Referência no PLAN.MD](PLAN.MD#25-marco-m7--deployment-automatizado)

- [ ] Definir fluxo `git push → GitHub → CI → tests → Docker build`.
- [ ] Configurar Container Registry, se necessário.
- [ ] Automatizar deploy na VPS.
- [ ] Definir estratégia de rollback.

### Marco M8 — Tarefas agendadas e notificações

[Referência no PLAN.MD](PLAN.MD#26-marco-m8--tarefas-agendadas-e-notificações)

Depende do M1. O SPEC lista `automações proativas` e `scheduling avançado` fora da V1 — este marco amplia esse escopo de propósito.

Implementado em 09/08. Documentação: [019 — Tarefas agendadas e notificações](docs/development/019-scheduled-jobs.html).

#### Fundação

- [x] Migration `20260809_0006` com `scheduled_jobs` e `scheduled_job_occurrences`, mais índice em `(enabled, next_run_at)`. A regra fica guardada como payload parseado + nome IANA da zona; `next_run_at` é sempre derivado dos dois, em UTC, nunca um offset fixo.
- [x] Coluna `origin` em `agent_runs` (`telegram` | `schedule`), com `server_default` que preenche as linhas existentes. `telegram_update_id` nulo não distinguia execução agendada de chamada direta.
- [x] Task de scheduler no `lifespan` (`app/main.py`), acordando a cada `SCHEDULER_INTERVAL_SECONDS`, reivindicando por `SELECT ... FOR UPDATE SKIP LOCKED`. Sem Redis, sem Celery, sem daemon. `SCHEDULER_ENABLED=false` desliga — necessário numa segunda réplica.
- [x] `croniter==6.0.0` pinado, com a justificativa no próprio `requirements.txt`.

#### Semântica de disparo

Derivada da leitura do `cron/` do [hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT). O que se adaptou foi a semântica, não o código — e o `jobs.json` deles é justamente a escolha que não se repetiu tendo PostgreSQL: a camada de reparo de arquivo corrompido que ela obriga não existe aqui.

- [x] A regra avança e a ocorrência é gravada na mesma transação que reivindica o job, antes de qualquer trabalho. Constraint única em `(job_id, scheduled_for)` como rede: quem perde a corrida registra e não faz nada.
- [x] Backlog colapsa em um disparo e a regra avança para depois de *agora*, não para o horário seguinte ao perdido. Seis horas fora do ar rendem uma notificação, não vinte e quatro; quantos horários foram engolidos vai só para o log.
- [x] `unknown` como estado terminal que não re-tenta, quando o lease expira com a ocorrência em `claimed` ou `delivering`. Sai de graça: a regra já tinha avançado na reivindicação, então não há nada a impedir ativamente.
- [x] Preflight antes de reivindicar, com alerta-uma-vez — um deploy sem bot token não queima um horário por job a cada tick, e o horário continua lá quando a configuração for corrigida.

Desvio consciente do plano: a janela de graça de “metade do período, limitada a `[2min, 2h]`” não foi implementada como escrita. Para um job recorrente ela não mudava nada — ele dispara uma vez de qualquer forma. Onde a graça importa é no *one-shot*, e ali a regra é `ONE_SHOT_MAX_LATENESS = 24h`: abaixo disso o lembrete ainda é entregue mesmo atrasado, acima a ocorrência é gravada como `expired` com o motivo. Um reinício de horas não engole um lembrete; um job ressuscitado da semana passada não incomoda.

#### Notificação

- [x] Três tipos separados: `message` (texto fixo), `task_digest` (consulta o board e renderiza, sem LLM no disparo) e `agent` (`run_agent` sobre um prompt sintético). O digest é o padrão para lembrete recorrente — barato, previsível e sem alucinação.
- [x] Silêncio decidido pela aplicação a partir do envelope da tool. Para um digest quem decide é o `count`; só o tipo `agent` tem prosa a interpretar, e ali o sentinela é o último recurso, não o mecanismo.
- [x] Detecção de mudança por digest SHA-256 do conteúdo renderizado, com `only_on_change`, e o digest gravado *antes* da entrega que ele descreve. A ordem inversa re-alerta sobre o mesmo conteúdo indefinidamente.
- [x] Cabeçalho e rodapé identificam o job e dizem como pará-lo. A entrega reusa `send_reply`, a mesma escada de três degraus da etapa 018 — uma notificação não pode falhar de formatação de um jeito diferente de uma resposta.
- [x] A notificação entregue é anexada à thread como mensagem do assistente, sem inventar um turno do usuário — um turno sintético voltaria como instrução na execução seguinte.

#### Superfície do agente

- [x] `schedule_reminder`, `list_reminders` e `cancel_reminder` em `app/tools/reminders.py`, mesmo envelope `{"ok", "outcome"}`. Aceita `30m`, `every 2h`, `0 9 * * *`, ISO e as formas em português (`a cada 2 horas`, `1 dia`). Timestamp ingênuo ancorado em `APP_TIMEZONE`, e `next_run_at` devolvido ao modelo no relógio local — em UTC ele seria repetido ao usuário e lido como local.
- [x] O escopo do lembrete vem do contexto de correlação que a aplicação já propaga, nunca de um argumento: o modelo emite argumentos e não tem como escrever nesse contexto, então não alcança outra conversa.
- [x] `build_scheduled_agent` publica apenas `search_projects` e `search_tasks`. Verificado por teste de superfície.
- [x] Dois tetos contra laço e custo: `MAX_JOBS_PER_THREAD = 20` regras ativas por conversa, e piso de uma hora para uma regra recorrente do tipo `agent` — o único tipo cujo custo cresce com a frequência.
- [x] Nenhuma auto-aprovação de tool call. A recusa estrutural do `ToolAllowlistMiddleware` cobre o risco por construção, o que dispensa o arsenal de scanners que o hermes-agent precisa manter por ter escolhido o caminho oposto.

Substituído por algo mais forte: o plano previa que um run agendado terminando em `awaiting_approval` enviasse a pergunta e parasse. Isso não pode mais acontecer — a superfície agendada não tem nenhuma tool de escrita, então `awaiting_approval` é inalcançável ali. Uma execução que conclua que uma escrita é necessária diz isso no texto, que chega como notificação, e o usuário resolve na conversa onde o ciclo de aprovação funciona.

Efeito colateral corrigido: ampliar `ALL_TOOLS` de cinco para oito quebrava a mensagem de falha de `_guarded_reply`, que dizia “não consegui consultar o Notion” para uma falha de `schedule_reminder` — que não toca no Notion. A mensagem agora depende de a execução ter chamado uma tool do Notion.

#### Revisão corretiva pós-implementação

- [x] Corrigir o Markdown determinístico do `task_digest` de `**[título](url)**` para `[**título**](url)` e atravessar o resultado até `render_html` e `render_rich_html`; respostas diretas e notificações continuam convergindo no mesmo `send_reply`.
- [x] Fazer o piso de uma hora do tipo `agent` cobrir cron: cinco campos e um único minuto numérico garantem estruturalmente no máximo uma ocorrência por hora; `* * * * *` e extensões de seis campos são recusados.
- [x] Aplicar `only_on_change` também a respostas bem-sucedidas do agente por meio do digest de conteúdo compartilhado. Falhas permanecem sem digest para nunca serem suprimidas como repetição.
- [x] Transformar cancelamento em desativação auditável: regra e ledger são preservados; `claimed → cancelled` impede a entrega e `claimed → delivering` torna explícito que uma chamada já iniciada pode chegar.
- [x] Recuperar leases expirados tanto em `claimed` quanto em `delivering` como `unknown`, sem retry.
- [x] Isolar a colisão da constraint da ocorrência em savepoint, para um `IntegrityError` não abortar a transação PostgreSQL que avança a regra. Coberto por SQLite e por novo teste PostgreSQL opt-in.
- [x] Persistir `finished_at` com um relógio de conclusão injetável, capturado depois do trabalho, em vez de reutilizar o instante do claim.
- [x] Atualizar `README.md`, `docs/development/019-scheduled-jobs.html`, `docs/architecture/decisions.html`, `docs/index.html` e o prompt de cancelamento.

Critério de conclusão do marco:

- [~] Um lembrete recorrente chega no horário certo, sobrevive a um restart do container sem duplicar nem perder disparo, e não envia nada quando não há o que relatar. As três propriedades estão provadas por teste contra SQLite; a verificação contra o ambiente publicado, com uma notificação real chegando ao celular, continua aberta.

### Plano RADAR pós-testes avançados — Fase 2: medição real de indicadores

- [x] Publicar Core 3.2.0 com `record_measurement` aceitando Evidence existente ou inline completa.
- [x] Garantir atomicidade, códigos seguros, revisão otimista, ordem temporal e replay idempotente.
- [x] Criar schema/tool de proposta de medição sem fonte controlada pelo modelo.
- [x] Capturar update/chat/mensagem/autor/timestamp/texto/hash no host e preservar seleção original.
- [x] Ocultar a operação individualmente quando o pacote instalado for incompatível; nenhum fallback para `capture_issue`.
- [x] Cobrir T09: 68 → 75, uma Evidence, +23 pp sobre baseline, −15 pp para meta e campos estáticos preservados.

### Plano RADAR pós-testes avançados — Fase 3: captura fiel e idempotência semântica

- [x] Ampliar `capture_issue` com prioridade validada e Person responsável visível no Issue, nunca no Case.
- [x] Remover `source` do schema do modelo e derivá-lo da mensagem autenticada.
- [x] Persistir fingerprint v1 de ator/contexto/operação/alvo/parâmetros/hash antes da proposta.
- [x] Impedir proposta/execução duplicada para match pendente ou executado dentro da janela configurável.
- [x] Responder por snapshot público salvo e implementar `registrar como novo fato` como override auditado de uso único.
- [x] Manter `radar:<proposal_uuid>` como idempotência de execução e claim atômico na confirmação.
- [x] Cobrir T01/T02, isolamento de owner, duplicata exata, override e aprovação concorrente.
- [x] Criar migration `20260913_0011` e documentar em `038-radar-measurement-semantic-idempotency.html`.

### Integração RADAR no JMR_Personal-CoS

Objetivo: dar ao agente da linha de uso real as leituras, consultas e mutações aprovadas do vault RADAR, sem reescrever o domínio.

- [x] Reaplicar a diferença `b8d89be..cdf1ef9` do `RADAR-CoS-v1` por patch de três vias e resolver os nove conflitos.
- [x] Manter `system_context` do M10 como bloco de `_application_context`, preservando mensagens de sistema consecutivas.
- [x] Reencadear a migration do M10 como `20260927_0012`, depois da `20260913_0011`, com uma só head.
- [x] Renumerar a documentação do M10 para a página 040 e a ADR-026; as páginas 028–039 e as ADR-019 a 025 ficam com o RADAR.
- [x] Pinar `radar-vault` no commit `5f85264` (0.5.0) de `JMR_RADAR_ONTOLOGY`, com token apenas como secret de build. O 0.4.0 inicial foi trocado porque rejeitava o vault real (25 `invalid_relation_target`); o 0.5.0 valida com 0 achados.
- [x] Executar a suíte completa: 1.128 passaram, 11 opt-in ignorados.
- [x] Documentar em `docs/development/041-radar-integration-port.html`, ADR-027 e `docs/index.html`.
- [x] Construir a imagem na VPS com o token do `gh` como secret de build (2026-10-01); o token não aparece no histórico da imagem.
- [x] Preencher o `.env` da VPS (bot `@JMR_manager7bot`, chave Anthropic copiada dentro da VPS, `NOTION_ENABLED=false` por decisão) e registrar o webhook restrito a `message`.
- [x] Vault populado (47 entidades, escopo `manager:joao-marcos-ramos`, pessoa `PER-20261002-ACBDFE`), montado no container e `RADAR_ENABLED=true` só para leitura em 2026-10-02: preflight `ready`, 0 erros de validação, pacote 0.5.0. Ligar o RADAR antes disso deixou o agente respondendo que não tinha acesso ao vault.
- [x] Homologar as leituras pelo Telegram antes de habilitar `RADAR_WRITES_ENABLED`: confirmado pelo usuário em 2026-10-02.
- [x] Liberar as escritas aprovadas em 2026-10-02: `RADAR_WRITES_ENABLED=true` com `capture_issue,delegate,review,record_measurement`, aprovação persistida de 900 s e `RADAR_MANAGER_CONTEXTS` vazio. O container grava no vault e as quatro tools `radar_propose_*` aparecem na superfície.
- [ ] Validar uma escrita real de ponta a ponta pelo Telegram (proposta, aprovação, nota nova no vault e chegada ao Mac pelo Sync).

### Marco M10 — API RADAR para cos-mariana

Objetivo: permitir round-trip autenticado do simulador sem reutilizar a identidade Telegram nem a superfície operacional do Chief.

- [x] Implementar os endpoints compatíveis com o contrato alvo: criação de thread, envio de mensagem, consulta de status e health público.
- [x] Proteger criação/envio/consulta por Bearer `RADAR_API_KEY`; ausência de configuração desabilita as rotas autenticadas.
- [x] Validar modelos fechados, tamanho do conteúdo, UUIDs, dia/instante simulado com fuso, identidade da sessão e `Idempotency-Key`.
- [x] Persistir sessões e ledger de mensagens, hash do payload, lease, status e resposta confirmada com migration `20260927_0012` aplicada sobre a head de produção `20260913_0011`.
- [x] Usar thread sintética separada e auditar execuções com `origin="radar"`.
- [x] Renovar o lease durante inferências ativas; após queda do processo, deixar expirar para `unknown`.
- [x] Montar agente dedicado sem tools, subagentes, workspace, memória ou acesso às integrações pessoais.
- [x] Cobrir auth em criação/status, `202 processing`, criação idempotente, resposta, replay, conflito de payload, identidade, timestamp com fuso e renovação do lease nos testes herméticos; validar polling limitado e a chave fraca no adapter HTTP.
- [x] Adicionar `scripts/check_radar_connection.py` no `cos-mariana` como smoke opt-in de um round-trip real.
- [x] Documentar a arquitetura, o contrato e os trade-offs em `docs/development/040-radar-api-connection.html`, ADR-026 e `docs/index.html`.
- [x] Publicar o patch M10 sobre uma cópia isolada da imagem ativa, sem sobrescrever o checkout remoto com alterações pendentes; construir `personal-cos-agent:radar-20260927`, aplicar migration `0012` e manter tag de rollback e backup PostgreSQL.
- [x] Configurar a mesma chave aleatória de 64 caracteres nos `.env` do Personal-CoS e do `cos-mariana`, sem registrá-la no repositório ou na documentação.
- [x] Validar HTTPS público (`/health` HTTP 200), Bearer ausente (`POST /v1/threads` HTTP 401) e o smoke real via `HttpRadarClient`; a resposta chegou como `connected` com `thread_id` e `run_id`.

Critério de conclusão do marco:

- [x] Os testes locais provam compatibilidade e idempotência do contrato: 77 testes do Personal-CoS e 13 do cliente HTTP passaram em 2026-09-27.
- [x] A adaptação do endpoint, migration `0012` e agente sem tools sobre a fonte extraída do container passou 10 testes de API/migration e um teste focado do agente (11 no total, 2026-09-27).
- [x] O `HttpRadarClient` real completou, contra a API FastAPI port em ASGI e com runner falso, criação de thread e duas mensagens; a segunda recebeu histórico e contexto do dia 2.
- [x] A comunicação entre os processos foi confirmada em 2026-09-27: o smoke do `cos-mariana` criou thread sintética e recebeu uma resposta concluída do Personal-CoS por HTTPS.

## Backlog futuro

Itens preservados do [backlog futuro do PLAN.MD](PLAN.MD#28-backlog-futuro), sem antecipar implementação:

- [ ] Experience: comandos Telegram, botões inline, respostas estruturadas, resumo diário, captura rápida e inbox universal.
- [ ] Agent: subagentes, long-term memory, planning, background workflows, reflection e routing.
- [ ] Integrations: Calendar, Gmail, Drive, GitHub e web search, além do Notion já priorizado.
- [ ] Observability: dashboard, tracing, custos, token usage, latência e taxa de erros das tools.
- [ ] Definir métricas após existir volume de uso: runs/dia, tool calls/dia, taxa de sucesso, falhas, latência, custo, tarefas criadas, correções e taxa de ambiguidade.
- [ ] Medir especialmente o percentual de ações corretas sem correção humana.

## Guardrails de execução

- [ ] Implementar sempre na ordem `código determinístico → tool → agent → interface`.
- [ ] Consultar `SPEC.MD` e `PLAN.MD` antes de cada item de implementação.
- [ ] Não começar uma funcionalidade pelo prompt.
- [ ] Não adicionar integrações, bibliotecas ou infraestrutura fora do plano sem necessidade comprovada e decisão documentada.
- [ ] Não criar subagentes prematuramente.
- [ ] Após cada marco funcional, usar o sistema de verdade e registrar fricções.
- [ ] Parar quando a tarefa do marco estiver concluída; não expandir o escopo automaticamente.
