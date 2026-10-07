# RADAR Core U1 — Entrega das fases 0 e 1

**Data:** 06/10/2026, America/Bahia. **Escopo:** fases 0 e 1 do [plano U1](CORE_U1_IMPLEMENTATION_PLAN.md), autorizadas após sua elaboração. Decisões: [ADR](CORE_U1_PHASE_01_ADR.md). **Status:** fases 0 e 1 concluídas e validadas em ambiente isolado; C15, C16 e C22 corrigidos no código.

## Resultado implementado

| Achado | Correção                                                                                               | Evidência                                                                    |
| ------ | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| C22    | Resumos de criação/edição por provenance e actor, com resolução de humanos em lote                     | Testes humanos/não humanos/legados, limite de queries e Object Page real     |
| C16    | Interfaces públicas para contexto, membership, queries, validação e efeitos; DTOs sem serializers HTTP | Teste de fronteiras/imports e paridade da representação v1                   |
| C15    | Defaults no ledger comum e intenção estável de retry na store                                          | Replay histórico, rollback, revogação, resposta perdida e aprovação pendente |

As fases seguintes continuam pendentes. Este trabalho não publica builders nem torna lifecycle, contexto de runtime e apresentação configuráveis por metadata.

## Fase 0 — Base e decisões

Preservados hashes e cópia dos fontes anteriores à edição em [output/core-u1-phase-01-20261006](../../output/core-u1-phase-01-20261006/README.md). O worktree já continha alterações staged/unstaged/untracked; o manifesto diferencia esta entrega dessa base, sem usar o diff contra HEAD como prova de autoria das mudanças.

Baseline executado: **301 backend RADAR aprovados, 4 opt-in ignorados; 93 frontend aprovados**. O inventário inicial registra 20 imports privados entre módulos, consumers do catálogo e estrutura de `OperationalRecord`. O ADR define ownership do seed/customizações, leitura operacional/histórica, prazo/atribuição, narrativa, lifecycle e limite do retry em memória.

Inspeção somente leitura do stack `plane` em uso confirmou **app RADAR não instalado, zero migrations e zero tabelas RADAR**. A ativação futura requer disponibilizar o app e aplicar sua cadeia de migrations, incluindo 0011. Não há `OperationalRecord` legado nesse stack; não se presume ausência em outros ambientes. O stack em uso não foi alterado.

No banco descartável, o round-trip **0010 → 0011 → 0010 → 0011** passou, preservando identidades e tipo customizado, instalando as duas regras normativas. Não há nova migration de produto na fase 1; o check de migrations confirmou isso.

## C22 — Autoria efetiva

[authorship.py](../../apps/api/plane/radar/authorship.py) resolve `created_actor` e `updated_actor` usando os ponteiros de provenance. O resumo inclui actor_type, actor_id, display_name quando disponível, user_status, source, timestamp e provenance_id. Diferencia humano disponível, identidade humana histórica sem User, ator não humano e autoria desconhecida. FKs User existentes permanecem na representação para compatibilidade.

[ObjectSerializer](../../apps/api/plane/radar/api/serializers.py) acrescenta os resumos em leituras HTTP. Na listagem, Object/type/provenance são carregados por join e nomes humanos por uma consulta em lote: **duas queries para seis Objects com dois autores**, verificadas em teste. A [Object Page](../../apps/web/components/radar/object-page.tsx) mostra humano, agente, sistema e integração com labels distintos; null isolado passa a autoria desconhecida.

No navegador, a criação por integração continuou atribuída à integração após edição humana, e `updated_actor` passou ao humano com versão 2. Reload e consulta PostgreSQL confirmam persistência. [Captura](../../output/core-u1-phase-01-20261006/browser-integration-human-edit.jpg).

## C16 — Fronteiras públicas

Publicados os contratos de [contexto](../../apps/api/plane/radar/commands/context.py), [membership](../../apps/api/plane/radar/commands/access.py), [queries/validação](../../apps/api/plane/radar/commands/queries.py) e [DTOs de resultado](../../apps/api/plane/radar/commands/results.py). Helpers de primitives, provisioning e efeitos usados por outros módulos receberam nomes públicos; callers de operations, runtime, Risk Review, API e management commands foram atualizados.

Handlers não importam `ObjectSerializer` nem `RelationSerializer` da API. Os DTOs mantêm a representação v1 dos resultados persistidos, incluindo UUIDs como strings e timestamps ISO. Testes comparam essa representação ao JSON dos adapters e impedem novos imports privados entre módulos/serializers API nos commands.

A tradução comum de membership foi extraída e reutilizada na autorização de primitives e execução. Isso não encerra C09: planejamento/autoridade de efeitos compostos e demais traduções operacionais continuam para fase 3. Django, DRF e serializers de inputs compartilhados permanecem; não houve substituição do framework.

## C15 — Defaults e retries

`InitializeObjectProperties` tem input tipado e execução pelo dispatcher/ledger existente. Continua **human-only**, inclusive perante grant forjado; provisioning não permite concedê-lo a atores não humanos. Bootstrap de tipos/definições continua idempotente por estado e auditado no caminho interno.

O endpoint POST de defaults usa [initialize_properties_command](../../apps/api/plane/radar/commands/semantic.py) e devolve o snapshot confirmado em `CommandExecution.result`. Replay com mesma chave/input retorna esse snapshot antes de verificar versões antigas; alterações posteriores no Object não reescrevem o resultado histórico. Na primeira execução, autoria é resolvida após o flush de provenance. No-op também tem um único resultado confirmado; falha de validação reverte ledger, propriedades, versões e auditoria.

`initialize_object_properties` preserva o retorno Object para callers Python confiáveis. Na compatibility layer, chave existente com versões omitidas recupera o mapa original do ledger; versões fornecidas pelo cliente não são substituídas. Transport continua exigindo expected_versions e Idempotency-Key.

[RadarMutationIntents](../../apps/web/store/radar/mutation-intents.ts) conserva input copiado, chave e expected_versions de criação, edição, defaults, propriedades e relações. Timeout/5xx não troca a intenção; resposta 4xx definitiva a encerra, exceto timeout/rate limit. Não há retry automático nem rebase automático após conflito. Erros 409 orientam refresh e revisão.

Aprovação pendente conserva a intenção. O approval ID só é anexado por `resumePendingMutation` após retomada explícita; o servidor continua verificando o review. Submit simultâneo na mesma operação é bloqueado. A troca de workspace/usuário recria o provider e isola as intenções.

**Limite declarado:** estado em memória, sem persistência após reload. Depois de resposta incerta e reload, consultar estado antes de enviar criação como nova intenção. Uma mudança de input significa nova intenção; não implica cancelamento automático de um command antigo pendente no servidor. Compatibilidade Python sem versões segue restrita a callers confiáveis.

## Validação e limites

Os comandos, logs, manifests e capturas ficam no [diretório de evidências](../../output/core-u1-phase-01-20261006/README.md). A regressão final teve **323 casos backend: 319 aprovados, 4 opt-in ignorados, zero falhas/erros**, incluindo os **18 casos U1 novos**. O frontend teve **106 casos aprovados em 15 arquivos**, incluindo oito cenários novos de retry e cinco de apresentação de actor. `pnpm check` passou com **56/56 tarefas** (53 em cache); Ruff, formatação Python, migration check e round-trip passaram. Não se somam reexecuções às contagens finais. O check do monorepo apresentou avisos de cache/IO do sandbox e avisos Vite/PostCSS existentes, sem falhar.

A bancada de navegador usa Object Page, stores/services de produto, sessão Django, API e PostgreSQL reais. Permissões no hook da UI, member picker e editor de notas são fixtures explícitas; não representam novo E2E do shell/login completo. Foram verificados rótulos dos quatro actors, edição humana de Object criado por integração, reload e ausência de erros de console. Agent-browser CLI não iniciou Chromium devido à restrição de Mach ports do ambiente; a verificação foi concluída com Chrome via Computer Use.

As tentativas iniciais conservam logs: assertions comparavam UUIDs do serializer antes da renderização com strings JSON; o helper de URL recebeu Workspace em vez de contexto; a fixture de autor histórico tentou cascata de User bloqueada pelos guards U0; e uma importação de uuid4 precisou ser restaurada. Foram corrigidos os testes, preservando guards de produto. O lint pediu evitar sort mutável, mas `toSorted` não pertence ao target ES2022 do projeto: mantido sort de array local com justificativa e supressão pontual da regra, sem mudar tsconfig/dependências.

Não houve deploy, ativação no stack em uso, alteração de credenciais ou código do COS_AGENT_V2. Provider real e quatro opt-ins não foram reexecutados. Não há alegação de homologação em ambiente publicado nem de encerramento dos outros 13 U1 ou dois U2.
