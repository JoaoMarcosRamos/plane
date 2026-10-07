# RADAR Core — Auditoria 2.1

**Auditoria inicial:** 05/10/2026, America/Bahia. **Atualização:** 07/10/2026. **Entrega:** prompt 2.1 de [radar_prompts_por_fase.md](../../../DOCS_PROJETO_RADAR_COMPLETO/radar_prompts_por_fase.md), com acompanhamento das correções U0 e das fases 0–6 do plano U1 e das pendências U2 posteriormente autorizadas.

> **Estado atual (07/10/2026):** os 5 U0 e os 16 U1 foram corrigidos no código, incluindo C13/fase 6. C23 foi corrigido com navegação e views pelo catálogo de tipos. C14 recebeu medição de concorrência e instrumentação de espera/retenção; **a coordenação conservadora por workspace permanece como limite arquitetural medido**, sem otimização de granularidade. Saldo: **22 achados corrigidos e 1 limite U2 medido**. A migration 0017 acrescenta índices para paginação, validada por ida/volta/reaplicação em banco descartável; nenhuma ativação ou homologação de ambiente publicado. O aceite integrado local combina configuração, criação/UI, relação obrigatória, lifecycle, runtime, autoria, revisão e replay, com limites descritos no [relatório das pendências](CORE_PENDING_REPORT.md). As entregas anteriores conservam sua evidência nos relatórios [U0](CORE_U0_REPORT.md), [0/1](CORE_U1_PHASE_01_REPORT.md), [2](CORE_U1_PHASE_02_REPORT.md), [3A](CORE_U1_PHASE_03_REPORT.md), [3B/3C](CORE_U1_PHASE_03BC_REPORT.md), [4](CORE_U1_PHASE_04_REPORT.md), [5A](CORE_U1_PHASE_05A_REPORT.md) e [5B](CORE_U1_PHASE_05B_REPORT.md).

## Conclusão

O RADAR já possui persistência independente de WorkItem: `Object`, `ObjectType`, propriedades e relações têm models, tabelas e commands próprios. Não há FK para Project ou Issue do Plane nesses models. A navegação por tipo usa o catálogo ativo do workspace, com views genéricas filtradas no servidor. Os registros operacionais permanecem especializações tipadas, com fontes canônicas e histórico explícito desde 5B. Identidade e elegibilidade de runtime passaram a descritores do workspace na entrega 5A. O dispatcher e a autoridade de efeitos consomem o registro/plano comum desde a entrega 3A. Desde a 3B/3C, a seleção de criação e as transições são descritores do workspace sobre capabilities e guards registrados. Desde a fase 4, o formulário de criação, o editor e a apresentação da Object Page derivam desses descritores e de capacidades calculadas pelo servidor.

O Core permite criar um tipo adicional com criação, lifecycle e apresentação configurados por commands auditados, criá-lo na UI com seus campos obrigatórios e operá-lo com transições governadas, sem branch por nome. A entrega 5A demonstra acesso de tipo customizado pelo runtime autorizado com opt-in e binding explícitos. **Fatos operacionais canônicos e histórico paginável foram entregues em C18/5B**; a fase 6 entrega consultas delimitadas e aceite integrado local em 07/10/2026. Não há homologação do ambiente publicado.

Dos **23 achados**, os **5 U0 foram corrigidos**: restrições de domínio passaram a ter escopo de tipo; escrita e derivação de propriedades usam uma implementação compartilhada; invariantes do workspace e contrato de implementação integram o fingerprint de aprovação; relações obrigatórias têm validação genérica em momentos definidos; e os models do Core bloqueiam escrita ORM fora do contexto de command. A regressão final teve **301 testes backend aprovados, 4 opt-in ignorados e 93 testes frontend aprovados**, incluindo 33 casos U0 novos.

As fases 0/1 do [plano U1](CORE_U1_IMPLEMENTATION_PLAN.md) corrigiram autoria por actor/provenance (C22), interfaces públicas e resultados sem serializers HTTP no domínio (C16), e replay de defaults/retries com intenção estável (C15). A validação final teve **319 backend aprovados, 4 opt-in ignorados e 106 frontend aprovados**.

A fase 2 do plano U1 entregou instalação/upgrade de schema por workspace (C07), leitura operacional uniforme (C11), revisão de metadata em snapshots/cache/formulários (C12) e o registro estrutural de kinds/config/relações (parte de C17). A regressão teve **356 backend aprovados, 4 opt-in ignorados e 114 frontend aprovados**; os 5 testes de transporte foram reexecutados após o ajuste de CORS, sem somar a contagem. A migration 0012 passou por ida, volta e reaplicação. O navegador confirmou preservação de rascunhos, revisão explícita e persistência sob schema revision 2.

A entrega 3A concluiu C09/C17: registro único de capabilities, planos transacionais completos e verificação de autoridade/versões/efeitos na revisão e execução. As entregas 3B/3C concluíram C02/C01: criação pelo descritor do tipo, separando propriedades de parâmetros compostos, e lifecycle explícito aplicado no writer comum de propriedades. A regressão final teve **452 backend aprovados e 4 opt-in ignorados**. A fase 4 concluiu C03/C20/C21: formulário de criação por metadata, editor por capacidades efetivas e apresentação com narrativa principal; a regressão teve **477 backend aprovados, 4 opt-in ignorados e 132 frontend aprovados**, com prova de navegador sobre API e PostgreSQL reais. A entrega 5A concluiu C19, com identidade e contexto por descritor validado, mantendo grants, review, histórico e provisioning explícitos. A entrega 5B concluiu C18 com prazo/executores canônicos, histórico imutável paginado e backfill explícito. Após a entrega de 07/10/2026, o saldo dos **23 achados é de 22 corrigidos e 1 limite U2 medido** (C14). As correções não equivalem a builders completos com UI nem a fatos operacionais inteiramente configuráveis por metadata. A entrega não demonstra homologação em produção: a ativação exige disponibilizar o app RADAR, aplicar sua cadeia de migrations e instalar/atualizar explicitamente o schema dos workspaces no ambiente alvo.

## Escopo e método

- Base observada: worktree `plane-radar-phase-0-spike`, HEAD `8fa56b19d7864da0c80a4ae92dc4371d5487699e`. O HEAD **não representa sozinho o estado auditado**: há mudanças staged, unstaged e arquivos untracked anteriores a esta auditoria.
- Backend: `apps/api/plane/radar/{models,commands,api,ontology}`, runtime/configuração, Risk Review, Today e colaboração presentes no filesystem. Frontend: componentes, services, stores e rotas RADAR.
- Foram lidos contratos arquiteturais e testes existentes para distinguir garantias atuais de lacunas. Colaboração, Risk Review e Today foram incluídos mesmo quando documentos históricos ainda os apresentavam como próximos passos.
- O snapshot efetivamente carregado contém **11 tipos, 22 tipos de relação e 2 invariantes**, versão `3.2.0`; não apenas os cinco tipos iniciais do spike.
- Na auditoria inicial, foram feitos probes locais de leitura usando JSON/AST: inventário do snapshot, tabela de transições, FKs externas, métodos do queryset e execução isolada de `_is_human_only`. Não houve escrita no banco, acesso ao runtime, benchmark ou execução de pytest/browser nessa etapa.
- COS_AGENT_V2 e a ontologia externa são fronteiras de integração, não objetos de auditoria integral. As conclusões sobre essas fronteiras se apoiam no código consumidor do Plane. Recursos `spike/` são protótipos, não implementação produtiva.
- As referências abaixo são relativas a este arquivo. Os intervalos de linhas preservados nos achados pendentes identificam a evidência histórica da auditoria inicial; as seções de correções U0/U1 e as notas de acompanhamento descrevem a implementação atual por arquivo e função.
- A atualização incorpora código, migrations, testes e evidências de U0 e das fases 0–3 do plano U1. Os probes e limitações da auditoria estática acima descrevem o método inicial, não a validação posterior. As fases anteriores foram conferidas novamente por baseline PostgreSQL isolada nas entregas 3A e 3B/3C; regressões e validações estão nos relatórios específicos.

## Critérios de classificação

**Impacto** mede a consequência: **alto** afeta extensibilidade central, integridade, autoridade ou operação de fluxos; **médio** afeta partes da experiência, consistência ou manutenção; **baixo** é localizado e predominantemente editorial.

**Urgência:** **U0** = resolver o contrato antes de liberar novas escritas de metadata/tipos que acionem o problema; **U1** = endereçar no desenho e implementação dos builders/capabilities da Fase 2 de produto; **U2** = melhoria posterior, com limite explícito enquanto persistir. A Fase 2 de produto dos prompts 2.x é distinta das fases 0–6 do [plano de correções U1](CORE_U1_IMPLEMENTATION_PLAN.md). A auditoria inicial não refatorou o Core; U0 e as fases 0–3 de U1 foram implementados mediante autorização posterior.

**Risco** mede a possibilidade de efeitos indevidos ou regressões se a situação persistir: **alto** envolve inconsistência de fatos/autoridade/auditoria; **médio** envolve fluxos bloqueados, divergência de contratos ou escala sem proteção; **baixo** envolve apresentação ou manutenção localizada. As consequências projetadas estão descritas separadamente da evidência confirmada.

## Matriz dos achados

Impacto, urgência e risco conservam a **classificação original** para rastreabilidade. A coluna Status indica o trabalho ainda aberto; um achado corrigido não representa um problema ainda presente no código. A aplicação da migration é uma condição de ativação comum à entrega, não uma confirmação de implantação.

| ID  | Problema                                                                 | Categorias                       | Impacto | Urgência | Risco | Status               |
| --- | ------------------------------------------------------------------------ | -------------------------------- | ------- | -------- | ----- | -------------------- |
| C01 | Ciclo de vida fechado por tipo em Python                                 | Tipos; hardcoded; metadata       | Alto    | U1       | Alto  | Corrigido U1 3C      |
| C02 | CreateObject redireciona tipos conhecidos para contratos fechados        | Tipos; acoplamento; hardcoded    | Alto    | U1       | Médio | Corrigido U1 3B      |
| C03 | Formulário de criação não deriva campos de PropertyDefinition            | Duplicação; tipos; metadata      | Alto    | U1       | Médio | Corrigido U1 fase 4  |
| C04 | Nomes de campos/estados reservados globalmente sem escopo de tipo        | Hardcoded; acoplamento           | Alto    | U0       | Alto  | Corrigido no código  |
| C05 | Duas implementações de escrita/invariantes semânticos                    | Duplicação; acoplamento          | Alto    | U0       | Alto  | Corrigido no código  |
| C06 | Invariantes e regras executáveis fora do schema efetivo de workspace     | Metadata; acoplamento            | Alto    | U0       | Alto  | Corrigido no código  |
| C07 | Seed sem evolução/versionamento por workspace                            | Acoplamento; metadata            | Alto    | U1       | Alto  | Corrigido U1 fase 2  |
| C08 | Cardinalidade 1..1 incompleta e divergente na UI                         | Duplicação; metadata             | Alto    | U0       | Alto  | Corrigido no código  |
| C09 | Membership e papéis repetidos; efeitos autorizados por listas manuais    | Duplicação; hardcoded; metadata  | Alto    | U1       | Alto  | Corrigido U1 3A      |
| C10 | Model/queryset do Core não exigem contexto de command para toda escrita  | Acoplamento; integridade         | Alto    | U0       | Alto  | Corrigido no código  |
| C11 | Visibilidade de tipos/propriedades/relações inativos é inconsistente     | Duplicação; acoplamento          | Alto    | U1       | Alto  | Corrigido U1 fase 2  |
| C12 | Object.version não cobre mudanças de metadata                            | Acoplamento; metadata            | Alto    | U1       | Alto  | Corrigido U1 fase 2  |
| C13 | Object Page e seletores carregam todo o workspace                        | Acoplamento; escala              | Médio   | U1       | Médio | Corrigido U1 fase 6  |
| C14 | Writes e inicialização de schema serializam o workspace inteiro          | Acoplamento; escala              | Médio   | U2       | Médio | Medido; lock mantido |
| C15 | Defaults internos e retries não têm o mesmo contrato de idempotência     | Duplicação; acoplamento          | Médio   | U1       | Médio | Corrigido no código  |
| C16 | Domain handlers dependem de serializers HTTP e funções privadas          | Acoplamento                      | Médio   | U1       | Médio | Corrigido no código  |
| C17 | Catálogo e contratos estruturais repetidos manualmente                   | Duplicação; hardcoded; metadata  | Médio   | U1       | Médio | Corrigido U1 3A      |
| C18 | OperationalRecord cria metadata operacional paralela                     | Hardcoded; acoplamento; WorkItem | Alto    | U1       | Alto  | Corrigido U1 5B      |
| C19 | Tipo criado no workspace não ganha identidade/contexto de runtime        | Tipos; acoplamento; metadata     | Alto    | U1       | Médio | Corrigido U1 5A      |
| C20 | Editor genérico não conhece campos derivados, guards e ações disponíveis | Metadata; WorkItem               | Alto    | U1       | Médio | Corrigido U1 fase 4  |
| C21 | Página universal de título/conteúdo e descrição concorrente              | Hardcoded; WorkItem              | Médio   | U1       | Médio | Corrigido U1 fase 4  |
| C22 | Autoria resumida da página ainda pressupõe User humano                   | Acoplamento; WorkItem            | Médio   | U1       | Médio | Corrigido no código  |
| C23 | Navegação por tipos é estática e contém placeholders                     | Tipos; hardcoded; metadata       | Médio   | U2       | Baixo | Corrigido U2         |

## Evidências e consequências

### C01 — Ciclo de vida fechado por tipo em Python

**Impacto alto · Urgência U1 · Risco alto.**

[rules.py](../../apps/api/plane/radar/commands/rules.py) mantém `ORDINARY_TRANSITIONS`, consumido por [handlers.py](../../apps/api/plane/radar/commands/handlers.py), que aplica guards dedicados para Action, Decision, Document e Indicator. A entrega U0 moveu a tabela e a incluiu no contrato de implementação; não tornou o grafo configurável. [operations.py](../../apps/api/plane/radar/commands/operations.py), linhas 116–119 e 182–193, acrescenta estados de delegação e mapeamentos de disposition. Defaults/vocabulários/terminais são metadata, mas o grafo de transições e a associação a commands não são.

Um tipo adicional com enum `status` pode ser criado e ter outros campos editados, porém uma mudança de estado é recusada por falta de entrada na tabela. Mesmo entre os tipos semeados, `case`, `commitment`, `decision`, `indicator` e `management_item` não têm transições ordinárias; alguns têm caminhos dedicados, o que não equivale a um ciclo de vida genérico. Não se deve preencher todas as transições automaticamente: etapas terminais e decisões humanas possuem guards legítimos.

**Direção para etapa futura:** declarar lifecycle, transições e capabilities por tipo, apontando para handlers tipados de validação/efeitos. Independência de aprovação, evidência obrigatória e autoridade devem continuar garantias executáveis.

**Correção U1 3C (06/10/2026):** `ObjectType.rules.lifecycle` persiste propriedade de estado, inicial e transições explícitas. Cada transição referencia uma capability registrada (UpdateObject, CompleteAction, ReviewObject com disposition, DelegateAction) e, opcionalmente, um guard registrado e um carimbo datetime. `ORDINARY_TRANSITIONS` foi removido; a migration de dados 0013 e o pacote reproduzem exatamente a tabela anterior e declaram os caminhos especializados, incluindo o mapa de disposition de `operations.py`. O writer comum de propriedades aplica o lifecycle a toda entrada: API, compatibilidade, primitives, runtime e handlers internos. Pares não declarados continuam bloqueados, terminais exigem saída declarada e carimbos são protegidos. CompleteAction, ApproveDecision e o guard `decision_approval` continuam handlers tipados com evidência e autoridade executáveis. Lifecycle inválido é recusado na configuração. Tipo customizado com lifecycle faz transições sem branch por nome; sem lifecycle, `status` é propriedade comum. Guards que não são transições (Decision tomada imutável, observações de Indicator, evidência usada) permanecem em código. [Relatório](CORE_U1_PHASE_03BC_REPORT.md), [ADR](CORE_U1_PHASE_03BC_ADR.md).

### C02 — Criação genérica redirecionada a contratos fechados

**Impacto alto · Urgência U1 · Risco médio.**

[handlers.py](../../apps/api/plane/radar/commands/handlers.py), linhas 170–185 e 442–452, transforma `CreateObject` em `CreateAction`, `RegisterRisk` ou `CreateDecision` pelo `ObjectType.key`. Os serializers em [inputs.py](../../apps/api/plane/radar/commands/inputs.py), linhas 117–155, e os handlers nas linhas 563–625 têm listas próprias de campos e relações.

Adicionar uma propriedade válida ao tipo `action` no workspace não basta para enviá-la na criação genérica: `_special_input` passa o payload ao serializer especializado, que rejeita campos desconhecidos. Tipos novos seguem outro caminho. A política de estado inicial também consulta o snapshot global, em vez do default persistido do workspace.

**Direção futura:** explicitar a capability de criação e os requisitos/efeitos de cada tipo em metadata. Preservar os comandos semânticos; retirar do dispatcher genérico a necessidade de conhecer todo tipo novo.

**Correção U1 3B (06/10/2026):** `ObjectType.rules.creation` seleciona uma capability com perfil de criação registrado. O perfil declara tipos aceitos, parâmetros compostos, requisitos mínimos, iniciais aceitos e efeitos. `CreateObject` valida `properties` pelas definições do workspace e `parameters` pelo perfil; o redirecionamento por `ObjectType.key` foi removido. CreateAction, RegisterRisk e CreateDecision são fachadas do mesmo caminho. Uma propriedade extra válida em tipo semeado é persistida com relações, eventos, findings e autoridade compostos preservados. Criações internas também exigem a capability declarada. O estado inicial vem do lifecycle persistido e é limitado pelo perfil na configuração. Referências compostas enviadas em `properties` passam a ser recusadas; o formato correto é `parameters`. [Relatório](CORE_U1_PHASE_03BC_REPORT.md).

### C03 — Criação na UI não usa propriedades obrigatórias da metadata

**Impacto alto · Urgência U1 · Risco médio.**

[create-object-input.ts](../../apps/web/components/radar/create-object-input.ts), linhas 3–15, define `context/decision/rationale` para Decision e `description` para Action/Risk. [create-object-dialog.tsx](../../apps/web/components/radar/create-object-dialog.tsx), linhas 28–43 e 98–109, usa essa lista e campos de texto, sem consultar definições. O tipo inicial também é fixado como `objective`.

Ao adicionar uma propriedade obrigatória sem default a um tipo, o backend corretamente bloqueia a criação incompleta; a UI não oferece o campo necessário. O teste existente [test_semantic.py](../../apps/api/plane/radar/tests/test_semantic.py), linhas 639–647, documenta essa validação de backend. O probe do snapshot atual não encontrou atributos obrigatórios sem default além dos cobertos pela UI; a falha de extensibilidade surge ao ampliar a configuração, não foi atribuída a todos os seeds atuais.

**Direção futura:** formulário de criação orientado por definições/capability de criação, incluindo tipos de valor e campos necessários aos efeitos compostos.

**Correção U1 fase 4 (06/10/2026):** `create-object-input.ts` deriva o formulário das `PropertyDefinition` ativas e do perfil de criação declarado. Required sem default e requisitos do perfil são exigidos; opcionais e defaults não alterados não são reenviados; derivados, estado e carimbos ficam fora, com o inicial do lifecycle informado. Parâmetros compostos usam seletores de Object filtrados pela dica `object_types` do contrato (`ObjectReferenceField`). Não há tipo padrão; perfil ausente do catálogo torna o tipo indisponível; relações 1..1 são anunciadas. Os controles são compartilhados com o editor e a precondição de revisão de schema impede envio obsoleto. O navegador criou, pela UI, um tipo existente apenas no workspace exigindo seu required sem default. [Relatório](CORE_U1_PHASE_04_REPORT.md).

### C04 — Colisões de nomes globais

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** nomes como `score`, `likelihood/impact`, `decided_at` e `status=decided` acionavam restrições de Risk/Decision em qualquer tipo, mesmo quando tinham outro significado.

**Implementação:** [handlers.py](../../apps/api/plane/radar/commands/handlers.py) limita a restrição de `decided_at` e o human-only de `status=decided` ao tipo Decision. Na criação, campos derivados são descobertos pelas invariantes do ObjectType. A checagem de grants usa `property_effect_fields`, incluindo resultados que precisam ser materializados ou reparados; não deduz autoridade por nomes globais.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre tipos customizados com nomes coincidentes e autoridade sobre campos derivados com outras chaves. Um `score` sem invariante de derivação pode ser preenchido normalmente.

**Limite:** guards especializados continuam em código e cobertos pelo contrato de implementação. O lifecycle configurável foi entregue em C01 (3C); a apresentação de capacidades por campo permanece C20, U1.

### C05 — Duas implementações de invariantes/escritas

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** handler e primitive mantinham leituras, derivação e persistência próprias, com comportamentos diferentes para fatores ausentes, produtos e patches não relacionados.

**Implementação:** [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py) centraliza `effective_values`, `plan_properties`, `property_effect_fields` e `patch_properties`. O handler, as primitives de edição/remoção e a inicialização de defaults usam esse engine. A antiga `_invariant_changes` foi removida. Os operadores tipados de [rules.py](../../apps/api/plane/radar/commands/rules.py) calculam produtos com todos os fatores declarados via `math.prod`.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) verifica paridade entre writers, produtos com múltiplos fatores, grants sobre efeitos derivados e rollback de valores, versões, eventos e provenance em batches inválidos.

**Limite:** a semântica compartilhada não resolve todos os efeitos compostos enumerados manualmente (C09). O contrato de idempotência de defaults/retries (C15), originalmente separado dessa entrega, foi corrigido nas fases 0/1 de U1.

### C06 — Regras executáveis fora do schema efetivo

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** invariantes eram lidas do snapshot global, enquanto propriedades efetivas pertenciam ao workspace. O fingerprint de aprovação não cobria a revisão dos handlers/guards Python.

**Implementação:** `ObjectType.rules` persiste invariantes por workspace, expostas em modo somente leitura pelo serializer. [rules.py](../../apps/api/plane/radar/commands/rules.py) valida os operadores fechados `ordered_dates` e `product`, suas referências, tipos ativos e limites, recusando metadata desconhecida e produtos encadeados/cíclicos. Não executa scripts de metadata.

[execution.py](../../apps/api/plane/radar/commands/execution.py) inclui essas regras e `implementation_contract()` no `schema_fingerprint`. O contrato combina a revisão `2.1.u0.1` com digest determinístico dos módulos Python RADAR de produto, excluindo tests, migrations e management commands. É registrado no envelope persistido/provenance e vincula preview, review e execução: mudança de metadata ou implementação impede consumir uma aprovação pendente sob o contrato anterior. Replays de execuções confirmadas devolvem o resultado histórico.

`command_envelope` projeta somente os campos declarados de entrada ao retomar uma intenção em sessão, Risk Review e runtime. Campos do servidor como `rules_contract/schema_hash` não são reenviados como input do cliente. `command_version=1` permanece a versão do protocolo de entrada, separada da revisão de semântica.

**Migration:** [0011_objecttype_rules.py](../../apps/api/plane/radar/migrations/0011_objecttype_rules.py) instala as duas invariantes normativas em Objective/Risk existentes e preserva tipos customizados com `{}`, identidades, estado ativo e autoria. Na fase 2 de U1, workspaces novos passaram a receber as regras pela instalação administrativa explícita do pacote (C07).

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre regras inválidas, alterações de metadata/código antes e depois do review e ownership do contrato pelo servidor. Upgrade, downgrade e novo upgrade foram verificados em banco descartável.

**Limites:** o digest é conservador e pode invalidar uma intenção por mudança de código sem efeito específico nela. Não foi criada uma API pública de edição de regras nem lifecycle configurável (C01). A migration ainda precisa ser aplicada ao ambiente em uso; downgrade remove a coluna e perde customizações posteriores, exigindo exportação prévia para preservá-las.

### C07 — Instalação e upgrade por workspace — corrigido

**Impacto alto · Urgência original U1 · Risco alto.**

A evidência inicial era o uso de `get_or_create` em GETs, sem base instalada ou evolução de metadata. A fase 2 substituiu esse comportamento por estado de schema/revisão, instalação administrativa explícita, preview e upgrade com diff de três vias. A base materializada e IDs geridos permitem preservar customizações, inativação e soft-delete. Conflitos e incompatibilidades factuais são diagnosticados antes de upgrade; falhas revertem metadata, estado, histórico e provenance na mesma transação.

A migration 0012 registra workspaces existentes como legados, com diferenças/ausências e versão desconhecida; conserva IDs/fatos e mantém workspaces vazios sem instalação. Initializers Python são fachadas de provisioning auditado. GETs operacionais não criam schema.

**Limites:** não há execução automática de migração de fatos nem UI de builder. Kind changes e incompatibilidades exigem migração explícita; não há sobrescrita forçada de conflitos. Decisões e evidências no [ADR da fase 2](CORE_U1_PHASE_02_ADR.md) e [relatório](CORE_U1_PHASE_02_REPORT.md).

### C08 — Cardinalidade obrigatória parcialmente implementada

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** o máximo de `1..1` era protegido no servidor, mas ignorado pelo seletor. O mínimo era exigido especificamente no binding de Commitment, sem um contrato genérico de momento de validação.

**Implementação:** `validate_required_relations` em [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py) consulta RelationType ativo, domínio/codomínio, allowed_pairs, self-link e endpoints ativos. O mínimo é exigido em mudanças efetivas de status, no binding de runtime e ao concluir efeitos compostos que criaram/tocaram Objects já vinculados, tanto no preview quanto na execução, incluindo commands internos.

A criação isolada permite **montagem** de propriedades e relações em commands subsequentes, independentemente do nome do status default. No [binding](../../apps/api/plane/radar/commands/runtime_control.py), o único target obrigatório precisa estar vinculado no mesmo contexto. A validação específica de Commitment foi substituída pelo contrato genérico. Máximo com locks e bloqueio de remoção independente continuam garantidos pelo servidor.

[semantic-utils.ts](../../apps/web/components/radar/semantic-utils.ts) trata `0..1` e `1..1` como máximo de um ao filtrar candidatos sobre as relações conhecidas.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) cobre montagem, transição, binding e revalidação de escrita interna em Object vinculado; [semantic-utils.test.ts](../../apps/web/components/radar/semantic-utils.test.ts) cobre o seletor.

**Limites:** não foi criado um workflow universal de conclusão de draft. A UI filtra dados conhecidos; a validação definitiva permanece no backend. Identidade de runtime de tipos adicionais continua C19/U1.

### C09 — Autoridade comum e planejamento de efeitos — corrigido

**Impacto alto · Urgência original U1 · Risco alto.**

A evidência inicial eram traduções de roles espalhadas e listas manuais de tipos, campos, referências e commands compostos. A entrega 3A centraliza membership/admin em `commands/access.py`, inclusive colaboração, e associa inputs, referências, handlers, planners e políticas ao registro executável de capabilities.

`commands/effects.py` exercita o handler sob savepoint revertido e captura todos os efeitos/dependências observados. O mesmo plano fornece grants, locks/versões, preview e review; a execução é recapturada e comparada antes do flush. Defaults, campos derivados, relações removidas e payloads privados integram a autoridade. Efeito inesperado, grant parcial ou mudança de dependência recusa a intenção atomicamente. Referências do input e Objects escritos exigem versões explícitas; leituras auxiliares conservam versões capturadas pelo servidor e também invalidam review quando mudam.

**Compatibilidade/limites:** coordenação conservadora de Workspace e guards especializados permanecem. Confirmed replay usa autoridade persistida e grant atual; ledgers anteriores sem plano usam uma declaração histórica isolada, sem participar de novas escritas. Criação/lifecycle declarativos foram entregues em 3B/3C (C02/C01); otimização de locks é C14. [ADR](CORE_U1_PHASE_03_ADR.md), [relatório/evidências](CORE_U1_PHASE_03_REPORT.md).

### C10 — Proteção desigual contra escrita ORM fora de commands

**Classificação original: impacto alto · Urgência U0 · Risco alto. Status: corrigido no código em 06/10/2026.**

**Problema original:** o Core bloqueava delete direto, mas `save`, `update`, `bulk_create` e `bulk_update` podiam escrever fora do contexto de command, sem as garantias de autoridade/provenance. FKs isoladas também não asseguravam tenant/tipo compatíveis.

**Implementação:** [RadarBaseModel e RadarQuerySet](../../apps/api/plane/radar/models/core.py) exigem contexto de mutação do mesmo workspace, tornam workspace/criador existentes imutáveis, bloqueiam alterações ordinárias dos ponteiros de provenance e validam FKs RADAR no tenant. [PropertyValue](../../apps/api/plane/radar/models/semantic.py) verifica a definição contra o ObjectType do Object.

Querysets recusam `update`, `bulk_create` e `bulk_update`. A única exceção é o flush de [MutationContext](../../apps/api/plane/radar/mutation.py), para ponteiros de provenance com o ID corrente e somente registros capturados pela própria mutação no mesmo workspace. A exceção é encerrada em `finally`.

**Validação:** [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py) verifica bloqueio sem command, isolamento de workspace/FKs, imutabilidade, tentativa de falsificar provenance e flush/replay legítimos. Setups históricos de testes antigos usam [fixture_writes.py](../../apps/api/plane/radar/tests/fixture_writes.py) explicitamente por chamada, sem bypass de produto ou fixture autouse; os comandos executam os guards reais.

**Limites:** a proteção cobre descendentes de RadarBaseModel. SQL administrativo, models históricos de migration e ledgers/eventos/runs com writers próprios da aplicação estão fora dessa barreira ORM. O contexto é uma fronteira interna de escrita; builders devem usar commands autorizados.

### C11 — Política comum de leitura operacional — corrigido

**Impacto alto · Urgência original U1 · Risco alto.**

A auditoria inicial identificou divergência entre lista, detalhe, snapshots e contexto. A fase 2 centraliza queries em [active.py](../../apps/api/plane/radar/active.py): Object/tipo, definição/valor e relação/endpoints precisam estar ativos, não excluídos e no workspace correto. Lista, detalhe, propriedades/relações, Today, Risk Review e runtime aplicam essa política; metadata retirada deixa de entrar no contexto corrente.

O endpoint autorizado de provenance usa `all_objects` explicitamente para conservar histórico de recursos retirados. Testes cobrem inativação/soft-delete, ausência uniforme nas superfícies operacionais e leitura histórica. A query de contexto omite valores/arestas retirados. [Relatório da fase 2](CORE_U1_PHASE_02_REPORT.md).

**Limite:** histórico autorizado não implica reativação, elegibilidade operacional ou permissão de escrita. Paginação e delimitação geral da lista permanecem em C13.

### C12 — Revisão de metadata nos snapshots/cache — corrigido

**Impacto alto · Urgência original U1 · Risco alto.**

A comparação exclusiva por `Object.version` foi substituída por revisão separada de schema. Metadata muda a revisão uma vez por transação auditada, sem incrementar todos os Objects. Catálogo agregado e snapshots usam lock de Workspace e anunciam `schema_revision`; adapters de arrays expõem a revisão por cabeçalho. Today, contexto e capabilities de runtime também anunciam a revisão.

O cliente rejeita catálogo/snapshot antigo, evita combinar revisões diferentes e preserva rascunhos durante atualização. Formulários exigem revisão explícita; escrita genérica de sessão envia precondição de schema. Retry conserva o envelope original. Replay confirmado precede conflitos de schema, inclusive para intenções confirmadas v1 sem o novo campo; propostas pendentes sob metadata anterior tornam-se obsoletas.

Membership/role e grant têm invalidação de autoridade separada; o servidor revalida autoridade em cada acesso. Testes cobrem corrida de respostas, revisões incompatíveis, permissões, retry/replay e aprovação obsoleta. O navegador e PostgreSQL confirmam o fluxo de revisão/persistência. [Relatório](CORE_U1_PHASE_02_REPORT.md).

**Limites:** polling de 30 segundos/foco descobre mudanças; precondição do servidor cobre a corrida antes da descoberta visual. Callers Python confiáveis e runtime v1 podem omitir a precondição durante compatibilidade, conservando validação/fingerprint. O contrato de capabilities/lifecycle foi entregue na fase 3; sua apresentação detalhada por campo e ação na UI pertence à fase 4.

### C13 — Detalhe exige catálogo inteiro

**Impacto médio · Urgência U1 · Risco médio.**

[ObjectsView](../../apps/api/plane/radar/api/views.py), linhas 68–71, serializa todos os Objects sem paginação/filtro server-side. [root.store.ts](../../apps/web/store/radar/root.store.ts), linhas 74–78 e 158–161, carrega a lista inteira também na Object Page. O seletor em [semantic-utils.ts](../../apps/web/components/radar/semantic-utils.ts), linhas 13–40, filtra candidatos localmente.

A navegação de uma entidade e seus backlinks depende do volume total do workspace. O catálogo repete `object_type_detail` e inclui content. A consequência de escala é inferida da consulta; não há latência ou limite de volume medido nesta entrega.

**Direção futura:** paginação, busca de candidatos por relation/type/capability e resolução dos endpoints necessários ao detalhe. Manter tenant/autoridade na consulta do servidor.

**Correção C13/fase 6 (07/10/2026):** lista/candidatos são resumos de 50 itens por padrão (máximo 100), com busca e filtros server-side, cursor assinado vinculado ao tenant/filtros/schema e política de relação nas duas direções. Object Page carrega snapshots e resumos apenas dos endpoints da página de relações; permissões de remoção também são paginadas. Seletores de relações/capabilities fazem busca remota; o endpoint é lido com versão antes da mutação. Índices parciais em 0017 apoiam as páginas. Fixtures crescentes demonstram payload/queries/objetos materializados delimitados; busca textual não tem custo de varredura constante presumido. Detalhes, benchmark local, testes e prova de navegador no [relatório](CORE_PENDING_REPORT.md).

### C14 — Lock global de workspace

**Impacto médio · Urgência U2 · Risco médio.**

[execution.py](../../apps/api/plane/radar/commands/execution.py) mantém o lock de Workspace para coordenar execução e commands internos. A fase 2 eliminou a inicialização lazy por GET, mas instalação/upgrade de schema, escritas de fatos e leitura agregada coerente continuam usando a coordenação conservadora por Workspace. Há adicionalmente locks nos Objects para versões e relações.

O lock protege mudanças de schema/grants e é uma escolha conservadora válida no MVP. Seu custo é serializar mutações independentes do mesmo tenant, inclusive com validação/preview no percurso. Não foi medido throughput nem demonstrado deadlock.

**Direção futura:** medir concorrência e tempo dos locks antes de alterar a estratégia; preservar a atomicidade de schema, autoridade e replay ao propor granularidade menor.

**Medição e decisão C14 (07/10/2026):** logger JSON observa `wait_ms`, `held_ms`, operação, resultado e escopo de transação nos commands/schema/snapshots. Teste concorrente PostgreSQL com retenção deliberada de 200 ms confirma aproximadamente 205 ms de espera no mesmo workspace e 1–2 ms em outro tenant. Commit/rollback/nesting preservados. A instrumentação não altera autoridade, replay ou atomicidade. O diagnóstico pendente foi entregue; a serialização continua um **limite arquitetural medido**, mantido até haver workload que justifique e valide uma estratégia menor. Isso não é benchmark de throughput nem otimização de locks. [Decisão e limites](CORE_PENDING_REPORT.md).

### C15 — Defaults internos e retry de intenção

**Classificação original: impacto médio · Urgência U1 · Risco médio. Status: corrigido no código em 06/10/2026.**

**Problema original:** `initialize_object_properties` recebia uma chave que não usava e executava via `run_internal`, sem ledger/replay. No cliente, o service gerava chaves quando a store não conservava uma intenção; resposta perdida podia resultar em nova criação ou conflito de versão no retry de defaults.

**Implementação:** `InitializeObjectProperties` usa o dispatcher/ledger comum, preserva human-only e grava o snapshot confirmado; o endpoint retorna esse snapshot no replay antes de recusar uma versão antiga. No-op e rollback seguem o mesmo contrato. A compatibility layer reutiliza versões do ledger somente quando um caller Python confiável omite o mapa; transport continua exigindo versões e chave explícitas.

`RadarMutationIntents` conserva chave, payload copiado e expected_versions para criação/edição/propriedades/defaults/relações. Resposta incerta mantém a intenção; input alterado ou rejeição definitiva permite nova intenção. Aprovação pendente é conservada e retomada explicitamente. Troca de usuário/workspace recria o provider; não há rebase automático de conflito.

**Validação:** os testes U1 cobrem snapshot histórico, retry de defaults/criação, rollback, revogação, chave conflitante, versões mantidas após refresh da cache e aprovação pendente. Evidências no [relatório das fases 0/1](CORE_U1_PHASE_01_REPORT.md).

**Limites:** intenções ficam em memória; reload exige consultar estado antes de reenviar uma criação incerta. Callers Python sem versões continuam uma compatibilidade confiável. A instalação e evolução do schema foram entregues em C07 na fase 2; retries de fatos conservam também a revisão de schema original, conforme C12.

### C16 — Interfaces públicas da aplicação

**Classificação original: impacto médio · Urgência U1 · Risco médio. Status: corrigido no código em 06/10/2026.**

**Problema original:** handlers importavam serializers de representação HTTP; operations/runtime/Risk Review dependiam de funções privadas de primitives/handlers/execution. Imports locais contornavam ciclos, sem contrato público verificável.

**Implementação:** `commands/context.py`, `access.py`, `queries.py` e `results.py` publicam contexto, membership, lookup/validação/evidência/aprovação e DTOs tipados. Helpers de efeitos, primitives e provisioning usados entre módulos têm nomes públicos e callers atualizados. Handlers deixaram de importar serializers da API, incluindo resultados de Object e Relation. A representação v1 dos resultados persistidos/replays foi preservada.

**Validação:** paridade de JSON Object/Relation/propriedades com adapters e teste de fronteiras impedindo imports privados entre módulos e serializers API nos commands; regressão final e contratos runtime/Risk Review aprovados. Ver [relatório das fases 0/1](CORE_U1_PHASE_01_REPORT.md).

**Limites:** Django/DRF e serializers de input compartilhados continuam na infraestrutura/aplicação. Esta correção não substitui o framework nem implementa o registro de capabilities/efeitos de C09/C17.

### C17 — Contratos/catálogos repetidos manualmente — corrigido

**Classificação original: impacto médio · Urgência U1 · Risco médio. Status: parte estrutural entregue na fase 2 e conclusão na entrega 3A em 06/10/2026.**

**Evidência original:** tipos de propriedade apareciam em [models/semantic.py](../../apps/api/plane/radar/models/semantic.py), linhas 5–17, [services/types.ts](../../apps/web/services/radar/types.ts), linhas 45–65, no validador de primitives e no parser/editor da UI. [api/serializers.py](../../apps/api/plane/radar/api/serializers.py), linhas 48–70, repetia o bloqueio de campos desconhecidos já presente no `StrictSerializer`. `DEFINITIONS` em [runtime_views.py](../../apps/api/plane/radar/api/runtime_views.py), linhas 40–74, repetia parâmetros/target_types dos serializers operacionais e handlers.

Na base auditada, uma capability nova precisava ser mantida em input, dispatch, catálogo, references, grants e client types. A repetição de validação no cliente continua útil para UX; o registro/paridade da entrega 3A corrigiu a falta de contrato comum. Os kinds de valor atuais são operadores estruturais legítimos. A ausência de `rich_text`/`object_reference` no catálogo atual é escopo futuro do 2.4, não bug de um campo já suportado.

**Entregue na fase 2:** [ontology/contracts.py](../../apps/api/plane/radar/ontology/contracts.py) centraliza os 11 kinds e schemas de config/descritores de relações, validados antes de persistir. `pnpm check:radar-contracts`, integrado ao `pnpm check`, verifica equivalência de 11 kinds, 5 chaves de config e 3 cardinalidades com o cliente. Aliases futuros estão declarados, sem adicionar kinds persistidos. Ver [relatório da fase 2](CORE_U1_PHASE_02_REPORT.md).

**Concluído na entrega 3A:** `commands/capabilities.py` registra as 21 capabilities existentes. `INPUTS`/`OPERATIONS` são views do registro; dispatch e referências o consomem. O runtime gera parâmetros dos inputs e elimina `DEFINITIONS`; as operações usam handlers/guards selecionados diretamente pelo registro. Catálogo de schema/runtime expõe contratos tipados, políticas mínimas, targets e transporte, incluindo multipart autenticado. CI verifica nove tipos de campo do contrato com o cliente; testes de paridade e execução cobrem cada capability e registro adicional sem listas extras. Constraints e controles do cliente continuam explícitos. Novos kinds de produto e capacidades efetivas por actor permanecem fora deste achado. Ver [entrega 3A](CORE_U1_PHASE_03_REPORT.md).

### C18 — Estado operacional paralelo às propriedades/relações — corrigido

**Impacto alto · Urgência U1 · Risco alto.**

**Evidência original:** [models/commands.py](../../apps/api/plane/radar/models/commands.py), linhas 180–186, mantinha `OperationalRecord.data`. [operations.py](../../apps/api/plane/radar/commands/operations.py), linhas 81–88 e 161–176, gravava `assignment.executor_id/executor_ids/due_at/next_review_at/state/acceptances`. A atribuição também aparecia em relações `assigned_to`. Reviews e measurements acumulavam listas no JSON, nas linhas 194–199 e 226–242.

Na auditoria inicial, Action possuía `due_date` em PropertyValue; delegação gravava outro prazo, `due_at`, no OperationalRecord, e Today só consultava `due_date` ([today.py](../../apps/api/plane/radar/today.py), linhas 62–64). Uma delegação atrasada sem `due_date` não entrava nesse grupo do Today. Esse é um cenário derivado das leituras/escritas, não um teste de runtime executado aqui. O JSON não era mostrado pelo Property Builder/Editor e as listas cresciam sem limite local.

**Correção U1 5B (06/10/2026):** executores correntes em `assigned_to` ativo; prazo de delegação em `Action.due_at` datetime, separado de `due_date`. Today/detalhe/runtime usam projeção comum com fuso explícito e conflito declarado. Delegações/reviews/medições escrevem `OperationalEntry` imutável e tipado, com autoria/evidência/versão/provenance e cursor limitado por Object/kind. Leituras correntes selecionam apenas últimos fatos e não carregam listas do arquivo. A UI filtra/pagina e descarta dados obsoletos/inacessíveis. Migration 0016 expande sem migrar fatos; CLI administrativo aplica backfill revisado/idempotente, preservando originais, precisão e desconhecidos. Novos writers não fazem dual-write. [Relatório](CORE_U1_PHASE_05B_REPORT.md), [ADR](CORE_U1_PHASE_05B_ADR.md).

**Limites:** inventário do stack em uso encontrou tabela legada ausente; backfill representativo foi provado no banco descartável. Definição local incompatível requer reconciliação. Reversão destrutiva é bloqueada; export/restore compatível deve preceder rollback da aplicação. Sem nova negociação de aceitação, deploy ou homologação integrada. C13 continua aberto.

### C19 — Identidade/contexto de runtime por descritor — corrigido

**Impacto alto · Urgência U1 · Risco médio.**

**Evidência original:** [runtime_control.py](../../apps/api/plane/radar/commands/runtime_control.py) recusava tipos sem spec/prefix no snapshot. [operations.py](../../apps/api/plane/radar/commands/operations.py) aplica o mesmo contrato; o ramo de cardinalidade específico de Commitment presente na auditoria inicial foi removido nos U0. [agent_runtime.py](../../apps/api/plane/radar/agent_runtime.py), linhas 105–119, exige identidade no contexto para selecionar Objects.

Um ObjectType adicional no PostgreSQL pode funcionar na API genérica, mas não recebe automaticamente binding para o runtime. A existência de prefixo, formato de ID externo e eligibility para contexto não é metadata do ObjectType persistido. Não é dependência direta de Deep Agents: é um limite do port/contexto atual.

**Acompanhamento U0:** a cardinalidade obrigatória passou a ser genérica (C08); a exigência de spec/prefix global permaneceu naquela entrega e foi removida em 5A.

**Correção U1 5A (06/10/2026):** `ObjectType.rules.runtime` seleciona estratégia registrada, prefixo e categorias de contexto; ausência é desabilitada. Writers de binding e geração usam a mesma política. Tipo customizado pode ser habilitado pelo command auditado de metadata, receber binding explícito e ser lido/revisado no runtime sem alterar o snapshot global. Contextos Plane/Telegram e capabilities filtram elegibilidade ativa, revisão efetiva, grants e escopo. Revogação conserva identidades; mudanças incompatíveis com bindings são recusadas. Migration 0015 preserva IDs, timestamps, opt-outs e base de upgrade. Registro/DTO têm checagem de paridade em CI. [Relatório](CORE_U1_PHASE_05A_REPORT.md), [ADR](CORE_U1_PHASE_05A_ADR.md).

**Limites:** habilitação não cria autoridade/binding; provisioning é administrativo. CoS permanece no protocolo v1, sem mudanças de código. C18 foi entregue em 5B e C13/aceite integrado local em 6; rollback antigo perde a política nova e exige exportação prévia dos descritores.

### C20 — Editor de campos não conhece capabilities/guards

**Impacto alto · Urgência U1 · Risco médio.**

[property-editor.tsx](../../apps/web/components/radar/property-editor.tsx), linhas 34–41 e 73–141, determina edição por `canWrite` e value_type; enums oferecem todos os choices. [semantic-panel.tsx](../../apps/web/components/radar/semantic-panel.tsx), linhas 94–105 e 139–147, oferece remoção de toda relação a quem pode escrever. Não recebe `computed`, `read_only`, transições disponíveis ou requisitos de command/review.

Score derivado aparece como input editável; `completed_at`/`decided_at` e transições protegidas aparecem em formulários genéricos, mas são recusados pelo backend. Relações obrigatórias ou de aprovação também oferecem remoção que será recusada ou ficará pendente. Os guards de backend estão presentes; o problema é o modelo de edição de WorkItem aplicado a uma entidade que possui ações semânticas governadas.

**Direção futura:** capacidades calculadas pelo servidor para campos, transições, comandos e relações; mostrar ações como CompleteAction/ApproveDecision quando disponíveis e manter o servidor como autoridade final.

**Correção U1 fase 4 (06/10/2026):** `GET objects/{id}/capabilities/` calcula, para o actor, editabilidade e razão por campo, opções de estado permitidas, transições e ações disponíveis, removibilidade e review de relações, layout e erros de metadata. Transições e ApproveDecision são sondadas pelo planner real sob savepoint revertido; as restrições especializadas foram extraídas para funções únicas usadas pelo command e pelo cálculo. A UI mostra derivados, carimbos e campos protegidos somente leitura com a razão, limita o estado aos alvos permitidos, não oferece remoção protegida e executa ações governadas com preview e confirmação, distinguindo indisponibilidade corrente de metadata inválida. A API direta continua recusando tudo o que é proibido. [Relatório](CORE_U1_PHASE_04_REPORT.md), [ADR](CORE_U1_PHASE_04_ADR.md).

### C21 — Rich Object reduzido a título/conteúdo universal

**Impacto médio · Urgência U1 · Risco médio.**

[models/core.py](../../apps/api/plane/radar/models/core.py), linhas 84–89, exige `title` de até 255 caracteres e `content` HTML em todo Object. [object-page.tsx](../../apps/web/components/radar/object-page.tsx), linhas 15–81, renderiza sempre Title, Content e Save. Action/Risk possuem também propriedade `description`; Decision possui textos semânticos próprios, mantidos pelo handler especializado.

Título/UUID/version são envelopes comuns defensáveis e não indicam herança de Issue. A dívida é o layout fixo e a falta de papel explícito para content versus description/context/summary. O usuário pode manter narrativas divergentes em dois campos sem indicação de qual expressa a descrição principal. Tipos futuros como Person/Meeting/Evidence continuam recebendo a mesma página, sem metadata de apresentação/capabilities.

**Direção futura:** declarar campos principais, seções e apresentação por tipo, reutilizando a Object Page. Manter campos técnicos de identidade/versionamento no Core; não migrar automaticamente todo campo comum para EAV.

**Correção U1 fase 4 (06/10/2026):** `ObjectType.rules.presentation` declara a narrativa principal (`content` ou propriedade texto) e as seções; propriedades não listadas aparecem em "Other properties" e o layout nunca concede escrita. Sem apresentação, vale o fallback documentado (Content + Properties). Com narrativa em propriedade, `content` é rotulado como notas complementares e o conteúdo legado é preservado e sinalizado, sem cópia. Aposentar uma propriedade referenciada degrada o layout em vez de bloquear. O pacote declara apresentações para os 11 tipos (migration de dados 0014). UUID, título e versão continuam como envelope comum. [Relatório](CORE_U1_PHASE_04_REPORT.md).

### C22 — Autoria por provenance na página

**Classificação original: impacto médio · Urgência U1 · Risco médio. Status: corrigido no código em 06/10/2026.**

**Problema original:** ObjectSerializer não expunha autoria por provenance; a Object Page tratava FK User nula como `Deleted user`, inclusive em criação/edição por agente com actor conhecido.

**Implementação:** `authorship.py` fornece `created_actor/updated_actor`, tipo/ID do actor, nome humano quando disponível, user_status, fonte, timestamp e provenance_id. ObjectSerializer acrescenta os resumos e resolve humanos em lote; a UI distingue humano, agente, sistema, integração e autoria desconhecida. FKs User legadas continuam compatíveis. Identidade humana histórica sem User é distinta de falta de provenance/actor.

**Validação:** testes dos quatro actors, criação versus última edição, dados históricos e orçamento constante de queries; navegador/sessão/API/PostgreSQL confirmaram autoria de integração preservada após edição humana e reload. Ver [relatório das fases 0/1](CORE_U1_PHASE_01_REPORT.md).

**Limites:** resolução do nome humano usa cadastro atual; a identidade histórica continua no provenance. O caso sem User é validado por fixture histórica, sem ampliar/burlar os guards U0 para exclusão de usuários de produto. Não há alteração de PersonIdentity nem de seu significado.

### C23 — Navegação estática por tipo

**Impacto médio · Urgência U2 · Risco baixo.**

[sections.ts](../../apps/web/components/radar/sections.ts), linhas 8–15, enumera seções; Decisions/Risks são nomes fixos. A [rota de seção](../../apps/web/app/%28all%29/%5BworkspaceSlug%5D/%28radar%29/radar/%5Bsection%5D/page.tsx), linhas 28–42, mantém essas duas páginas como placeholders. `RadarHome` ainda contém status `Agent: not_implemented` ([home.tsx](../../apps/web/components/radar/home.tsx), linhas 29–45), embora runtime/configuração/Risk Review estejam presentes.

A lista Objects agrupa os tipos recebidos da API, o que é genérico. A navegação principal e as views por tipo não acompanham esse catálogo. Criar um tipo não cria uma view navegável configurada, e o shell expõe mensagens históricas conflitantes com o estado local.

**Direção futura:** views/navegação de tipos orientadas por metadata, separadas das entradas funcionais Today/configuração/skills. Remover placeholders somente em etapa autorizada de implementação.

**Correção C23 (07/10/2026):** sidebar/home derivam entradas de tipos ativos do catálogo; `type-<key>` abre uma lista genérica filtrada no servidor. Ferramentas funcionais conservam namespace separado. Bookmarks Decisions/Risks são aliases para views reais. Placeholders e o status fixo `Agent: not_implemented` foram removidos. Renomeação/inativação acompanha schema; tipo customizado aparece sem branch ou tela dedicada. Builder de navegação com ordenação/ocultação personalizada permanece fora desta correção. [Relatório](CORE_PENDING_REPORT.md).

## Onde Object ainda se comporta como WorkItem

Não foi encontrada dependência estrutural `Workspace → Plane Project → Issue` no Core. Os seguintes comportamentos são **semelhanças de contrato e UX**, não herança de WorkItem:

| Comportamento                                           | Evidência                | Avaliação                                                                                   |
| ------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------- |
| Formulário universal de título/descrição com Save       | C21, corrigido           | Narrativa principal e seções por tipo; content como notas quando a narrativa é propriedade. |
| Status tratado como dropdown de propriedade editável    | C01, C20, corrigidos     | Estado limitado às transições permitidas; ações governadas com preview.                     |
| Assignee/prazo/status de execução em estrutura dedicada | C18                      | Legítimo para Action; não deve se tornar estado oculto de todo Object.                      |
| Autoria antes resumida como db.User                     | C22, corrigido           | Resumo por provenance/actor entregue; FKs User permanecem para compatibilidade.             |
| Tipos conhecidos controlam formulário/rotas             | C02, C03 corrigidos; C23 | Formulário e navegação pelo catálogo entregues; views filtradas genéricas (C23).            |
| Relação de Decision com Project em input especializado  | C02                      | `project_id` é opcional e aponta a Object RADAR; não é FK nem requisito de Plane Project.   |

List layout, design system, workspace membership e rich text do Plane são reutilizações legítimas. O store [RadarRootStore](../../apps/web/store/radar/root.store.ts) não recebe Issue/Project stores. Comments/attachments são models RADAR ligados a Object, não adapters de Issue. Não há justificativa nesta auditoria para substituir essas fronteiras já isoladas.

## Metadata a explicitar nas próximas etapas

| Regra/informação                                      | Local atual                                                   | Destino conceitual                                                  | Garantia que continua em código              |
| ----------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------- |
| Campos de criação, obrigatoriedade e defaults         | C02/C03 entregues em `rules.creation` e no formulário         | Descritor de criação + PropertyDefinition                           | Validação tipada e atomicidade               |
| Estados, transições e ação que realiza cada transição | C01/C20 entregues em `rules.lifecycle` e capacidades          | Lifecycle/capability do tipo                                        | Handler com guard, evidência e autoridade    |
| Campos derivados e dependências                       | C04–C06: entregues em ObjectType.rules e engine compartilhado | Invariantes efetivos versionados; edição por builder ainda futura   | Operadores tipados; sem scripts arbitrários  |
| Efeitos compostos e necessidade de review             | C09, C17                                                      | Descritor de command/capability/policy                              | Grants, delegação e separação de aprovação   |
| Mínimo/máximo de relações e momento de validação      | C08: entregues no validador genérico e seletor                | RelationType; mínimo em transição/binding/efeitos em vinculados     | Locks, unicidade e validação de endpoints    |
| Critério de atenção do Today                          | [today.py](../../apps/api/plane/radar/today.py), linhas 26–64 | Regra de view/atenção: tipos, estados, campos, limiar `score >= 15` | Consulta somente leitura e escopo autorizado |
| Identidade externa/contexto elegível                  | C19 entregue em `rules.runtime`                               | Descritor de integração por tipo                                    | Provisioning auditado e restrição do escopo  |
| Campo principal, seções, ordem, visibilidade de UI    | C21 entregue em `rules.presentation`; navegação C23           | Metadata de apresentação/view                                       | Capacidades efetivas calculadas no servidor  |

`Risk Review` conhece deliberadamente Risk → Objective/Project, `threatens` e sugestões de Action ([risk_review.py](../../apps/api/plane/radar/risk_review.py), linhas 20–81). Isso é **especialização legítima da skill 1.5**, não motivo isolado para tornar o Core dependente desses tipos nem para ampliar a skill no 2.1. Limites de contexto, tamanho de anexo, UUIDs e versão de protocolos também são contratos técnicos legítimos; não se presume que todo literal deva virar metadata editável.

`DecisionApproval`, `ActionCompletion` e `EvidenceRecord` são registros operacionais/auditáveis específicos ([models/commands.py](../../apps/api/plane/radar/models/commands.py), linhas 111–166), não models separados de ObjectType. Sua existência não viola automaticamente o modelo genérico. A fase 3 do plano U1 registrou as capabilities e as transições que os utilizam, sem apagar histórico nem nivelar todos os tipos ao workflow de Action.

## Ativação e estado das pendências

**Entregas concluídas:** U0, fases 0–6 de U1 e C23. O aceite integrado é local, com API/PostgreSQL/commands e UI real em harness delimitado. Não equivale a homologação de produção ou entrega completa dos builders 2.2–2.6.

| Frente     | Estado                                      | Limite/próximo trabalho                                                                       |
| ---------- | ------------------------------------------- | --------------------------------------------------------------------------------------------- |
| C13/fase 6 | Corrigido; aceite integrado local           | Monitorar queries/payload/latência com volume real; provider e shell completo não homologados |
| C23        | Corrigido                                   | Ordenação/ocultação personalizada de navegação e builders completos são produto adicional     |
| C14        | Instrumentado e medido; coordenação mantida | Granularidade menor exige workload e prova de concorrência de schema/grants/replay            |

Não há achado U1 pendente. C14 é um limite U2 explicitamente mantido após a medição; não foi declarado otimizado. A migration **0017_query_page_indexes** é condição para ativar os índices no ambiente alvo, além da cadeia 0011–0016 e instalação/upgrade explícito do schema.

**Condição de ativação:** disponibilizar o app RADAR no ambiente alvo, aplicar a cadeia de migrations incluindo `0011_objecttype_rules`, `0012_workspace_schema` e `0013_type_descriptors`, verificar o baseline legado e instalar/atualizar o schema por commands administrativos explícitos; após a 0013, o upgrade explícito apenas alinha o hash do pacote. As migrations foram validadas em banco isolado; não foram aplicadas ao stack Plane em uso nem publicadas. Não há UI de builder ativada nem migração automática de fatos incompatíveis.

As fases 2 e 3 estão concluídas e validadas localmente, o que satisfaz o primeiro gate do plano para escrita dos builders. As correções do Core não constituem a entrega integral dos prompts 2.2–2.6; o aceite integrado local de U1 foi registrado na fase 6, sem ativação de ambiente publicado.

## Validação e limites

**Auditoria inicial:** os probes estáticos de 05/10 confirmaram 11 tipos/22 relações/2 invariantes, transições ordinárias para seis tipos, `commits_to=1..1`, FKs externas limitadas a Workspace/User nos models core/semantic e as lacunas originais de human-only/ORM. Não houve pytest/browser nessa etapa. As evidências históricas dos achados corrigidos não descrevem o comportamento atual.

**Entrega U0 de 06/10:** os resultados finais estão em [result.json](../../output/core-u0-20261005/result.json), com comandos e logs em [output/core-u0-20261005](../../output/core-u0-20261005/README.md). A pasta conserva a data de início do trabalho.

- Backend RADAR: **305 casos, 301 aprovados, 4 opt-in ignorados, zero falhas/erros**, incluindo **33 casos U0 novos**. Evidência: [JUnit final](../../apps/api/output/core-u0-final.xml) e [test_core_u0.py](../../apps/api/plane/radar/tests/test_core_u0.py).
- Frontend: **93 testes aprovados em 14 arquivos**, incluindo a correção do seletor de cardinalidade.
- Checks aprovados: Ruff, formatação Python, OxLint, Oxfmt, TypeScript e `makemigrations radar --check --dry-run`.
- Migration: duas invariantes normativas instaladas nos tipos legados, tipo customizado e identidades preservados; upgrade 0010 → 0011, downgrade e novo upgrade aprovados em banco descartável. Evidência: [resultado da migration](../../apps/api/output/core-u0-migration.json).

Na entrega U0, não foram reexecutados a suíte completa do Plane fora de RADAR, testes de navegador ou opt-ins de provider real/CoS. Não há benchmark novo nem confirmação de implantação. A barreira ORM tem os limites descritos em C10; o digest conservador e o downgrade têm os limites descritos em C06. Lifecycle customizado, formulário de required fields, divergência de prazos e registro de capabilities continuam pendências U1, sem alegação de cobertura integral.

**Acompanhamento U1 fases 0/1 de 06/10:** 319 backend aprovados/4 ignorados, 106 frontend aprovados, `pnpm check` 56/56 tarefas, Ruff/formatação/migrations e navegador dirigido aprovados. Relatório, limites e evidências em [CORE_U1_PHASE_01_REPORT.md](CORE_U1_PHASE_01_REPORT.md). Essas contagens e as de U0 permanecem históricas; não foram somadas à regressão da fase 2.

**Validação U1 fase 2 de 06/10:** C07/C11/C12 corrigidos e C17 parcial. Resultado consolidado em [result.json](../../output/core-u1-phase-02-20261006/result.json), comandos/logs em [evidências da fase 2](../../output/core-u1-phase-02-20261006/README.md), decisões no [ADR](CORE_U1_PHASE_02_ADR.md) e escopo/limites no [relatório](CORE_U1_PHASE_02_REPORT.md).

| Verificação              | Resultado registrado                                                                                         | Evidência                                                                                                                                                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend RADAR            | 360 casos: **356 aprovados, 4 opt-in ignorados**, zero falhas/erros; 37 casos novos                          | [JUnit final](../../apps/api/output/core-u1-phase-02-final.xml), [test_core_u1_phase02.py](../../apps/api/plane/radar/tests/test_core_u1_phase02.py), [test_agent_runtime.py](../../apps/api/plane/radar/tests/test_agent_runtime.py) |
| Transporte/CORS          | **5 aprovados** após o ajuste de cabeçalhos; reexecução sem soma ao total                                    | [JUnit de transporte](../../apps/api/output/core-u1-phase-02-transport.xml)                                                                                                                                                           |
| Frontend                 | **114 aprovados em 16 arquivos**; 8 casos novos                                                              | [Log frontend](../../output/core-u1-phase-02-20261006/frontend-final.log)                                                                                                                                                             |
| Workspace                | **56/56 tarefas** de `pnpm check`, incluindo equivalência de 11 kinds, 5 chaves de config e 3 cardinalidades | [Log de checks](../../output/core-u1-phase-02-20261006/workspace-check-final.log)                                                                                                                                                     |
| Python/schema            | Ruff e formatação aprovados; `makemigrations radar --check --dry-run` sem mudanças                           | [Evidências e comandos](../../output/core-u1-phase-02-20261006/README.md)                                                                                                                                                             |
| Migration 0012           | Ida/volta/reaplicação; IDs/fatos preservados, legado sem versão presumida, workspace vazio não inicializado  | [Resultado da migration](../../apps/api/output/core-u1-phase-02-migration.json)                                                                                                                                                       |
| Navegador/API/PostgreSQL | Schema 1 → 2 com rascunhos preservados e revisão explícita; duas escritas e reload com Object v3/schema 2    | [Prova final](../../apps/api/output/core-u1-phase-02-browser-proof-final.json), [captura após reload](../../output/core-u1-phase-02-20261006/browser-persisted.jpg)                                                                   |

O navegador usou ObjectPage, store/service/provider, sessão, API, commands, ledger e PostgreSQL reais em fixture dirigida; shell/roteamento, editor narrativo e picker de membros foram substituídos. Isso não demonstra homologação do shell completo, provider/CoS real ou ambiente publicado. A suíte Plane fora de RADAR e os 4 opt-ins reais não foram reexecutados. Não há benchmark de concorrência; C14 continua aberto. Esta atualização do audit consolida essas evidências, sem novos testes de produto ou deploy.

**Entrega 3A de 06/10:** baseline das fases anteriores reproduzida e C09/C17 concluídos. Escopo, resultados e limites em [CORE_U1_PHASE_03_REPORT.md](CORE_U1_PHASE_03_REPORT.md); comandos e logs nas [evidências](../../output/core-u1-phase-03-20261006/README.md).

**Entregas 3B/3C de 06/10:** baseline de 399 aprovados reproduzida; C02/C01 concluídos. Regressão final com **452 aprovados e 4 opt-ins ignorados** (53 casos novos) e 98 contratos dirigidos aprovados, incluindo o adapter CoS real. Frontend: 115 aprovados; `pnpm check`: 56/56; Ruff e checagem de migrations aprovados; migration 0013 com ida, volta e reaplicação em banco descartável. Escopo, resultados e limites em [CORE_U1_PHASE_03BC_REPORT.md](CORE_U1_PHASE_03BC_REPORT.md); comandos e logs nas [evidências](../../output/core-u1-phase-03bc-20261006/README.md). Não houve deploy, teste de navegador ou homologação integral de U1.

**Validação da fase 4 de 06/10:** C03/C20/C21 concluídos. Regressão final com **477 aprovados e 4 opt-ins ignorados** (25 casos novos) e 123 contratos dirigidos aprovados, incluindo o adapter CoS real. Frontend: 132 aprovados em 18 arquivos; `pnpm check`: 56/56; Ruff e checagem de migrations aprovados; migration 0014 com ida, volta e reaplicação em banco descartável. Navegador com componentes de produção sobre API, sessão, commands e PostgreSQL reais em cinco fluxos, com prova independente no banco; editor rico, seletor de membros e permissões de UI foram stubs. Escopo, resultados e limites em [CORE_U1_PHASE_04_REPORT.md](CORE_U1_PHASE_04_REPORT.md); comandos, capturas e logs nas [evidências](../../output/core-u1-phase-04-20261006/README.md). Não houve deploy nem homologação integral de U1.

**Validação 5A de 06/10:** C19 concluído. Regressão em processo novo com **516 RADAR e 2 Plane aprovados**, incluindo 38 casos novos e o adapter CoS real com transporte in-process; 3 opt-ins desativados. Frontend: 132 aprovados; `pnpm check`: 56/56; Ruff/formatação/migrations aprovados. Migration 0015 verificada por ida, volta, reaplicação e idempotência, com IDs/timestamps/fatos/opt-out preservados e upgrade sem conflitos. Contexto Plane/Telegram e capabilities consomem elegibilidade/revisão/grants do workspace. Sem deploy, provider externo ou nova prova de navegador. Escopo, reprodução e limites em [CORE_U1_PHASE_05A_REPORT.md](CORE_U1_PHASE_05A_REPORT.md) e [evidências](../../output/core-u1-phase-05a-20261006/README.md). Naquele momento, seguiam C18 (5B), C13 e homologação integrada (6); C18 foi entregue em 5B.

**Validação histórica — 5B de 06/10:** C18 concluído. Regressão final com **542 RADAR + 2 Plane aprovados**, 26 casos novos e 3 opt-ins HTTP CoS desativados; contratos dirigidos com 41 aprovados e adapter CoS real in-process. Frontend: 147 aprovados em 20 arquivos; `pnpm check`: 56/56; Ruff/formatação/migrations aprovados. Upgrade 0015→0016 e backfill revisado/idempotente verificados em banco descartável, preservando arquivo/timestamps/precisão/evidência/customizações; export verificado e reversão destrutiva bloqueada. Navegador confirmou fontes canônicas, conflitos, filtro/páginas, guest e descarte do histórico após perda de acesso, com prova independente no PostgreSQL. Inventário somente leitura do stack em uso encontrou tabela legada ausente. Sem deploy ou homologação integral. [Relatório](CORE_U1_PHASE_05B_REPORT.md), [decisões](CORE_U1_PHASE_05B_ADR.md), [evidências](../../output/core-u1-phase-05b-20261006/README.md). Naquela entrega, seguiam C13/fase 6 e C14/C23; o estado de 07/10 está registrado abaixo.

**Validação de 07/10/2026 — C13/fase 6, C23 e medição C14:** C13/C23 concluídos no código; locks conservadores observados/medidos e mantidos. Frontend: **154 aprovados**; workspace: **56/56 checks**; Ruff/formato/schema aprovados. Migration 0017 com ida/volta/reaplicação e fatos preservados. Navegador confirmou criação customizada/required, candidato fora da primeira página, relação obrigatória, lifecycle, backlinks/permissões/remoção, lista filtrada e navegação pelo catálogo; prova independente no PostgreSQL. Backend final: **557 RADAR + 2 Plane aprovados**, 3 opt-ins ignorados, 15 casos novos. Limites completos no [relatório](CORE_PENDING_REPORT.md), com [evidências reproduzíveis](../../output/core-pending-20261007/README.md). Sem deploy, provider externo ou homologação do shell completo.
