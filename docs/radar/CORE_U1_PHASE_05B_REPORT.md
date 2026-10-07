# RADAR Core U1 — entrega 5B

**Data:** 06/10/2026, America/Bahia. **Achado:** C18. [Plano](CORE_U1_IMPLEMENTATION_PLAN.md), [decisões](CORE_U1_PHASE_05B_ADR.md), [evidências e reprodução](../../output/core-u1-phase-05b-20261006/README.md).

## Entrega

Executores correntes vêm das relações ativas `assigned_to`. `DelegateAction` escreve a propriedade semântica datetime `Action.due_at`, exigindo definição ativa e compatível. `due_date` continua sendo data, sem conversão automática. Uma projeção compartilhada calcula prazo efetivo e vencimento no fuso IANA informado (default UTC). Quando a data diverge do dia local do datetime, informa ambos e declara conflito, sem escolher silenciosamente um prazo. Today inclui delegações atrasadas sem `due_date` e conflitos, inclusive futuros; o detalhe e o runtime usam o mesmo cálculo. No protocolo de query do runtime, a projeção fica em `metadata.operation_data.deadline`, preservando propriedades locais que tenham o nome `deadline`.

`OperationalEntry` guarda delegações, reviews e medições em registros imutáveis, com payload v1 validado, autoria, instante, evidência, versão do Object e provenance vinculada ao command. A projeção corrente deriva dos últimos registros e das propriedades/relações canônicas. Trocar executores/prazo preserva os termos históricos e sinaliza que a aceitação anterior não representa os termos novos. Medições correntes vêm de `current`/`measured_at` ativos. Não foi criado um novo fluxo de negociação ou aceitação.

Novas operações deixam de escrever `OperationalRecord.data`. O arquivo legado permanece para rastreabilidade. A leitura corrente seleciona somente os últimos fatos; o histórico usa cursor por Object/kind, limite 1–100 (20 na UI), índices próprios e uma query de página, sem carregar o arquivo JSON, `source_data` ou o JSON de alterações da provenance. O endpoint histórico autoriza explicitamente Objects retirados da operação; a projeção corrente usa a política ativa. Grants, planos de efeitos e replay continuam no dispatcher comum, incluindo autoridade sobre `due_at` e `assignment`.

A Object Page apresenta prazo, executores e histórico, com filtro e carregamento de páginas. A store compara Object version e schema revision, ignora respostas atrasadas, rejeita leituras de revisões distintas e descarta histórico após conflito/perda de acesso. Atualizar o painel usa leituras do Object, sem recarregar a lista do workspace. `due_at` aparece no fallback de propriedades adicionais do layout existente; o teste da fase 4 foi ajustado para verificar esse novo campo.

## Migração e reconciliação

A migration **0016_operational_history** cria a tabela/índices e instala a definição de prazo nos tipos Action semeados. Atualiza a base gerida/revisão do schema, preserva definições locais existentes e não migra fatos automaticamente. Definição local incompatível deve ser reconciliada antes de delegar.

O inventário anterior à migração foi somente leitura, sob `SET TRANSACTION READ ONLY`, no stack local em uso. **A tabela `radar_operational_records` não existe nesse stack** (`legacy_table_present=false`); as contagens zero não comprovam um arquivo instalado vazio. A prova de migração/backfill usa dados representativos no PostgreSQL descartável.

O CLI administrativo `radar_operational_backfill` faz dry-run, exportação streaming e apply com hash revisado e motivo explícito. A transação preserva arquivo/timestamps, literals de prazo com offset/microssegundos, evidências, provenance de origem e payloads originais em `source_data`. Ausência de autoria comprovada, instante ou versão original fica explícita como `unknown`/null. O administrador é autor da migração, não dos fatos originais.

Referências indisponíveis ou de tipo incorreto, payload inválido, prazo canônico conflitante e arquivo alterado após importação bloqueiam apply atomicamente. Relações divergentes são preservadas e sinalizadas. Repetir o backfill não duplica fatos; operações novas sobre arquivo não reconciliado são bloqueadas. Não há dual-write. Reversão destrutiva da migration é bloqueada: rollback de aplicação exige exportação compatível e restauração preparada. A exportação foi verificada; não se afirma que um restore operacional completo tenha sido executado.

## Validação

| Verificação                | Resultado                                                                                                                                                             |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend final              | **542 RADAR + 2 Plane aprovados**, 3 opt-ins de HTTP CoS desativados; **26 casos C18 novos**                                                                          |
| Contratos dirigidos finais | **41 aprovados**, incluindo C18, namespace e adapter CoS real com HTTPX in-process                                                                                    |
| Frontend                   | **147 aprovados em 20 arquivos**, 15 casos novos                                                                                                                      |
| Workspace                  | **56/56 tarefas** de `pnpm check`, incluindo tipos, lint, formato e paridade de contratos                                                                             |
| Python/model/migration     | Ruff/formatação aprovados; `makemigrations radar --check --dry-run` sem mudanças pendentes                                                                            |
| Migration/backfill         | Upgrade real em banco isolado, originais/offset/microssegundos/customização/identidades preservados, idempotência e export verificados; reversão destrutiva bloqueada |
| Navegador/dados            | Fluxos de leitura confirmados sobre API e PostgreSQL reais, capturas inspecionadas e prova independente no banco                                                      |

O navegador usou Today/Object Page, service e stores de produção sobre API, sessão, commands e PostgreSQL reais. Editor rico, seletor de membros e identificação/permissões visuais do usuário usam stubs do harness; a autorização dos endpoints usa membership real. Confirmou prazo sem data, conflito explícito, 24 fatos em páginas 20/4, filtro de 23 reviews em páginas 20/3, três medições, guest lendo legado sem autoria/instante inventados e descarte do histórico após mudança para sessão sem membership. Prova independente no banco confirmou fontes canônicas, vínculos execution/provenance e ausência de novas escritas no arquivo legado.

As capturas foram inspecionadas. O harness apresenta warnings de módulos externalizados pelo Vite; a navegação inicial teve favicon ausente. As respostas 403 no cenário de perda de acesso são esperadas. A página final de Today não apresentou erros de console.

## Próxima pendência e limites

C18 fica concluído no código. O saldo da auditoria passa a **20/23 corrigidos**, com **C13 (U1)** e **C14/C23 (U2)** pendentes. A próxima implementação é a fase 6: consultas delimitadas para detalhe/seletores e aceite integrado. As cargas amplas preexistentes da Object Page/runtime pertencem a C13; a nova paginação não afirma resolver esse achado.

Não houve deploy, migration/backfill no stack em uso, alteração do repositório CoS, provider externo nem homologação completa de U1. A ativação exige a cadeia de migrations, schema explícito por workspace e reconciliação dos arquivos legados no ambiente alvo. Mudanças anteriores do worktree foram preservadas; nenhum commit foi criado.
