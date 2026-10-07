# RADAR U1 — Decisões das fases 0 e 1

**Data:** 06/10/2026, America/Bahia. **Escopo autorizado:** fases 0 e 1 do [plano U1](CORE_U1_IMPLEMENTATION_PLAN.md). As decisões sobre schema/lifecycle/runtime orientam fases posteriores; não ativam builders nesta entrega.

## Base e ambiente

O manifesto inicial e a cópia dos fontes em [output/core-u1-phase-01-20261006](../../output/core-u1-phase-01-20261006) preservam o filesystem anterior à implementação, incluindo alterações staged, unstaged e untracked. A comparação da entrega será contra essa base, não contra HEAD.

Inspeção somente leitura do stack `plane` em uso: `showmigrations radar` informa que o app RADAR não está instalado; o banco `plane` não contém migrations nem tabelas `radar_%`. Portanto a pendência de ativação não se limita a aplicar 0011: exige disponibilizar o app/código RADAR e sua cadeia de migrations. Esta entrega valida em stack isolado e não altera esse ambiente. Outros ambientes não foram inspecionados.

## Ownership e evolução de schema

O pacote de ontologia fornece uma base instalada; o workspace é dono da configuração efetiva. Upgrades futuros devem comparar base instalada, configuração local e pacote candidato. `is_system` não autoriza sobrescrever personalizações. IDs e inativações intencionais são preservados; alterações incompatíveis exigem relatório e migração explícita. Na fase 1, bootstrap continua idempotente por estado e auditado, sem ledger de intenção por GET.

## Leitura operacional e histórica

Na fase 2, a política operacional deverá excluir tipos/definições/relações/endpoints inativos ou excluídos. Histórico tem consulta explícita e autorização própria. A fase 1 publica as interfaces de consulta existentes sem alegar que unificou todas as queries de C11. Provenance permanece fonte da identidade histórica do actor; uma FK User nula não significa usuário excluído.

## Prazo, atribuição e registros

Executores correntes deverão ter fonte canônica em `assigned_to`. Prazo de delegação precisa preservar precisão datetime de `due_at`; `due_date` mantém seu significado de data até reconciliação explícita. O prazo efetivo compartilhado por Today/UI/runtime deverá ter política de fuso e diagnóstico de divergências antes do backfill da fase 5. Reviews/measurements/acceptances permanecem fatos operacionais tipados, com histórico paginável e origem rastreável. Não transformar listas JSON nesta fase.

## Narrativa e lifecycle

Title/UUID/version permanecem envelope comum. Apresentação futura declara narrativa principal e notas complementares; divergências entre content/description/context não são resolvidas por cópia automática. Tipo customizado não ganha transições nem autoridade de runtime implicitamente; lifecycle futuro seleciona operadores/capabilities registrados, sem scripts ou workflows arbitrários.

## Interfaces e compatibilidade da fase 1

Publicar lookup ativo, valores efetivos, membership, evidência/aprovação e helpers de execução usados entre módulos. Commands retornam DTOs de aplicação sem importar serializers da API. Manter nomes/campos e formatação dos resultados HTTP e dos resultados antigos do ledger; autoria no resumo HTTP é uma extensão aditiva. Preservar o fingerprint U0: intents pendentes sob código anterior exigem novo preview/review; execuções confirmadas continuam retornando resultados históricos.

Inicialização de defaults pública passa pelo ledger compartilhado como command human-only. A API retorna o snapshot confirmado persistido, mesmo quando a versão atual já mudou; o caller pode buscar estado corrente separadamente. Callers Python confiáveis podem continuar omitindo versões/chave, com o limite documentado na compatibility layer.

## Retry no cliente

A store mantém em memória uma intenção por operação/target, com payload copiado, chave, reason e expected_versions estáveis. Resposta incerta conserva a intenção; submit com conteúdo diferente cria outra; resposta 4xx definitiva encerra a tentativa; conflito exige refresh e nova revisão antes de novo submit. Aprovação pendente conserva a intenção e seu approval ID para retomada. Mudança de versão da cache não rebaseia retries incertos.

Não persistir intenções em localStorage nesta fase. O escopo é a instância de store do workspace/sessão; troca de usuário deve recriar o provider. Reload encerra esse escopo: depois de resposta incerta, consultar estado antes de reenviar criação como nova intenção. Garantir replay atravessando reload exige produto/armazenamento adicional e fica explicitamente fora deste contrato de retry.

## Inventário e validação

O [inventário inicial](../../output/core-u1-phase-01-20261006/phase0-inventory.json) registra imports privados, consumers do catálogo, estrutura operacional e compatibilidade. Não há OperationalRecord legado no stack inspecionado; dados de outro ambiente exigirão inventário antes da fase 5. O [relatório de entrega](CORE_U1_PHASE_01_REPORT.md) registra os resultados executados, migrations e limites finais.
