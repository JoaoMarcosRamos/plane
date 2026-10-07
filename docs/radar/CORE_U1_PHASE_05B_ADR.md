# RADAR Core U1 — 5B: fatos operacionais canônicos

**Data:** 06/10/2026, America/Bahia. **Decisão:** C18. [Plano](CORE_U1_IMPLEMENTATION_PLAN.md).

## Fontes e prazo efetivo

Executores correntes vêm exclusivamente das relações ativas `assigned_to`. A delegação escreve o prazo datetime na propriedade semântica Action `due_at`, preservando instante e microssegundos; o backfill conserva também o literal legado com seu offset; `due_date` conserva sua semântica de data. Não há cópia automática entre os dois.

No query do runtime, prazo/schema/migration_required ficam no namespace já reservado `metadata.operation_data`, preservando nomes de propriedades do workspace. Today, detalhe e runtime usam a mesma função de projeção, com fuso IANA explícito e default UTC. Um datetime vence quando o instante passa; uma data vence quando seu dia termina no fuso. Se a data e o dia local do datetime coincidem, o datetime refina a data. Se divergem, a projeção declara conflito, apresenta ambos e não escolhe uma fonte silenciosamente. Today inclui o conflito para revisão, mesmo antes do vencimento. Editar a propriedade ou trocar relações não altera termos históricos: a projeção informa termos alterados e invalida aceitação corrente derivada de termos anteriores.

## Registros e autoridade

`OperationalEntry` é histórico imutável tipado e versionado de delegation/review/measurement. Autor original, instante, versão do Object e provenance são explícitos. `created_provenance` vincula cada escrita ao CommandExecution (via command_id), ou ao command administrativo de backfill. FKs de evidência e referências no payload pertencem ao mesmo workspace. Replay usa o ledger existente e não insere novo histórico.

A projeção corrente deriva dos últimos registros especializados e das fontes canônicas; não é um writer concorrente. JSON `OperationalRecord.data` torna-se arquivo legado: novos writers deixam de atualizá-lo. Reviews/measurements não acumulam listas nesse JSON. `assigned_to`, `due_at`, `current` e `measured_at` têm seus writers comuns já autorizados pelo planner; registros guardam o fato histórico, sem ampliar grants. History e projeção são pagináveis/delimitados e têm autorização distinta para leitura histórica de Objects retirados.

## Migração e rollout

Primeiro: inventário somente leitura do stack local, sob `SET TRANSACTION READ ONLY`, e relatório de divergências. No stack em uso, a tabela legada estava ausente; a validação de arquivos representativos ocorre no banco descartável. Depois: expansão estrutural 0016, sem backfill automático dos fatos. `radar_operational_backfill` faz dry-run por workspace; apply exige administrador, hash revisado e reason. Backfill é transação auditada, idempotente por origem/índice e hash do arquivo. Relações correntes divergentes são preservadas e sinalizadas; prazo canônico existente conflitante, payload inválido ou referência de outro tenant bloqueiam, sem reparar fatos silenciosamente.

Originais, timestamps, offset, evidência e fonte ficam preservados no arquivo e em source_data. Um UUID de actor legado sem tipo comprovado é `unknown`; ausência de instante/versão original permanece nula. Não atribuir esses fatos ao administrador do backfill: seu papel consta no provenance da migração. O arquivo não pode mudar após importação sem nova reconciliação. Escritas operacionais sobre arquivo não reconciliado são bloqueadas até o backfill.

Executar inventário/dry-run, exportar originais, revisar hash, aplicar, verificar contagens/projeções e só então liberar novos writers. Não existe dual-write contínuo. Rollback de aplicação exige exportação compatível de todos os registros e preparação de restauração; voltar ao leitor antigo isoladamente oculta os fatos novos. A migration bloqueia reversão destrutiva automática. O CLI exporta arquivo e histórico para preparação de recuperação, sem destruir tabelas.

## Limites

Não implementa nova negociação/aceitação de delegação nem C13/aceite integrado. Registros especializados continuam fechados e tipados. Não é event sourcing geral. O stack publicado não é migrado nem recebe backfill nesta entrega.
