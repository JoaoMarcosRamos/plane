# RADAR Core — Auditoria 2.1

**Auditoria inicial:** 05/10/2026, America/Bahia. **Atualização:** 06/10/2026. **Entrega:** prompt 2.1 de [radar_prompts_por_fase.md](../../../DOCS_PROJETO_RADAR_COMPLETO/radar_prompts_por_fase.md), com acompanhamento das correções U0 posteriormente autorizadas.

> **Estado atual:** C04, C05, C06, C08 e C10 corrigidos no código e validados. Permanecem 16 achados U1 e 2 U2. A migration 0011 foi validada em banco isolado e ainda não foi aplicada ao stack Plane em uso nem a ambiente publicado. O [CORE_U0_REPORT.md](CORE_U0_REPORT.md) detalha a implementação e seus limites.

## Conclusão

O RADAR já possui persistência independente de WorkItem: `Object`, `ObjectType`, propriedades e relações têm models, tabelas e commands próprios. Não há FK para Project ou Issue do Plane nesses models. A genericidade, entretanto, não percorre toda a aplicação. O dispatcher, as transições, a autorização de efeitos, o formulário de criação e a integração de identidades de runtime ainda dependem de nomes de tipos e campos conhecidos em código.

O Core permite criar um tipo adicional e editar propriedades escalares, mas **isso não demonstra que um novo tipo tenha criação, ciclo de vida, ações, revisão humana e acesso pelo agente inteiramente definidos por metadata**. A principal prioridade da Fase 2 é fechar esse contrato preservando commands, validação, provenance e approvals existentes.

Dos **23 achados**, os **5 U0 foram corrigidos**: restrições de domínio passaram a ter escopo de tipo; escrita e derivação de propriedades usam uma implementação compartilhada; invariantes do workspace e contrato de implementação integram o fingerprint de aprovação; relações obrigatórias têm validação genérica em momentos definidos; e os models do Core bloqueiam escrita ORM fora do contexto de command. A regressão final teve **301 testes backend aprovados, 4 opt-in ignorados e 93 testes frontend aprovados**, incluindo 33 casos U0 novos.

Os **18 achados U1/U2 permanecem pendentes**. As correções não tornam lifecycle, criação, builders, identidade de runtime ou apresentação inteiramente configuráveis por metadata. A entrega também não demonstra homologação em produção: a ativação depende da migration descrita abaixo.

## Escopo e método

- Base observada: worktree `plane-radar-phase-0-spike`, HEAD `8fa56b19d7864da0c80a4ae92dc4371d5487699e`. O HEAD **não representa sozinho o estado auditado**: há mudanças staged, unstaged e arquivos untracked anteriores a esta auditoria.
- Backend: `apps/api/plane/radar/{models,commands,api,ontology}`, runtime/configuração, Risk Review, Today e colaboração presentes no filesystem. Frontend: componentes, services, stores e rotas RADAR.
- Foram lidos contratos arquiteturais e testes existentes para distinguir garantias atuais de lacunas. Colaboração, Risk Review e Today foram incluídos mesmo quando documentos históricos ainda os apresentavam como próximos passos.
- O snapshot efetivamente carregado contém **11 tipos, 22 tipos de relação e 2 invariantes**, versão `3.2.0`; não apenas os cinco tipos iniciais do spike.
- Foram feitos probes locais de leitura usando JSON/AST: inventário do snapshot, tabela de transições, FKs externas, métodos do queryset e execução isolada de `_is_human_only`. Não houve escrita no banco, acesso ao runtime, benchmark ou execução de pytest/browser nesta auditoria.
- COS_AGENT_V2 e a ontologia externa são fronteiras de integração, não objetos de auditoria integral. As conclusões sobre essas fronteiras se apoiam no código consumidor do Plane. Recursos `spike/` são protótipos, não implementação produtiva.
- As referências abaixo são relativas a este arquivo. Os intervalos de linhas preservados nos achados pendentes identificam a evidência histórica da auditoria inicial; as seções U0 e as notas de acompanhamento descrevem a implementação atual por arquivo e função.
- A atualização incorpora código, migration, testes e evidências da entrega U0. Os probes e limitações da auditoria estática acima descrevem o método inicial, não a validação posterior.

## Critérios de classificação

**Impacto** mede a consequência: **alto** afeta extensibilidade central, integridade, autoridade ou operação de fluxos; **médio** afeta partes da experiência, consistência ou manutenção; **baixo** é localizado e predominantemente editorial.

**Urgência:** **U0** = resolver o contrato antes de liberar novas escritas de metadata/tipos que acionem o problema; **U1** = endereçar no desenho e implementação dos builders/capabilities da Fase 2; **U2** = melhoria posterior, com limite explícito enquanto persistir. A auditoria inicial não refatorou o Core; as correções U0 foram autorizadas em solicitação posterior.

**Risco** mede a possibilidade de efeitos indevidos ou regressões se a situação persistir: **alto** envolve inconsistência de fatos/autoridade/auditoria; **médio** envolve fluxos bloqueados, divergência de contratos ou escala sem proteção; **baixo** envolve apresentação ou manutenção localizada. As consequências projetadas estão descritas separadamente da evidência confirmada.

## Matriz dos achados

Impacto, urgência e risco conservam a **classificação original** para rastreabilidade. A coluna Status indica o trabalho ainda aberto; um U0 corrigido não representa um problema ainda presente no código. A aplicação da migration é uma condição de ativação comum à entrega, não uma confirmação de implantação.

| ID  | Problema                                                                 | Categorias                       | Impacto | Urgência | Risco | Status              |
| --- | ------------------------------------------------------------------------ | -------------------------------- | ------- | -------- | ----- | ------------------- |
| C01 | Ciclo de vida fechado por tipo em Python                                 | Tipos; hardcoded; metadata       | Alto    | U1       | Alto  | Pendente            |
| C02 | CreateObject redireciona tipos conhecidos para contratos fechados        | Tipos; acoplamento; hardcoded    | Alto    | U1       | Médio | Pendente            |
| C03 | Formulário de criação não deriva campos de PropertyDefinition            | Duplicação; tipos; metadata      | Alto    | U1       | Médio | Pendente            |
| C04 | Nomes de campos/estados reservados globalmente sem escopo de tipo        | Hardcoded; acoplamento           | Alto    | U0       | Alto  | Corrigido no código |
| C05 | Duas implementações de escrita/invariantes semânticos                    | Duplicação; acoplamento          | Alto    | U0       | Alto  | Corrigido no código |
| C06 | Invariantes e regras executáveis fora do schema efetivo de workspace     | Metadata; acoplamento            | Alto    | U0       | Alto  | Corrigido no código |
| C07 | Seed sem evolução/versionamento por workspace                            | Acoplamento; metadata            | Alto    | U1       | Alto  | Pendente            |
| C08 | Cardinalidade 1..1 incompleta e divergente na UI                         | Duplicação; metadata             | Alto    | U0       | Alto  | Corrigido no código |
| C09 | Membership e papéis repetidos; efeitos autorizados por listas manuais    | Duplicação; hardcoded; metadata  | Alto    | U1       | Alto  | Pendente            |
| C10 | Model/queryset do Core não exigem contexto de command para toda escrita  | Acoplamento; integridade         | Alto    | U0       | Alto  | Corrigido no código |
| C11 | Visibilidade de tipos/propriedades/relações inativos é inconsistente     | Duplicação; acoplamento          | Alto    | U1       | Alto  | Pendente            |
| C12 | Object.version não cobre mudanças de metadata                            | Acoplamento; metadata            | Alto    | U1       | Alto  | Pendente            |
| C13 | Object Page e seletores carregam todo o workspace                        | Acoplamento; escala              | Médio   | U1       | Médio | Pendente            |
| C14 | Writes e inicialização de schema serializam o workspace inteiro          | Acoplamento; escala              | Médio   | U2       | Médio | Pendente            |
| C15 | Defaults internos e retries não têm o mesmo contrato de idempotência     | Duplicação; acoplamento          | Médio   | U1       | Médio | Pendente            |
| C16 | Domain handlers dependem de serializers HTTP e funções privadas          | Acoplamento                      | Médio   | U1       | Médio | Pendente            |
| C17 | Catálogo e contratos estruturais repetidos manualmente                   | Duplicação; hardcoded; metadata  | Médio   | U1       | Médio | Pendente            |
| C18 | OperationalRecord cria metadata operacional paralela                     | Hardcoded; acoplamento; WorkItem | Alto    | U1       | Alto  | Pendente            |
| C19 | Tipo criado no workspace não ganha identidade/contexto de runtime        | Tipos; acoplamento; metadata     | Alto    | U1       | Médio | Pendente            |
| C20 | Editor genérico não conhece campos derivados, guards e ações disponíveis | Metadata; WorkItem               | Alto    | U1       | Médio | Pendente            |
| C21 | Página universal de título/conteúdo e descrição concorrente              | Hardcoded; WorkItem              | Médio   | U1       | Médio | Pendente            |
| C22 | Autoria resumida da página ainda pressupõe User humano                   | Acoplamento; WorkItem            | Médio   | U1       | Médio | Pendente            |
| C23 | Navegação por tipos é estática e contém placeholders                     | Tipos; hardcoded; metadata       | Médio   | U2       | Baixo | Pendente            |

## Evidências e consequências

### C01 — Ciclo de vida fechado por tipo em Python

**Impacto alto · Urgência U1 · Risco alto.**

[rules.py](../../apps/api/plane/radar/commands/rules.py) mantém `ORDINARY_TRANSITIONS`, consumido por [handlers.py](../../apps/api/plane/radar/commands/handlers.py), que aplica guards dedicados para Action, Decision, Document e Indicator. A entrega U0 moveu a tabela e a incluiu no contrato de implementação; não tornou o grafo configurável. [operations.py](../../apps/api/plane/radar/commands/operations.py), linhas 116–119 e 182–193, acrescenta estados de delegação e mapeamentos de disposition. Defaults/vocabulários/terminais são metadata, mas o grafo de transições e a associação a commands não são.

Um tipo adicional com enum `status` pode ser criado e ter outros campos editados, porém uma mudança de estado é recusada por falta de entrada na tabela. Mesmo entre os tipos semeados, `case`, `commitment`, `decision`, `indicator` e `management_item` não têm transições ordinárias; alguns têm caminhos dedicados, o que não equivale a um ciclo de vida genérico. Não se deve preencher todas as transições automaticamente: etapas terminais e decisões humanas possuem guards legítimos.

**Direção para etapa futura:** declarar lifecycle, transições e capabilities por tipo, apontando para handlers tipados de validação/efeitos. Independência de aprovação, evidência obrigatória e autoridade devem continuar garantias executáveis.

### C02 — Criação genérica redirecionada a contratos fechados

**Impacto alto · Urgência U1 · Risco médio.**

[handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 170–185 e 442–452, transforma `CreateObject` em `CreateAction`, `RegisterRisk` ou `CreateDecision` pelo `ObjectType.key`. Os serializers em [inputs.py](../../apps/api/plane/radar/commands/inputs.py), linhas 117–155, e os handlers nas linhas 563–625 têm listas próprias de campos e relações.

Adicionar uma propriedade válida ao tipo `action` no workspace não basta para enviá-la na criação genérica: `_special_input` passa o payload ao serializer especializado, que rejeita campos desconhecidos. Tipos novos seguem outro caminho. A política de estado inicial também consulta o snapshot global, em vez do default persistido do workspace.

**Direção futura:** explicitar a capability de criação e os requisitos/efeitos de cada tipo em metadata. Preservar os comandos semânticos; retirar do dispatcher genérico a necessidade de conhecer todo tipo novo.

### C03 — Criação na UI não usa propriedades obrigatórias da metadata

**Impacto alto · Urgência U1 · Risco médio.**

[create-object-input.ts](../../apps/web/components/radar/create-object-input.ts), linhas 3–15, define `context/decision/rationale` para Decision e `description` para Action/Risk. [create-object-dialog.tsx](../../apps/web/components/radar/create-object-dialog.tsx), linhas 28–43 e 98–109, usa essa lista e campos de texto, sem consultar definições. O tipo inicial também é fixado como `objective`.

Ao adicionar uma propriedade obrigatória sem default a um tipo, o backend corretamente bloqueia a criação incompleta; a UI não oferece o campo necessário. O teste existente [test_semantic.py](../../apps/api/plane/radar/tests/test_semantic.py), linhas 639–647, documenta essa validação de backend. O probe do snapshot atual não encontrou atributos obrigatórios sem default além dos cobertos pela UI; a falha de extensibilidade surge ao ampliar a configuração, não foi atribuída a todos os seeds atuais.

**Direção futura:** formulário de criação orientado por definições/capability de criação, incluindo tipos de valor e campos necessários aos efeitos compostos.

### C04 — Colisões de nomes globais

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** nomes como `score`, `likelihood/impact`, `decided_at` e `status=decided` acionavam restrições de Risk/Decision em qualquer tipo, mesmo quando tinham outro significado.

**Implementação:** [handlers.py](../../apps/api/plane/radar/commands/handlers.py) limita a restrição de `decided_at` e o human-only de `status=decided` ao tipo Decision. Na criação, campos derivados são descobertos pelas invariantes do ObjectType. A checagem de grants usa `property_effect_fields`, incluindo resultados que precisam ser materializados ou reparados; não deduz autoridade por nomes globais.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre tipos customizados com nomes coincidentes e autoridade sobre campos derivados com outras chaves. Um `score` sem invariante de derivação pode ser preenchido normalmente.

**Limite:** guards especializados continuam em código e cobertos pelo contrato de implementação; lifecycle/capabilities configuráveis permanecem C01/C20, U1.

### C05 — Duas implementações de invariantes/escritas

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** handler e primitive mantinham leituras, derivação e persistência próprias, com comportamentos diferentes para fatores ausentes, produtos e patches não relacionados.

**Implementação:** [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py) centraliza `effective_values`, `plan_properties`, `property_effect_fields` e `patch_properties`. O handler, as primitives de edição/remoção e a inicialização de defaults usam esse engine. A antiga `_invariant_changes` foi removida. Os operadores tipados de [rules.py](../../apps/api/plane/radar/commands/rules.py) calculam produtos com todos os fatores declarados via `math.prod`.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) verifica paridade entre writers, produtos com múltiplos fatores, grants sobre efeitos derivados e rollback de valores, versões, eventos e provenance em batches inválidos.

**Limite:** a semântica compartilhada não resolve o contrato de idempotência dos commands internos (C15) nem todos os efeitos compostos enumerados manualmente (C09).

### C06 — Regras executáveis fora do schema efetivo

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** invariantes eram lidas do snapshot global, enquanto propriedades efetivas pertenciam ao workspace. O fingerprint de aprovação não cobria a revisão dos handlers/guards Python.

**Implementação:** `ObjectType.rules` persiste invariantes por workspace, expostas em modo somente leitura pelo serializer. [rules.py](../../apps/api/plane/radar/commands/rules.py) valida os operadores fechados `ordered_dates` e `product`, suas referências, tipos ativos e limites, recusando metadata desconhecida e produtos encadeados/cíclicos. Não executa scripts de metadata.

[execution.py](../../apps/api/plane/radar/commands/execution.py) inclui essas regras e `implementation_contract()` no `schema_fingerprint`. O contrato combina a revisão `2.1.u0.1` com digest determinístico dos módulos Python RADAR de produto, excluindo tests, migrations e management commands. É registrado no envelope persistido/provenance e vincula preview, review e execução: mudança de metadata ou implementação impede consumir uma aprovação pendente sob o contrato anterior. Replays de execuções confirmadas devolvem o resultado histórico.

`command_envelope` projeta somente os campos declarados de entrada ao retomar uma intenção em sessão, Risk Review e runtime. Campos do servidor como `rules_contract/schema_hash` não são reenviados como input do cliente. `command_version=1` permanece a versão do protocolo de entrada, separada da revisão de semântica.

**Migration:** [0011_objecttype_rules.py](../../apps/api/plane/radar/migrations/0011_objecttype_rules.py) instala as duas invariantes normativas em Objective/Risk existentes e preserva tipos customizados com `{}`, identidades, estado ativo e autoria. Workspaces novos recebem as regras pelo bootstrap auditado.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre regras inválidas, alterações de metadata/código antes e depois do review e ownership do contrato pelo servidor. Upgrade, downgrade e novo upgrade foram verificados em banco descartável.

**Limites:** o digest é conservador e pode invalidar uma intenção por mudança de código sem efeito específico nela. Não foi criada uma API pública de edição de regras nem lifecycle configurável (C01). A migration ainda precisa ser aplicada ao ambiente em uso; downgrade remove a coluna e perde customizações posteriores, exigindo exportação prévia para preservá-las.

### C07 — Seed sem contrato de atualização por workspace

**Impacto alto · Urgência U1 · Risco alto.**

[schema.py](../../apps/api/plane/radar/ontology/schema.py), linhas 6–8, carrega um arquivo `core-3.2.0.json` fixo/cacheado; [snapshot.py](../../apps/api/plane/radar/ontology/snapshot.py), linhas 9–21, seleciona tipos em uma lista. [primitives_objects.py](../../apps/api/plane/radar/commands/primitives_objects.py), linhas 63–78, e [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py), linhas 60–107, usam `get_or_create` com configuração em `defaults`.

A idempotência preserva dados e tipos inativados, mas não atualiza definições existentes quando o snapshot muda. Não há nesses models versão de schema instalada no workspace. Os GETs de catálogo/propriedades inicializam schema via command auditado; leitura pode criar configuração. O comportamento é explícito e herdado do spike, porém não resolve upgrade, rollback ou conflito entre metadata local e seed normativo.

**Acompanhamento U0:** a migration 0011 instala as duas invariantes normativas em tipos existentes. Esse backfill específico não oferece upgrade/rollback geral de metadata por workspace; C07 permanece pendente.

**Direção futura:** distinguir bootstrap, versão normativa instalada e customizações locais; migração de metadata deve ser explícita, auditada e preservar decisões do workspace.

### C08 — Cardinalidade obrigatória parcialmente implementada

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** o máximo de `1..1` era protegido no servidor, mas ignorado pelo seletor. O mínimo era exigido especificamente no binding de Commitment, sem um contrato genérico de momento de validação.

**Implementação:** `validate_required_relations` em [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py) consulta RelationType ativo, domínio/codomínio, allowed_pairs, self-link e endpoints ativos. O mínimo é exigido em mudanças efetivas de status, no binding de runtime e ao concluir efeitos compostos que criaram/tocaram Objects já vinculados, tanto no preview quanto na execução, incluindo commands internos.

A criação isolada permite **montagem** de propriedades e relações em commands subsequentes, independentemente do nome do status default. No [binding](../../apps/api/plane/radar/commands/runtime_control.py), o único target obrigatório precisa estar vinculado no mesmo contexto. A validação específica de Commitment foi substituída pelo contrato genérico. Máximo com locks e bloqueio de remoção independente continuam garantidos pelo servidor.

[semantic-utils.ts](../../apps/web/components/radar/semantic-utils.ts) trata `0..1` e `1..1` como máximo de um ao filtrar candidatos sobre as relações conhecidas.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre montagem, transição, binding e revalidação de escrita interna em Object vinculado; [semantic-utils.test.ts](../../apps/web/components/radar/semantic-utils.test.ts) cobre o seletor.

**Limites:** não foi criado um workflow universal de conclusão de draft. A UI filtra dados conhecidos; a validação definitiva permanece no backend. Identidade de runtime de tipos adicionais continua C19/U1.

### C09 — Autoridade duplicada e efeitos compostos manuais

**Impacto alto · Urgência U1 · Risco alto.**

Papéis numéricos `5/15/20` aparecem em [primitives_objects.py](../../apps/api/plane/radar/commands/primitives_objects.py), linhas 25–35, [execution.py](../../apps/api/plane/radar/commands/execution.py), linhas 139–170, e [collaboration_views.py](../../apps/api/plane/radar/api/collaboration_views.py), linhas 55–58. A UI usa enums Plane e um `canWrite` de workspace. [handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 188–284, lista tipos criados, commands compostos, campos derivados e relações que exigem review.

Membership como fronteira do shell é apropriado. A dívida é manter várias traduções dos mesmos papéis e enumerar efeitos de cada command à mão. Um novo efeito precisa ser lembrado em references, locks/versions, grants, approval e handler. Omissões futuras podem bloquear fluxos ou autorizar apenas parte dos efeitos. Não foi demonstrada uma falha de acesso cross-workspace.

**Acompanhamento U0:** a autoridade sobre propriedades derivadas agora acompanha o plano compartilhado de efeitos (C04/C05). As traduções de membership e os demais efeitos compostos manuais permanecem pendentes.

**Direção futura:** regras comuns de membership e descritores tipados de efeitos/capabilities; metadata configura requisitos dentro de limites executáveis, sem permitir que o builder conceda autoridade arbitrária.

### C10 — Proteção desigual contra escrita ORM fora de commands

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** o Core bloqueava delete direto, mas `save`, `update`, `bulk_create` e `bulk_update` podiam escrever fora do contexto de command, sem as garantias de autoridade/provenance. FKs isoladas também não asseguravam tenant/tipo compatíveis.

**Implementação:** [RadarBaseModel e RadarQuerySet](../../apps/api/plane/radar/models/core.py) exigem contexto de mutação do mesmo workspace, tornam workspace/criador existentes imutáveis, bloqueiam alterações ordinárias dos ponteiros de provenance e validam FKs RADAR no tenant. [PropertyValue](../../apps/api/plane/radar/models/semantic.py) verifica a definição contra o ObjectType do Object.

Querysets recusam `update`, `bulk_create` e `bulk_update`. A única exceção é o flush de [MutationContext](../../apps/api/plane/radar/mutation.py), para ponteiros de provenance com o ID corrente e somente registros capturados pela própria mutação no mesmo workspace. A exceção é encerrada em `finally`.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) verifica bloqueio sem command, isolamento de workspace/FKs, imutabilidade, tentativa de falsificar provenance e flush/replay legítimos. Setups históricos de testes antigos usam [fixture_writes.py](../../apps/api/plane/radar/tests/fixture_writes.py) explicitamente por chamada, sem bypass de produto ou fixture autouse; os comandos executam os guards reais.

**Limites:** a proteção cobre descendentes de RadarBaseModel. SQL administrativo, models históricos de migration e ledgers/eventos/runs com writers próprios da aplicação estão fora dessa barreira ORM. O contexto é uma fronteira interna de escrita; builders devem usar commands autorizados.

### C11 — Queries divergem sobre o que está ativo

**Impacto alto · Urgência U1 · Risco alto.**

[api/views.py](../../apps/api/plane/radar/api/views.py), linhas 69–71 e 89–93, filtra Objects não excluídos, sem filtrar tipo inativo/excluído. A leitura semântica `_object` e `active_relations` em [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py), linhas 110–123 e 352–368, aplica filtros adicionais. Assim um Object pode aparecer no catálogo/detalhe e falhar ao abrir propriedades.

Na auditoria inicial, [handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 63–76, lia valores sem excluir explicitamente `definition.deleted_at`; essa leitura foi corrigida nos U0. [agent_runtime.py](../../apps/api/plane/radar/agent_runtime.py), linhas 105–109 e 123–175, continua sem os mesmos filtros de tipo excluído, RelationType ativo/excluído e definição ativa/excluída ao montar contexto. O cenário depende de inativação/soft delete de metadata, ainda sem builder público, mas o contrato de leitura continua divergente.

**Acompanhamento U0:** `_values` e o engine compartilhado passaram a usar definições ativas em `effective_values`. Isso corrige essa leitura sem estabelecer um contrato uniforme para detalhe, relações e contexto de runtime; C11 permanece pendente.

**Direção futura:** contrato comum de leitura de recursos ativos e valores efetivos, preservando consultas históricas explicitamente distintas. Verificar que contexto de agente não reutilize metadata retirada de operação.

### C12 — Snapshot de Object não versiona metadata

**Impacto alto · Urgência U1 · Risco alto.**

[root.store.ts](../../apps/web/store/radar/root.store.ts), linhas 99–105 e 148–161, compara snapshots por `Object.version`. Defaults, choices, obrigatoriedade, labels e cardinalidade pertencem às definições e não possuem revisão agregada devolvida nesses snapshots. Os commands atuais travam o workspace para schema/control, mas isso não fornece uma versão de schema à cache da UI.

Quando um builder alterar metadata sem alterar Object, a mesma versão de Object poderá representar valores efetivos/defaults ou regras diferentes. Duas requisições podem concordar sobre Object.version e discordar sobre schema. O fingerprint de approvals é uma proteção existente, porém não integra esse contrato de leitura/cache.

**Acompanhamento U0:** o fingerprint de aprovação agora cobre invariantes e implementação (C06), mas não é uma revisão de schema integrada aos snapshots/cache da UI. C12 permanece pendente.

**Direção futura:** revisão efetiva de schema/capabilities nos snapshots e invalidação de caches/formulários quando ela mudar, sem incrementar artificialmente todos os Objects a cada mudança visual.

### C13 — Detalhe exige catálogo inteiro

**Impacto médio · Urgência U1 · Risco médio.**

[ObjectsView](../../apps/api/plane/radar/api/views.py), linhas 68–71, serializa todos os Objects sem paginação/filtro server-side. [root.store.ts](../../apps/web/store/radar/root.store.ts), linhas 74–78 e 158–161, carrega a lista inteira também na Object Page. O seletor em [semantic-utils.ts](../../apps/web/components/radar/semantic-utils.ts), linhas 13–40, filtra candidatos localmente.

A navegação de uma entidade e seus backlinks depende do volume total do workspace. O catálogo repete `object_type_detail` e inclui content. A consequência de escala é inferida da consulta; não há latência ou limite de volume medido nesta entrega.

**Direção futura:** paginação, busca de candidatos por relation/type/capability e resolução dos endpoints necessários ao detalhe. Manter tenant/autoridade na consulta do servidor.

### C14 — Lock global de workspace

**Impacto médio · Urgência U2 · Risco médio.**

[execution.py](../../apps/api/plane/radar/commands/execution.py), linhas 335–339 e 262–278, trava Workspace em toda execução e command interno. A inicialização lazy também trava Workspace. GETs de schema invocam commands internos mesmo quando não há novos registros. Há adicionalmente locks nos Objects para versões e relações.

O lock protege mudanças de schema/grants e é uma escolha conservadora válida no MVP. Seu custo é serializar mutações independentes do mesmo tenant, inclusive com validação/preview no percurso. Não foi medido throughput nem demonstrado deadlock.

**Direção futura:** medir concorrência e tempo dos locks antes de alterar a estratégia; preservar a atomicidade de schema, autoridade e replay ao propor granularidade menor.

### C15 — Idempotência diferente entre commands e defaults internos

**Impacto médio · Urgência U1 · Risco médio.**

[commands/semantic.py](../../apps/api/plane/radar/commands/semantic.py), linhas 23–31, recebe `idempotency_key` em `initialize_object_properties`, mas não a usa; executa `run_internal` e verifica a versão fornecida. [execution.py](../../apps/api/plane/radar/commands/execution.py), linhas 262–281, não mantém `CommandExecution` para esse caminho. Os commands públicos regulares mantêm ledger de intenção/replay.

Um retry de inicialização que já alterou defaults pode falhar por versão antiga, em vez de devolver o resultado confirmado pela mesma chave. Separadamente, [radar.service.ts](../../apps/web/services/radar/radar.service.ts), linhas 41–47, gera nova chave quando a store não fornece uma; a store genérica não conserva uma intenção para repetição após resposta incerta. Isso não demonstra duplicações existentes, mas o risco de duplicar uma criação em retry manual permanece.

**Direção futura:** declarar quais operações internas são idempotentes por estado e quais exigem replay da intenção; conservar a chave enquanto a intenção do usuário não mudar. A compatibilidade Python que preenche versões correntes deve continuar explicitamente limitada a callers confiáveis ([compatibility.py](../../apps/api/plane/radar/commands/compatibility.py), linhas 25–34).

### C16 — Camada de domínio conhece a API

**Impacto médio · Urgência U1 · Risco médio.**

[handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 435–439, importa `ObjectSerializer` de `api.serializers` para produzir o resultado. Esse módulo importa `StrictSerializer` de commands. Handlers/operations usam funções privadas de primitives; runtime e Risk Review importam `_values`, `references`, `check_grant` e `_human_member` de implementação interna.

Os imports locais contornam dependências circulares, mas mudanças de representação HTTP podem atingir commands e adaptadores. O domínio e a aplicação também usam exceções/serializers DRF, de modo que os contratos chamados de independentes de transporte continuam dependentes do framework.

**Direção futura:** interfaces públicas para consulta, validação e resultado de command; adapters serializam essas estruturas. Isso não exige eliminar Django/DRF em uma única refatoração.

### C17 — Contratos/catálogos repetidos manualmente

**Impacto médio · Urgência U1 · Risco médio.**

Tipos de propriedade aparecem em [models/semantic.py](../../apps/api/plane/radar/models/semantic.py), linhas 5–17, [services/types.ts](../../apps/web/services/radar/types.ts), linhas 45–65, no validador de primitives e no parser/editor da UI. [api/serializers.py](../../apps/api/plane/radar/api/serializers.py), linhas 48–70, repete o bloqueio de campos desconhecidos já presente no `StrictSerializer`. `DEFINITIONS` em [runtime_views.py](../../apps/api/plane/radar/api/runtime_views.py), linhas 40–74, repete parâmetros/target_types dos serializers operacionais e handlers.

Uma capability nova precisa ser mantida no input, dispatch, catálogo anunciado, references, grants e client types. A repetição da validação no cliente é útil para UX; a dívida é não haver um contrato verificável comum. Os kinds de valor atuais são operadores estruturais legítimos. A ausência de `rich_text`/`object_reference` no catálogo atual é escopo futuro do 2.4, não bug de um campo já suportado.

**Acompanhamento U0:** os operadores de invariantes têm validação compartilhada e DTO `RadarInvariant` tipado no cliente. Os demais catálogos, capabilities e serializers continuam repetidos; C17 permanece pendente.

**Direção futura:** registro de operadores/capabilities e schema de contratos com verificação ou geração de DTOs; constraints do banco continuam explícitas. Validar `PropertyDefinition.config` e descritores de relações antes de disponibilizar escrita por builder.

### C18 — Estado operacional paralelo às propriedades/relações

**Impacto alto · Urgência U1 · Risco alto.**

[models/commands.py](../../apps/api/plane/radar/models/commands.py), linhas 180–186, mantém `OperationalRecord.data`. [operations.py](../../apps/api/plane/radar/commands/operations.py), linhas 81–88 e 161–176, grava `assignment.executor_id/executor_ids/due_at/next_review_at/state/acceptances`. A atribuição também aparece em relações `assigned_to`. Reviews e measurements acumulam listas no JSON, nas linhas 194–199 e 226–242.

Action possui `due_date` em PropertyValue; delegação grava outro prazo, `due_at`, no OperationalRecord, e Today só consulta `due_date` ([today.py](../../apps/api/plane/radar/today.py), linhas 62–64). Uma delegação atrasada sem `due_date` não entra nesse grupo do Today. Esse é um cenário derivado das leituras/escritas, não um teste de runtime executado aqui. O JSON não é mostrado pelo Property Builder/Editor e as listas crescem sem limite local.

**Direção futura:** decidir a fonte de cada prazo/atribuição e quais registros são fatos/histórico operacional. Records especializados podem ser legítimos; precisam de schema, invariantes e projeção explícitos, evitando um segundo formulário de tarefa escondido em JSON.

### C19 — Runtime depende de catálogo global de tipos

**Impacto alto · Urgência U1 · Risco médio.**

[runtime_control.py](../../apps/api/plane/radar/commands/runtime_control.py) recusa tipos sem spec/prefix no snapshot. [operations.py](../../apps/api/plane/radar/commands/operations.py) aplica o mesmo contrato; o ramo de cardinalidade específico de Commitment presente na auditoria inicial foi removido nos U0. [agent_runtime.py](../../apps/api/plane/radar/agent_runtime.py), linhas 105–119, exige identidade no contexto para selecionar Objects.

Um ObjectType adicional no PostgreSQL pode funcionar na API genérica, mas não recebe automaticamente binding para o runtime. A existência de prefixo, formato de ID externo e eligibility para contexto não é metadata do ObjectType persistido. Não é dependência direta de Deep Agents: é um limite do port/contexto atual.

**Acompanhamento U0:** a cardinalidade obrigatória no binding agora é genérica (C08). A exigência de spec/prefix global para identidade de runtime permanece; a remoção do ramo especial de Commitment não resolve C19.

**Direção futura:** descritor de identidade/contexto/capabilities por tipo, com defaults seguros e provisioning explícito. Não ampliar silenciosamente o escopo autorizado do agente ao cadastrar um tipo.

### C20 — Editor de campos não conhece capabilities/guards

**Impacto alto · Urgência U1 · Risco médio.**

[property-editor.tsx](../../apps/web/components/radar/property-editor.tsx), linhas 34–41 e 73–141, determina edição por `canWrite` e value_type; enums oferecem todos os choices. [semantic-panel.tsx](../../apps/web/components/radar/semantic-panel.tsx), linhas 94–105 e 139–147, oferece remoção de toda relação a quem pode escrever. Não recebe `computed`, `read_only`, transições disponíveis ou requisitos de command/review.

Score derivado aparece como input editável; `completed_at`/`decided_at` e transições protegidas aparecem em formulários genéricos, mas são recusados pelo backend. Relações obrigatórias ou de aprovação também oferecem remoção que será recusada ou ficará pendente. Os guards de backend estão presentes; o problema é o modelo de edição de WorkItem aplicado a uma entidade que possui ações semânticas governadas.

**Direção futura:** capacidades calculadas pelo servidor para campos, transições, comandos e relações; mostrar ações como CompleteAction/ApproveDecision quando disponíveis e manter o servidor como autoridade final.

### C21 — Rich Object reduzido a título/conteúdo universal

**Impacto médio · Urgência U1 · Risco médio.**

[models/core.py](../../apps/api/plane/radar/models/core.py), linhas 84–89, exige `title` de até 255 caracteres e `content` HTML em todo Object. [object-page.tsx](../../apps/web/components/radar/object-page.tsx), linhas 15–81, renderiza sempre Title, Content e Save. Action/Risk possuem também propriedade `description`; Decision possui textos semânticos próprios, mantidos pelo handler especializado.

Título/UUID/version são envelopes comuns defensáveis e não indicam herança de Issue. A dívida é o layout fixo e a falta de papel explícito para content versus description/context/summary. O usuário pode manter narrativas divergentes em dois campos sem indicação de qual expressa a descrição principal. Tipos futuros como Person/Meeting/Evidence continuam recebendo a mesma página, sem metadata de apresentação/capabilities.

**Direção futura:** declarar campos principais, seções e apresentação por tipo, reutilizando a Object Page. Manter campos técnicos de identidade/versionamento no Core; não migrar automaticamente todo campo comum para EAV.

### C22 — Autoria humana simplificada na página

**Impacto médio · Urgência U1 · Risco médio.**

[models/core.py](../../apps/api/plane/radar/models/core.py), linhas 22–34, mantém FKs opcionais de User e ponteiros de provenance. [handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 43–44, devolve `None` como User para actor não humano. [ObjectSerializer](../../apps/api/plane/radar/api/serializers.py), linhas 27–45, não devolve esses ponteiros. [object-page.tsx](../../apps/web/components/radar/object-page.tsx), linhas 65–71, interpreta null como `Deleted user`.

Uma criação/edição por agente pode mostrar `Deleted user` na identificação principal apesar de provenance válido e actor conhecido. O painel de colaboração/activity já apresenta actor_type/actor_id ([collaboration_views.py](../../apps/api/plane/radar/api/collaboration_views.py), linhas 68–80); portanto não há ausência geral de auditoria, e sim duas representações incoerentes. PersonIdentity corretamente distingue Person de db.User, mas essa distinção ainda não chega ao resumo da página.

**Direção futura:** resumo de autoria por provenance/actor, distinguindo humano, agente, sistema, integração e autor histórico desconhecido.

### C23 — Navegação estática por tipo

**Impacto médio · Urgência U2 · Risco baixo.**

[sections.ts](../../apps/web/components/radar/sections.ts), linhas 8–15, enumera seções; Decisions/Risks são nomes fixos. A [rota de seção](../../apps/web/app/%28all%29/%5BworkspaceSlug%5D/%28radar%29/radar/%5Bsection%5D/page.tsx), linhas 28–42, mantém essas duas páginas como placeholders. `RadarHome` ainda contém status `Agent: not_implemented` ([home.tsx](../../apps/web/components/radar/home.tsx), linhas 29–45), embora runtime/configuração/Risk Review estejam presentes.

A lista Objects agrupa os tipos recebidos da API, o que é genérico. A navegação principal e as views por tipo não acompanham esse catálogo. Criar um tipo não cria uma view navegável configurada, e o shell expõe mensagens históricas conflitantes com o estado local.

**Direção futura:** views/navegação de tipos orientadas por metadata, separadas das entradas funcionais Today/configuração/skills. Remover placeholders somente em etapa autorizada de implementação.

## Onde Object ainda se comporta como WorkItem

Não foi encontrada dependência estrutural `Workspace → Plane Project → Issue` no Core. Os seguintes comportamentos são **semelhanças de contrato e UX**, não herança de WorkItem:

| Comportamento                                           | Evidência     | Avaliação                                                                                 |
| ------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------- |
| Formulário universal de título/descrição com Save       | C21           | Envelope comum é aceitável; apresentação fixa não expressa Rich Objects.                  |
| Status tratado como dropdown de propriedade editável    | C01, C20      | Workflow governado não cabe em simples edição de campo.                                   |
| Assignee/prazo/status de execução em estrutura dedicada | C18           | Legítimo para Action; não deve se tornar estado oculto de todo Object.                    |
| Criador/editor resumidos como db.User                   | C22           | Preserva compatibilidade com shell, mas descreve incorretamente actor não humano.         |
| Tipos conhecidos controlam formulário/rotas             | C02, C03, C23 | Um tipo configurado não recebe automaticamente experiência completa.                      |
| Relação de Decision com Project em input especializado  | C02           | `project_id` é opcional e aponta a Object RADAR; não é FK nem requisito de Plane Project. |

List layout, design system, workspace membership e rich text do Plane são reutilizações legítimas. O store [RadarRootStore](../../apps/web/store/radar/root.store.ts) não recebe Issue/Project stores. Comments/attachments são models RADAR ligados a Object, não adapters de Issue. Não há justificativa nesta auditoria para substituir essas fronteiras já isoladas.

## Metadata a explicitar nas próximas etapas

| Regra/informação                                      | Local atual                                                   | Destino conceitual                                                  | Garantia que continua em código              |
| ----------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------- |
| Campos de criação, obrigatoriedade e defaults         | C02, C03                                                      | Descritor de criação + PropertyDefinition                           | Validação tipada e atomicidade               |
| Estados, transições e ação que realiza cada transição | C01, C20                                                      | Lifecycle/capability do tipo                                        | Handler com guard, evidência e autoridade    |
| Campos derivados e dependências                       | C04–C06: entregues em ObjectType.rules e engine compartilhado | Invariantes efetivos versionados; edição por builder ainda futura   | Operadores tipados; sem scripts arbitrários  |
| Efeitos compostos e necessidade de review             | C09, C17                                                      | Descritor de command/capability/policy                              | Grants, delegação e separação de aprovação   |
| Mínimo/máximo de relações e momento de validação      | C08: entregues no validador genérico e seletor                | RelationType; mínimo em transição/binding/efeitos em vinculados     | Locks, unicidade e validação de endpoints    |
| Critério de atenção do Today                          | [today.py](../../apps/api/plane/radar/today.py), linhas 26–64 | Regra de view/atenção: tipos, estados, campos, limiar `score >= 15` | Consulta somente leitura e escopo autorizado |
| Identidade externa/contexto elegível                  | C19                                                           | Descritor de integração por tipo                                    | Provisioning auditado e restrição do escopo  |
| Campo principal, seções, ordem, visibilidade de UI    | C20, C21, C23                                                 | Metadata de apresentação/view                                       | Capacidades efetivas calculadas no servidor  |

`Risk Review` conhece deliberadamente Risk → Objective/Project, `threatens` e sugestões de Action ([risk_review.py](../../apps/api/plane/radar/risk_review.py), linhas 20–81). Isso é **especialização legítima da skill 1.5**, não motivo isolado para tornar o Core dependente desses tipos nem para ampliar a skill no 2.1. Limites de contexto, tamanho de anexo, UUIDs e versão de protocolos também são contratos técnicos legítimos; não se presume que todo literal deva virar metadata editável.

`DecisionApproval`, `ActionCompletion` e `EvidenceRecord` são registros operacionais/auditáveis específicos ([models/commands.py](../../apps/api/plane/radar/models/commands.py), linhas 111–166), não models separados de ObjectType. Sua existência não viola automaticamente o modelo genérico. A questão para a Fase 2 é registrar capabilities e fronteiras que os utilizam, sem apagar histórico nem nivelar todos os tipos ao workflow de Action.

## Ativação e ordem recomendada das pendências

1. **Ativação da entrega U0:** aplicar a migration 0011 antes de usar o código atualizado. Ela foi validada em ambiente isolado; não foi aplicada ao stack Plane em uso nem publicada. As cinco correções estão concluídas no código, sem builders ou tipos novos.
2. **No desenho do Type/Property/Relation Builder:** versionamento/upgrade geral de schema e snapshots (C07, C12), lifecycle/criação/capabilities (C01–C03, C20), leitura ativa e autoridade compartilhada (C09, C11), contratos e vínculo ao runtime (C16–C17, C19).
3. **Na integração da experiência genérica:** fonte dos prazos/atribuições e registros operacionais (C18), apresentação e autoria (C21–C22), consultas de candidatos/detalhe e retries (C13, C15).
4. **Com evidência de uso/concorrência:** otimização de locks (C14) e navegação configurável/limpeza de mensagens históricas (C23).

As pendências orientam os prompts posteriores. A correção dos U0 não constitui implementação dos itens 2.2–2.6.

## Validação e limites

**Auditoria inicial:** os probes estáticos de 05/10 confirmaram 11 tipos/22 relações/2 invariantes, transições ordinárias para seis tipos, `commits_to=1..1`, FKs externas limitadas a Workspace/User nos models core/semantic e as lacunas originais de human-only/ORM. Não houve pytest/browser nessa etapa. As evidências históricas dos achados corrigidos não descrevem o comportamento atual.

**Entrega U0 de 06/10:** os resultados finais estão em [result.json](../../output/core-u0-20261005/result.json), com comandos e logs em [output/core-u0-20261005](../../output/core-u0-20261005/README.md). A pasta conserva a data de início do trabalho.

- Backend RADAR: **305 casos, 301 aprovados, 4 opt-in ignorados, zero falhas/erros**, incluindo **33 casos U0 novos**. Evidência: [JUnit final](../../apps/api/output/core-u0-final.xml) e [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py).
- Frontend: **93 testes aprovados em 14 arquivos**, incluindo a correção do seletor de cardinalidade.
- Checks aprovados: Ruff, formatação Python, OxLint, Oxfmt, TypeScript e `makemigrations radar --check --dry-run`.
- Migration: duas invariantes normativas instaladas nos tipos legados, tipo customizado e identidades preservados; upgrade 0010 → 0011, downgrade e novo upgrade aprovados em banco descartável. Evidência: [resultado da migration](../../apps/api/output/core-u0-migration.json).

Não foram reexecutados a suíte completa do Plane fora de RADAR, testes de navegador ou opt-ins de provider real/CoS. Não há benchmark novo nem confirmação de implantação. A barreira ORM tem os limites descritos em C10; o digest conservador e o downgrade têm os limites descritos em C06. Lifecycle customizado, formulário de required fields, upgrades gerais de schema e divergência de prazos continuam pendências U1, sem alegação de cobertura integral.

**Esta atualização é documental:** altera somente `docs/radar/CORE_AUDIT.md`, registra as implementações e evidências existentes e verifica formatação/links. As suítes acima foram executadas na entrega U0; não foram repetidas para esta edição do relatório.
