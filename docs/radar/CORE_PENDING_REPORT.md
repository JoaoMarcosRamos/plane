# RADAR Core — C13, C23 e medição C14

**Data:** 07/10/2026, America/Bahia. **Escopo autorizado:** implementações pendentes do [CORE_AUDIT.md](CORE_AUDIT.md). C13 e C23 corrigidos; diagnóstico e instrumentação de C14 entregues, mantendo a coordenação conservadora como limite explícito. Nenhum deploy ou alteração do stack Plane em uso.

## Consultas delimitadas — C13

- `GET objects/` retorna resumos sem `content` ou cópias dos descritores de tipo. Preserva o formato de array; `X-Radar-Schema-Revision` e `X-Radar-Next-Cursor` carregam revisão/continuação, expostos por CORS. Default 50, máximo 100; o cliente precisa consumir o cursor para obter os demais objetos. Consumidores que dependiam de narrativa/descritores na lista devem usar detalhe/schema.
- Filtros: `q`, `object_type`, `type_keys`, `exclude`, capability **de criação**, `relation_type`, `object_id` e `direction`. Capability de criação inclui o fallback registrado de tipos customizados sem descritor. Hints de parâmetros de capabilities usam busca por tipos; sua execução continua verificando requisitos, evidência e autoridade pelo dispatcher.
- Busca de relação aplica membership de escrita, workspace, tipos/endpoints ativos, domain/codomain, pares permitidos, self-link, duplicatas e cardinalidade nas duas direções. Usa `Exists` no SQL; filtra antes de paginar. Escrita continua revalidando sob locks.
- Cursores assinados expiram em uma hora e vinculam workspace, filtros, revisão e, para relações, Object.version. Ordenação estável por UUID; não é ordem cronológica. Inserções/edições concorrentes de uma lista podem exigir uma nova busca; não há snapshot MVCC entre requests.
- Relações/backlinks paginam com resumos apenas dos endpoints daquela página. Capacidades de remoção também são delimitadas: primeiros 50 IDs ou lote explícito de até 100 IDs, sempre filtrado pelo Object/workspace. O cliente une as permissões ao carregar mais relações.
- Object Page deixa de chamar a lista de objetos. Seletores de relação e de referências de capabilities usam busca remota, debounce, continuação e seleção preservada. O endpoint relacionado é lido com sua versão antes de criar/remover a relação; retries conservam a intenção original.
- Respostas antigas de busca/lista não substituem os filtros novos. Resumos não apagam narrativa já carregada da mesma versão. Perda de membership limpa objetos, snapshots e endpoints, e impede que respostas atrasadas repovoem o cache.
- Migration `0017_query_page_indexes`: quatro índices parciais sobre objetos ativos por workspace/UUID/tipo e relações ativas por workspace/endpoint/UUID. Não modifica fatos ou metadata.

**Medição:** fixtures de 10, 110 e 1.010 objetos, cada narrativa com 10 kB; página de cinco resumos mantém **3.301 bytes, dez queries e LIMIT 6** sem selecionar `Object.content`. Tempos locais nas execuções dirigidas: aproximadamente **4–7 ms**. Meta inicial para repetir esse smoke no mesmo ambiente: abaixo de 50 ms por request; não é SLO de produção nem teste temporal rígido em CI. O limite demonstrado é de objetos materializados/payload/queries de lista. Busca textual e validações podem examinar mais linhas no PostgreSQL; não se presume custo constante de varredura nem benchmark de grandes tenants. Probes de capabilities têm custo por relação da página.

## Navegação pelo catálogo — C23

Sidebar e home separam ferramentas funcionais de tipos ativos do workspace. Nome/chave vêm do schema; cada tipo abre `type-<key>` com a lista genérica filtrada no servidor. Tipos com nomes de ferramentas não colidem com suas rotas. Inativação remove a entrada; bookmarks indisponíveis mostram mensagem de indisponibilidade. Os bookmarks `decisions`/`risks` são aliases de compatibilidade para as views de tipos existentes. Não há placeholder nessas views nem mensagem fixa de agente não implementado.

Não foi criado model, handler, migration de domínio ou tela por tipo. A apresentação customizada e os campos required/default continuam os contratos das fases 3/4. Ocultação/ordenação personalizada da navegação e builders completos não fazem parte desta entrega.

## Locks observados — C14

`plane.radar.locks` registra aquisição (`wait_ms`) e finalização (`held_ms`, operação, resultado e `outermost`) sem dados de payload/credenciais. O logger INFO está ligado ao formatter JSON do ambiente local/produção. Commands, schema install/upgrade/metadata e snapshots HTTP usam a mesma coordenação observada. Atomicidade, locks de Object, grants, revisão de schema e replay permanecem os mesmos.

O teste PostgreSQL concorrente mantém deliberadamente um lock por 200 ms. Outro request do **mesmo workspace espera aproximadamente 205 ms**; outro workspace adquire em aproximadamente **1–2 ms**. O teste cobre commit, rollback e amostras aninhadas, sem alegar throughput de produto. `held_ms` termina no commit do escopo observado; `outermost=false` informa que um caller externo ainda possui a transação e pode reter o lock além desse intervalo.

**Decisão:** manter a coordenação por workspace. A medição confirma seu custo e a independência entre tenants; não fornece workload de produção para justificar uma divisão dos locks que hoje coordenam schema/autoridade/replay. C14 passa de diagnóstico pendente a **limite arquitetural medido**, não a otimização implementada. Uma alteração futura de granularidade precisa medir p95/p99 de espera/retenção e throughput com o workload alvo, além de testar mudanças de schema/grants concorrentes e replays.

## Aceite integrado e validação

O teste integrado configura um tipo customizado por commands auditados, com summary obrigatório, estado/default, lifecycle, apresentação e relação 1..1. Criação incompleta é recusada; transição sem relação é bloqueada; criação/ligação/transição passam pela API de sessão. Opt-in e provisioning explícitos habilitam identidade/contexto de runtime, com o target da relação obrigatória vinculado no mesmo contexto. Metadata alterada invalida a proposta pendente, enquanto a execução já confirmada faz replay único. Inativação retira o objeto da leitura operacional e preserva provenance histórica.

No navegador, componentes de produção criaram um Object do tipo customizado configurado na fixture, buscaram Objective 110 fora da primeira página, persistiram a relação obrigatória e a transição Open→Working. Outra página exibiu 55 backlinks via continuação, carregou permissões dos endpoints da segunda página e removeu uma relação com leitura prévia da versão. A lista por tipo carregou 50→100 objetos; home expôs o tipo customizado. API, sessão, commands e PostgreSQL são reais; editor rico e identidade/permissões visuais usam stubs. O shell completo não foi homologado. Prova independente: [browser-proof.json](../../apps/api/output/core-pending-browser-proof.json); capturas inspecionadas em [output/playwright](../../output/playwright).

| Verificação    | Resultado                                                                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend final  | **557 RADAR + 2 Plane aprovados**, 3 opt-ins ignorados; 15 casos novos. Adapter CoS real in-process incluído                                            |
| Frontend       | **154 aprovados em 21 arquivos**                                                                                                                        |
| Workspace      | **56/56 tarefas de `pnpm check`**                                                                                                                       |
| Python/schema  | Ruff aprovado; formato RADAR aprovado; nenhuma migration ausente                                                                                        |
| Migration 0017 | Ida/volta/reaplicação, preservando 112 Objects e 56 Relations; índices verificados                                                                      |
| Navegador      | Criação/relação/lifecycle, busca fora da primeira página, backlinks/permissões/removal, lista paginada e home; zero erros de console na navegação final |

A primeira tentativa de regressão completa se sobrepôs a testes dirigidos no mesmo `test_plane`, gerando dois conflitos de usuários de fixture. Foi descartada como evidência final e reexecutada sozinha com `--create-db`. Os logs iniciais também conservam ajustes dos testes à API compacta, autorização de leitura de candidatos e preparo de fixtures; não representam falhas abertas.

Reprodução, comandos e limitações em [evidências](../../output/core-pending-20261007/README.md). As suítes anteriores U0–5B e o adapter CoS in-process integram a regressão final; providers/CoS HTTP reais continuam opt-in. Nenhum token/credential foi exposto. A aplicação de 0017 no ambiente alvo e sua homologação operacional continuam atividades de ativação, não realizadas aqui.
