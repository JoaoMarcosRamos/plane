# RADAR Core — Correções U0

Entrega de 06/10/2026. Escopo: C04, C05, C06, C08 e C10 da [auditoria 2.1](CORE_AUDIT.md), autorizados após a entrega documental. Nenhum tipo novo, builder ou ampliação da skill foi implementado.

## Resultado por achado

| Achado                         | Correção                                                                                                                                                                                                                                       | Evidência principal                                                                                                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C04 — nomes globais            | Restrição de `decided_at` e human-only de `status=decided` limitada a Decision. Campos derivados e sua autoridade vêm das invariantes do tipo, não dos nomes likelihood/impact/score.                                                          | [handlers](../../apps/api/plane/radar/commands/handlers.py), [testes U0](../../apps/api/plane/radar/tests/test_core_u0.py)                                                                               |
| C05 — invariantes duplicadas   | Planejamento, avaliação, derivação, persistência e remoção compartilhados. Handler, primitive de propriedade e inicialização de defaults usam o mesmo engine. Produto aceita todos os fatores declarados.                                      | [primitives_semantic](../../apps/api/plane/radar/commands/primitives_semantic.py), [rules](../../apps/api/plane/radar/commands/rules.py)                                                                 |
| C06 — contrato de regras       | Invariantes persistidas em ObjectType.rules por workspace. Fingerprint inclui metadata e contrato da implementação. Aprovação/execução recusam intenção pendente com contrato alterado. Metadata do servidor é separada do envelope de replay. | [execution](../../apps/api/plane/radar/commands/execution.py), [migration 0011](../../apps/api/plane/radar/migrations/0011_objecttype_rules.py)                                                          |
| C08 — relação obrigatória      | Máximo `1..1` alinhado no seletor. Mínimo genérico validado nas mudanças de status e nos vínculos de runtime; writes em Objects vinculados revalidam o mínimo após efeitos compostos.                                                          | [validador](../../apps/api/plane/radar/commands/primitives_semantic.py), [binding](../../apps/api/plane/radar/commands/runtime_control.py), [seletor](../../apps/web/components/radar/semantic-utils.ts) |
| C10 — escrita fora de commands | RadarBaseModel exige contexto do mesmo workspace, preserva criador e valida FKs RADAR no tenant. Querysets bloqueiam bulk/update; somente o flush pode atualizar os ponteiros de provenance dos registros da própria mutação.                  | [core](../../apps/api/plane/radar/models/core.py), [mutation](../../apps/api/plane/radar/mutation.py)                                                                                                    |

## Invariantes efetivas e versionamento

`ObjectType.rules` é um JSON estruturado, com operadores fechados. Exemplo de Risk:

```json
{
  "invariants": [{ "kind": "product", "result": "score", "factors": ["likelihood", "impact"] }]
}
```

Operadores atuais:

- `ordered_dates`: propriedades `first/second` precisam ser definições ativas do tipo `date`; a segunda não pode preceder a primeira.
- `product`: resultado e 2–16 fatores precisam ser definições numéricas ativas. O resultado é derivado; input inicial manual é recusado, edição manual só aceita o valor calculado, remoção independente é recusada.

Metadata desconhecida, operadores desconhecidos, propriedades incompatíveis/inativas, fatores ausentes, referências repetidas e produtos encadeados/cíclicos são recusados. Há limite de 32 invariantes por tipo. Não existe execução de script vindo de metadata.

O seed normativo é usado para instalar as invariantes iniciais; a avaliação de Objects lê a configuração persistida do próprio tipo. Não procura regras de execução no snapshot global pelo nome da classe. As consultas de valores efetivos e o plano de alterações são compartilhados também com a checagem dos campos cobertos pelo grant, incluindo um resultado derivado que precise ser reparado/materializado.

O contrato da implementação contém a revisão `2.1.u0.1` e um digest determinístico dos módulos Python RADAR de produto. Tests, migrations e management commands ficam fora desse digest. Isso cobre handlers, transições, guards, adapters e models, inclusive uma alteração de código sem bump manual da revisão. A decisão é conservadora: uma alteração nesses módulos pode invalidar uma intenção pendente mesmo quando não modifica seu efeito específico.

O fingerprint do workspace incorpora esse contrato e `ObjectType.rules`, além das definições e relações já versionadas por hash. O contrato é conservado no envelope persistido e na provenance. Preview, review e consumo da aprovação estão vinculados a esse fingerprint. Alteração da regra efetiva ou implementação exige nova intenção/aprovação; intenções anteriores à introdução do contrato também não são aprovadas sob as regras novas.

O `command_version=1` continua sendo a versão do protocolo de entrada. A revisão de semântica é um contrato separado. O cliente não pode enviar `rules_contract`/`schema_hash` como autoridade: o serializer estrito recusa esses campos. O helper `command_envelope` projeta apenas os campos de entrada declarados ao retomar uma intenção nos adapters de sessão, Risk Review e runtime. Replays de execuções já confirmadas devolvem o resultado histórico, preservando a idempotência; não reinterpretam seus efeitos sob regras novas.

As transições ordinárias e guards de domínio continuam executáveis em código, agora cobertos pelo contrato. Tornar todo o lifecycle editável por builder é C01/U1, fora desta entrega. A persistência das invariantes não cria uma API pública de alteração de metadata.

## Momento da cardinalidade mínima

O Object recém-criado pode estar em **montagem**: suas propriedades e relações podem ser adicionadas em commands subsequentes. A criação isolada não passa a exigir todos os endpoints obrigatórios de uma vez, inclusive para tipos cujo default de status não se chama `draft`.

O mínimo `1..1` é exigido:

1. Quando um command altera efetivamente o status, antes de persistir a transição. Isso inclui caminhos especializados que usam o engine de propriedades.
2. Ao provisionar uma identidade de runtime, para qualquer ObjectType elegível ao binding. O único target precisa estar ativo e vinculado no mesmo contexto.
3. Ao concluir os efeitos de um command que criou/tocou um Object já vinculado. A validação ocorre depois dos efeitos compostos, tanto no preview quanto na execução real.

São considerados RelationType ativo, domínio/codomínio, allowed_pairs, endpoints ativos e self-link. A proteção específica de binding do Commitment foi substituída por essa validação orientada ao RelationType. O máximo de um target continua serializado por locks e a remoção independente de relação `1..1` continua bloqueada.

Objetos em montagem não são automaticamente considerados prontos para o runtime. Não foi introduzido um workflow universal de conclusão de draft nem uma migration de estado para todo Object. A UI filtra o máximo declarado sobre as relações conhecidas; o backend continua a validar a cardinalidade completa e definitiva.

## Fronteira de escrita

A proteção aplica-se aos models baseados em `RadarBaseModel`: Object/Type, PropertyDefinition/Value, RelationType/Relation, grants, vínculos, configuração e propostas, entre outros. `save` sem command ou em outro workspace é recusado; workspace/criador de registro existente são imutáveis; referências RADAR precisam pertencer ao mesmo tenant. PropertyValue também verifica se a definição pertence ao tipo do Object.

`update`, `bulk_create` e `bulk_update` não são mecanismos de escrita de domínio. A única exceção de queryset é o preenchimento de `created_provenance_id/last_provenance_id` durante o flush, com o ID da provenance corrente, no workspace e nos registros capturados por aquela mutação. Essa exceção é encerrada em `finally`; commands normais não ganham autoridade para editar esses ponteiros.

Ledger de execução, eventos, runs e cópias de resultado têm writers próprios da aplicação; não foram convertidos em subclasses de RadarBaseModel. A barreira ORM não pretende restringir SQL administrativo ou modelos históricos de migration. Builders futuros devem invocar commands autorizados, não fabricar contextos de mutação.

Testes antigos que construíam registros históricos, metadata inválida ou estado revogado passaram a usar [fixture_write](../../apps/api/plane/radar/tests/fixture_writes.py) explicitamente em cada chamada de setup. O helper existe somente nos testes e faz mock apenas daquela escrita ORM. Não há fixture autouse, flag de ambiente ou bypass no código de produto. Requests, commands e testes de bloqueio executam os guards reais.

## Migration e compatibilidade

[0011_objecttype_rules](../../apps/api/plane/radar/migrations/0011_objecttype_rules.py) adiciona o campo e instala as duas invariantes congeladas do Core 3.2.0 em Objective/Risk existentes, utilizando modelos históricos e a conexão da migration. Tipos customizados continuam com `{}`. Identidades dos tipos, estado ativo/inativo e autoria existente são preservados; não é fabricada provenance histórica de uma alteração de schema feita pela migration.

Para workspaces novos, o bootstrap auditado instala as mesmas regras a partir do snapshot. O `get_or_create` não sobrescreve regras de tipos existentes em cada leitura.

A migration foi verificada com upgrade de 0010 → 0011, downgrade → 0010 e novo upgrade, em banco descartável separado do Plane em uso. O downgrade remove a coluna e, portanto, descarta customizações de regras feitas depois de 0011; exportar essas configurações é necessário para conservá-las numa reversão real.

**A migration não foi aplicada ao stack Plane em uso nem a ambiente publicado.** O código entregue depende de aplicá-la antes de ativar a nova versão. Não houve alteração em COS_AGENT_V2, nas credenciais nem nas dependências do projeto.

## Validação

Logs e comandos reproduzíveis estão em [output/core-u0-20261005](../../output/core-u0-20261005/README.md). A pasta conserva a data inicial do trabalho; o relatório registra a conclusão em 06/10/2026.

**301 testes backend RADAR aprovados, 4 opt-in skipped; 93 testes frontend aprovados.** A regressão final inclui 33 casos U0 novos. Ruff, formatação Python, OxLint, Oxfmt, TypeScript e migration check passaram. Não se somam reexecuções às contagens finais. Os testes U0 cobrem nomes coincidentes, múltiplos fatores, grants sobre campos derivados, rollback, operadores inválidos, mudança de metadata/código antes e depois do review, relações obrigatórias, proteção ORM, FKs, provenance e replay.

## Pendências preservadas

Os achados U1/U2 da auditoria continuam como trabalho posterior: criação/lifecycle orientados a metadata, builders, upgrades gerais de schema, capacidades da UI, prazos operacionais, paginação e granularidade dos locks. Esta entrega não altera as decisões de produto ou a homologação de provider/piloto registradas nos relatórios da Fase 1.
