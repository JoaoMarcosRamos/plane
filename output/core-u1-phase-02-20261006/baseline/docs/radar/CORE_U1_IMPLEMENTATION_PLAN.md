# RADAR Core — Plano de correções U1

**Data:** 06/10/2026, America/Bahia. **Status:** fases 0 e 1 implementadas e validadas em 06/10/2026; fases 2–6 pendentes. [Relatório](CORE_U1_PHASE_01_REPORT.md), [decisões](CORE_U1_PHASE_01_ADR.md).

**Base:** [CORE_AUDIT.md](CORE_AUDIT.md), [entrega U0](CORE_U0_REPORT.md) e inspeção do código atual no filesystem. O worktree contém alterações anteriores; o HEAD isoladamente não representa a base analisada. Este plano cobre os **16 achados U1 originais** e preserva as garantias U0. C15, C16 e C22 foram corrigidos nas fases 0/1; permanecem **13 U1**. O plano conserva a sequência e os critérios originais para rastreabilidade.

## Análise e prioridade

O problema central é a falta de um contrato efetivo por workspace que conecte definições, criação, lifecycle, efeitos, autorização, apresentação e runtime. Persistência genérica já existe. Acrescentar campos aos formulários ou ampliar tabelas de nomes conhecidos corrigiria casos locais, mas manteria o custo de alterar vários pontos para cada tipo/capability.

A implementação deve começar por correções delimitadas e estabelecer versionamento e leitura uniforme antes de permitir mudanças de metadata pelos builders. Lifecycle e efeitos compostos são o trecho de maior complexidade: precisam preservar evidência, separação de aprovação, grants, versões, atomicidade e provenance. UI e runtime consomem esse contrato depois.

**Complexidade baixa:** mudança localizada, sem transformação de dados. **Média:** contrato entre camadas ou alteração de consultas/cache, com compatibilidade delimitada. **Alta:** nova persistência, evolução de schema ou integração com autoridade/runtime. **Muito alta:** mudança no planejamento de efeitos e execução de lifecycle, atingindo preview, aprovação e execução.

Complexidade não é urgência. A sequência abaixo considera dependências e risco; fases de UI e consultas podem ter complexidade menor mesmo vindo após o núcleo de execução. As estimativas são relativas, sem prazo em dias: migração de dados e contratos externos precisam ser dimensionados na fase 0.

| Fase | Entrega                                                 | Complexidade                 | Achados concluídos                     | Dependência                         |
| ---- | ------------------------------------------------------- | ---------------------------- | -------------------------------------- | ----------------------------------- |
| 0    | Baseline, contratos e preparação de migração            | Baixa a média                | Pré-condição                           | Nenhuma                             |
| 1    | Autoria, interfaces públicas e replay de intenções      | Baixa a média                | C22, C16, C15                          | 0                                   |
| 2    | Schema versionado e leitura uniforme                    | Alta                         | C07, C11, C12; parte estrutural de C17 | 1                                   |
| 3    | Registro de capabilities, criação e lifecycle           | Muito alta                   | C01, C02, C09, conclusão de C17        | 2                                   |
| 4    | Criação, edição e apresentação orientadas pelo contrato | Média a alta                 | C03, C20, C21                          | 3                                   |
| 5    | Identidade de runtime e fatos operacionais              | Alta                         | C19, C18                               | 3; integração visual com 4          |
| 6    | Consultas delimitadas e homologação U1                  | Média; validação transversal | C13 e aceite integrado dos 16          | Consultas após 2; aceite após 4 e 5 |

Após a fase 3, as fases 4, 5 e o trabalho de consultas da fase 6 podem avançar em frentes independentes. Isso indica dependências de implementação, sem exigir execução por múltiplos agentes.

## Contratos que orientam as correções

Os nomes abaixo são propostas para detalhamento na fase 0, não APIs já existentes.

| Contrato                         | Responsabilidade                                                                       | Limite                                                                 |
| -------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Estado de schema do workspace    | Versão do pacote instalado, revisão efetiva, origem e registro de upgrades             | Não confundir versão do seed com personalizações locais                |
| Registro de kinds e capabilities | Schema de input/config, handler, referências, efeitos e política mínima                | Metadata seleciona operadores registrados; não executa scripts         |
| Plano de efeitos                 | Objects lidos/escritos/criados, propriedades, relações, registros e eventos            | Conjunto completo alimenta versões, locks, grants, preview e aprovação |
| Snapshot semântico               | Object.version + schema_revision, valores efetivos, relações e capacidades disponíveis | Uma revisão de metadata comum às partes do snapshot                    |
| Capacidades efetivas             | Campos editáveis, transições, comandos, requisitos e razões de bloqueio                | Calculadas para actor/contexto; execução sempre revalida autoridade    |
| Descritor de apresentação        | Campo narrativo principal, seções, ordem e visibilidade                                | Não pode conceder escrita nem remover guards                           |
| Descritor de integração          | Elegibilidade, formato de identidade e capacidades publicáveis                         | Cadastro de tipo não cria grant, credential ou binding                 |

`Object.version` continua sendo a revisão dos fatos do Object. `schema_revision` muda quando definições mudam. O fingerprint de aprovação existente continua vinculando semântica e implementação, ampliado para os novos descritores. Revisão de schema não substitui o fingerprint nem representa, por si só, mudanças de membership/grants.

## Fase 0 — Preparar a implementação

**Objetivo:** fixar a base e as decisões que evitam retrabalho nas fases seguintes.

1. Registrar manifesto dos arquivos relevantes e estado das migrations. Confirmar no ambiente alvo a aplicação de `0011_objecttype_rules`; a auditoria informa validação isolada, sem ativação no stack em uso. Aplicá-la é pré-condição de ativação do código U0, não uma correção U1 nova.
2. Executar baseline RADAR em stack de testes isolado. Usar as contagens históricas de 301 backend aprovados/4 opt-in ignorados e 93 frontend apenas como referência, sem alegar nova validação.
3. Elaborar ADR curto com ownership do seed versus customizações, leitura operacional versus histórica, fontes de prazo/atribuição, narrativa principal e política de lifecycle customizado.
4. Inventariar callers das interfaces privadas, formatos de resultados/replay, consumers do catálogo do runtime e dados legados de `OperationalRecord`. Nenhuma credencial precisa ser exibida nesse inventário.

**Decisões recomendadas:** leitura operacional omite tipos inativos e recursos excluídos; leitura histórica é explícita e autorizada. Um tipo novo nasce sem transições ou capacidades de runtime implícitas. Configuração inválida é recusada com diagnóstico. Upgrades incompatíveis apresentam plano de migração e conflitos antes de modificar fatos.

**Saída:** ADR, baseline reproduzível, inventário de dados e contratos de compatibilidade. Não ativar builders com escrita enquanto fases 2 e 3 estiverem incompletas.

## Fase 1 — Correções delimitadas

**Complexidade:** C22 baixa; C16 e C15 médias. **Dependência:** fase 0.

### C22 — Autoria por actor/provenance

Expor resumos de criação e última alteração a partir de `created_provenance`/`last_provenance`, contendo tipo e identidade do actor, fonte e instante. Resolver nome humano quando disponível e manter a identidade histórica quando User não existir. Distinguir agente, sistema, integração e autoria desconhecida; `created_by=null` não permite inferir usuário excluído.

**Pontos:** [serializers.py](../../apps/api/plane/radar/api/serializers.py), [models/commands.py](../../apps/api/plane/radar/models/commands.py), [object-page.tsx](../../apps/web/components/radar/object-page.tsx) e DTOs do cliente. Reutilizar a semântica do activity existente e evitar consultas por Object na listagem.

**Aceite:** criações/edições humanas e não humanas mostram o actor correto; User removido e ausência de provenance têm fallbacks distintos; os campos legados continuam compatíveis.

### C16 — Interfaces públicas de aplicação

Extrair contratos públicos para lookup ativo, valores efetivos, membership, consulta de evidência/aprovação e resultado de command. Remover a importação de `ObjectSerializer` pelo handler e os imports de funções privadas em operations, runtime e Risk Review. O resultado usa uma estrutura de aplicação tipada; adapters HTTP fazem a representação.

**Pontos:** [handlers.py](../../apps/api/plane/radar/commands/handlers.py), [operations.py](../../apps/api/plane/radar/commands/operations.py), [execution.py](../../apps/api/plane/radar/commands/execution.py), [runtime_views.py](../../apps/api/plane/radar/api/runtime_views.py) e [risk_review.py](../../apps/api/plane/radar/risk_review.py).

**Aceite:** domínio deixa de importar serializers da API; consumers usam interfaces públicas; resultados públicos e replays históricos permanecem compatíveis. Django/DRF podem continuar na infraestrutura e na validação existente; substituir integralmente o framework não faz parte desta correção.

### C15 — Replay e intenção de retry

Classificar bootstrap interno como idempotência por estado e inicialização pública de defaults como intenção com replay. Fazer `initialize_object_properties` usar o ledger ou um caminho equivalente compartilhado, consumindo a chave já recebida. Confirmar replay antes de recusar a versão antiga de uma intenção já executada, preservando autorização atual e as regras existentes de reexecução.

Na store, criar uma intenção com chave, payload, expected_versions e reason estáveis antes do envio. Resposta incerta conserva essa intenção para retry; mudança de payload ou resolução consciente de conflito cria uma nova. A retomada de aprovação preserva a mesma intenção e o contrato já estabelecido. Não refazer automaticamente uma escrita com versões atuais após conflito. Compatibilidade Python que preenche versões continua limitada a callers confiáveis.

**Pontos:** [semantic.py](../../apps/api/plane/radar/commands/semantic.py), `execution.py`, [radar.service.ts](../../apps/web/services/radar/radar.service.ts) e [root.store.ts](../../apps/web/store/radar/root.store.ts).

**Aceite:** defaults repetidos com a mesma chave retornam resultado confirmado; commit seguido de perda de resposta e retry cria um único Object/efeito; mesma chave com input diferente gera conflito; eventos e provenance não se duplicam. Definir explicitamente se o retry atravessa reload; para suportá-lo, persistir a intenção por workspace/actor, sem credenciais.

## Fase 2 — Schema efetivo e leitura consistente

**Complexidade:** alta, com migration estrutural. **Dependência:** fase 1.

### C07 — Instalação e upgrade por workspace

Introduzir estado de instalação/revisão do schema e histórico auditado de upgrades. Separar bootstrap, upgrade do pacote e edição local. GETs operacionais deixam de instalar schema; workspace legado não inicializado recebe estado explícito e provisioning controlado.

Implementar diff entre versão instalada, configuração local e versão candidata. Atualizar apenas definições sob gestão do pacote e campos sem conflito; preservar IDs, customizações e inativação intencional. `is_system` sozinho não descreve ownership de cada campo: guardar origem/base instalada. Remoção de choices usados, mudança de kind, required sem default e redução de cardinalidade exigem verificação dos fatos e migração explícita.

**Pontos:** [ontology/schema.py](../../apps/api/plane/radar/ontology/schema.py), [snapshot.py](../../apps/api/plane/radar/ontology/snapshot.py), [primitives_objects.py](../../apps/api/plane/radar/commands/primitives_objects.py), [primitives_semantic.py](../../apps/api/plane/radar/commands/primitives_semantic.py), models e migrations.

**Aceite:** workspace novo, legado e customizado passam por instalação/upgrade idempotentes; conflitos não sobrescrevem valores; inativação é preservada; falha reverte schema, revisão e auditoria. A migration de baseline não atribui uma versão presumida a configuração divergente sem registrar essa diferença.

### C11 — Política única de recursos ativos

Centralizar consultas operacionais de Object/ObjectType, definições, relações e endpoints. Aplicar a política a lista, detalhe, snapshots, Today, Risk Review e contexto de agente. Separar APIs/consultas históricas para preservar audit trail de recursos retirados de operação, sem reutilizá-los como contexto corrente.

**Aceite:** inativar/soft-delete de tipo, definição, relação ou endpoint produz comportamento coerente em todas as superfícies. Não existe Object listado como operacional cujo detalhe semântico falhe por uma política diferente. Contexto corrente não inclui metadata inativa; histórico continua legível e autorizado.

### C12 — Revisão de metadata nos snapshots/cache

Retornar revisão efetiva em catálogo, propriedades, relações e capacidades. Alteração de metadata incrementa essa revisão atomicamente. Fazer a store comparar `(Object.version, schema_revision)` e descartar respostas antigas de catálogo/snapshot, inclusive quando terminam fora de ordem. Construir as partes do snapshot sob revisão coerente, usando a estratégia conservadora de coordenação existente.

Formulários abertos detectam revisão nova, atualizam definições/capacidades e pedem revisão dos campos afetados antes de submeter. Commands de metadata exigem revisão esperada de schema. Definir a precondição de schema para escritas feitas a partir desses formulários; não confiar apenas na validação visual. Mudanças de membership/grants também invalidam capacidades do actor e são revalidadas pelo servidor.

**Aceite:** default, choices, required, cardinalidade e apresentação podem mudar sem incremento artificial de todos os Objects; snapshots não misturam revisões; resposta atrasada não restaura metadata retirada; intenção pendente sob contrato semântico anterior fica obsoleta.

### C17 — Kinds/configuração estrutural

Criar registro único dos kinds existentes, schemas de `PropertyDefinition.config` e descritores de relações. Gerar DTOs/schemas do cliente ou validar sua equivalência em CI; manter constraints explícitas no banco e validação útil na UI.

**Aceite parcial:** metadata inválida é rejeitada antes de persistir; backend/cliente concordam sobre os kinds suportados. Registrar aliases futuros `text/string` e `url/uri`; implementar `rich_text` e `object_reference` integralmente pertence ao prompt 2.4 e não é requisito para corrigir duplicação do catálogo atual. C17 só termina com o registro de capabilities da fase 3.

## Fase 3 — Capabilities, criação e lifecycle

**Complexidade:** muito alta. **Dependência:** fase 2. Implementar em três entregas: registro/planejamento, criação, lifecycle.

### C09 e C17 — Registro e plano completo de efeitos

Consolidar a tradução de membership/roles em uma política comum, incluindo comandos de colaboração. Cada capability registrada declara input tipado, targets, referências e planner de efeitos, guard/handler e política mínima de execução/review. Gerar o catálogo anunciado pelo runtime a partir desse registro, eliminando `DEFINITIONS` paralelo.

Evoluir o planner compartilhado de propriedades U0 para abranger efeitos compostos. O mesmo plano identifica dependências lidas, Objects tocados/criados, relações, campos derivados, registros e eventos para preview, grants, versões, locks e aprovação. Planejar sob a coordenação existente, com IDs simbólicos para criações; verificar que execução não produz efeitos fora do plano. Quando uma dependência muda, replanejar e exigir revisão conforme o contrato, sem aproveitar aprovação antiga.

**Aceite:** capability nova registrada aparece nos contratos e no catálogo sem novas listas manuais; cada efeito tem autoridade e versões correspondentes; grant parcial, dependência alterada ou efeito extra recusam o command atomicamente. Metadata não pode reduzir mínimos human-only, independência de aprovador ou evidência definidos pelos handlers. Concluir C09 e C17 exige testes de paridade entre catálogo, input e execução.

### C02 — Criação por capability

Persistir descritor de criação no tipo, selecionando capability registrada. Usar propriedades/defaults efetivos do workspace e validar campos obrigatórios. Separar propriedades do Object de parâmetros de efeitos compostos, como referências de owner/evidência. Action/Risk/Decision mantêm comandos semânticos como fachadas sobre o mesmo caminho de criação/efeitos.

Eliminar o redirecionamento genérico por `ObjectType.key` em `_special_input`. Uma propriedade válida adicional em tipo semeado deve ser aceita e persistida com os efeitos semânticos obrigatórios, sem ampliar listas fechadas de serializers. O estado inicial vem do schema persistido, sujeito às restrições da capability; default incompatível é rejeitado na configuração.

**Aceite:** tipo novo e tipo semeado com propriedade extra podem ser criados; required/default funcionam; guards, relações, eventos e provenance especializados são preservados; nenhum caller pode escolher uma capability que contorne a política do tipo.

### C01 — Lifecycle declarativo limitado

Persistir estados, inicial, terminais e transições com referência a capabilities/guards registrados. Migrar `ORDINARY_TRANSITIONS` e declarar explicitamente caminhos especializados e mapeamentos de disposition em operations. Ausência de transição continua bloqueio; não completar automaticamente todos os pares de estados.

Separar transição semântica de patch livre de enum. Fields de estado protegidos usam comando de transição ou a mesma validação governada em todas as entradas. CompleteAction/ApproveDecision continuam handlers tipados com evidência e autoridade executáveis. Tipo customizado pode selecionar um perfil simples validado; workflows arbitrários permanecem fora do Type Builder mínimo.

**Aceite:** tipo customizado com lifecycle configurado faz transição autorizada sem branch Python por nome; terminal sem retorno declarado permanece terminal; lifecycle inválido é recusado; API, runtime e commands internos não escapam dos mesmos guards. Sem lifecycle, enum comum continua propriedade comum e não ganha semântica de status só pelo nome.

## Fase 4 — Experiência genérica de Rich Objects

**Complexidade:** média a alta. **Dependência:** fase 3.

### C03 — Formulário de criação por metadata

Substituir [create-object-input.ts](../../apps/web/components/radar/create-object-input.ts) por composição de PropertyDefinitions e capability de criação. Renderizar kinds já suportados, required/default, parâmetros compostos e relações necessárias. Selecionar tipo entre os elegíveis, sem default fixo `objective`. Reutilizar parsers/controles do editor, Propel e componentes Plane existentes.

**Aceite:** required sem default adicionado a tipo novo ou semeado aparece e pode ser preenchido; controles preservam tipos de valor; backend e UI concordam sobre requisitos; mudança de schema durante criação não envia formulário obsoleto silenciosamente.

### C20 — Editor por capacidades efetivas

Servidor calcula por actor/contexto campos derivados/read-only, opções/transições permitidas, comandos disponíveis, relações removíveis e requisitos de review/evidência. A UI usa essas respostas em [property-editor.tsx](../../apps/web/components/radar/property-editor.tsx) e [semantic-panel.tsx](../../apps/web/components/radar/semantic-panel.tsx). Renderizar ações governadas e formulários dos seus inputs; mapear erro de conflito, indisponibilidade e aprovação pendente.

**Aceite:** score derivado não aparece editável; estado terminal não vira opção livre; relação obrigatória/protegida tem capacidade adequada; ação disponível executa ou apresenta review com requisitos claros. API direta continua recusando toda tentativa proibida. UI distingue indisponibilidade atual de metadata inválida.

### C21 — Apresentação e narrativa principal

Adicionar descritor de apresentação validado com narrativa principal e seções. Manter UUID/title/version como envelope comum. `content`, `description`, `context` e demais textos têm papéis explícitos; se content é nota complementar, a UI o rotula assim. Evitar dois inputs que afirmem editar a mesma descrição.

**Aceite:** dois tipos com configurações distintas usam a mesma Object Page e apresentam suas seções; layout sem configuração usa fallback documentado. Dados legados divergentes permanecem preservados e recebem política explícita de reconciliação; não copiar/sobrescrever narrativas automaticamente.

## Fase 5 — Runtime e fatos operacionais

**Complexidade:** alta. **Dependência:** fase 3. Entregar C19 e C18 separadamente; a UI final integra com fase 4.

### C19 — Identidade/contexto por descritor do tipo

Persistir elegibilidade e estratégia registrada de identidade externa no schema do workspace. Substituir exigência de spec/prefix global em [runtime_control.py](../../apps/api/plane/radar/commands/runtime_control.py) e `operations._identify`. Defaults são desabilitados; provisioning cria binding explicitamente e valida formato, unicidade e contexto autorizado.

**Aceite:** tipo customizado elegível pode receber identidade e entrar no contexto autorizado sem alterar o snapshot global; tipo recém-criado não entra automaticamente. Identidades legadas não mudam; colisões, outro contexto e ausência/revogação de grant são recusados. Capabilities anunciadas e contexto usam revisão efetiva e política ativa das fases 2/3. Ajustar CoS apenas se seus testes de contrato mostrarem necessidade; não ampliar o runtime inteiro.

### C18 — Fontes canônicas e histórico operacional

Antes de migrar, fechar o ADR de prazo/atribuição e executar relatório de divergências. Recomendação: executores correntes nas relações `assigned_to`; prazo de delegação como propriedade semântica datetime, preservando a precisão de `due_at`; `due_date` legado mantém significado de data até reconciliação explícita. Today, UI e runtime consomem a mesma projeção de prazo efetivo, com fuso definido. Dois prazos simultâneos exigem distinção de negócio ou conflito identificado, sem escolha silenciosa.

Dados de aceitação, delegação, review e measurement podem continuar registros especializados, com schema tipado, revisão e invariantes. Materializar histórico em registros pagináveis, vinculados a execution/provenance, para eliminar listas ilimitadas em JSON. O registro corrente passa a uma projeção com origem definida, sem autoridade concorrente sobre propriedades/relações.

**Migração:** inventário e dry-run; backfill idempotente preservando valores, timestamps, evidências e fontes; verificação de divergências/contagens; mudança dos writers/readers para fonte canônica; retirada do writer legado após validação. Backfill é operação explícita e auditada, sem atribuir autoria original que os dados não comprovam. Evitar dual-write indefinido.

**Aceite:** delegação atrasada sem `due_date` aparece no Today; troca de executores mantém relações e projeção coerentes; retries não duplicam histórico; reviews/measurements paginam; migração não perde precisão nem evidência. Rollback de aplicação respeita compatibilidade dos dados; reversão destrutiva depende de exportação/restauração preparada.

## Fase 6 — Consultas e aceite integrado

**Complexidade:** média para C13. **Dependência:** fase 2 para consultas; fases 4/5 para homologação final.

### C13 — Detalhe e seletores com dados delimitados

Paginar/filterar a lista no servidor com ordenação estável e resumo compacto, sem content completo. A Object Page busca apenas Object, snapshots e resumos dos endpoints presentes nas relações, com paginação quando necessário. Fornecer busca paginada de candidatos por tipo, relação, direção e capability, aplicando domain/codomain, allowed_pairs, cardinalidade, estado ativo e autorização no servidor.

**Pontos:** [api/views.py](../../apps/api/plane/radar/api/views.py), [semantic_views.py](../../apps/api/plane/radar/api/semantic_views.py), `radar.service.ts`, `root.store.ts`, [semantic-utils.ts](../../apps/web/components/radar/semantic-utils.ts) e dialogs de relações.

**Aceite:** abrir detalhe não chama `listObjects` completo; candidatos válidos além da primeira página são encontrados; backlinks mostram resumos autorizados; endpoint do outro Object é carregado com versão antes da mutação. Volume de payload e quantidade de linhas lidas acompanham a página e o grau de relações, em vez do total do workspace. Medir esses limites com fixtures crescentes; estabelecer meta de latência a partir do baseline, sem inventar benchmark existente.

### Homologação dos 16 achados

Executar cenário único: criar tipo por caminho de configuração auditado, definir required/default e relação obrigatória, configurar perfil de lifecycle e apresentação, criar Object na UI, editar e transicionar com aprovação/evidência quando cabível, habilitar/provisionar runtime explicitamente e verificar contexto, autoria e provenance. Não criar model, migration, endpoint ou tela por tipo; migrations estruturais compartilhadas são permitidas.

Alterar metadata com formulário e intenção pendente abertos; confirmar invalidação, preservação de fatos, bloqueio de aprovação antiga e replay de execução já confirmada. Inativar metadata e verificar leitura operacional/histórica. Exercitar delegação/Today, paginação e resposta perdida após commit.

**Gate final:** cada achado tem evidência específica; fluxos U0 e Fase 1 não regrediram; upgrades/backfills passaram em banco descartável; contratos HTTP/CoS continuam compatíveis. Até esse gate, não declarar extensibilidade integral nem homologação de ambiente publicado.

## Rastreabilidade completa

| Achado | Complexidade | Fase de conclusão | Evidência mínima de encerramento                                            |
| ------ | ------------ | ----------------- | --------------------------------------------------------------------------- |
| C01    | Muito alta   | 3                 | Lifecycle customizado sem branch por tipo e guards preservados              |
| C02    | Alta         | 3                 | Criação de tipo semeado aceita propriedade adicional e efeitos obrigatórios |
| C03    | Média        | 4                 | UI cria com required sem default de metadata                                |
| C07    | Alta         | 2                 | Upgrade preserva customizações/inativação e detecta conflitos               |
| C09    | Muito alta   | 3                 | Membership comum e plano completo verifica autoridade de todos os efeitos   |
| C11    | Média        | 2                 | Lista, detalhe, semântica e runtime aplicam política ativa comum            |
| C12    | Alta         | 2                 | Snapshots/cache recusam revisões misturadas e respostas obsoletas           |
| C13    | Média        | 6                 | Detalhe e candidatos funcionam sem carregar o workspace inteiro             |
| C15    | Média        | 1                 | Retry de defaults/criação usa intenção estável sem duplicar efeitos         |
| C16    | Média        | 1                 | Handlers sem serializer da API; consumers sem interfaces privadas           |
| C17    | Alta         | 3                 | Registro valida config e verifica contratos backend/cliente/runtime         |
| C18    | Alta         | 5                 | Prazo/atribuição canônicos, Today coerente e histórico paginável            |
| C19    | Alta         | 5                 | Tipo customizado recebe binding explícito sem catálogo global               |
| C20    | Alta         | 4                 | UI usa capacidades efetivas e ações governadas                              |
| C21    | Média        | 4                 | Página reutilizável com narrativa/seções configuradas                       |
| C22    | Baixa        | 1                 | Resumo de actor distingue humano, agente, sistema e desconhecido            |

## Validação, rollout e limites de escopo

Cada entrega inclui unit tests no framework existente; fases de execução/migração incluem integração PostgreSQL para atomicidade, replay, versões, cardinalidade e aprovação. As fases 4–6 incluem testes de store/service/inputs e navegador nos fluxos alterados. No fechamento, repetir a regressão RADAR e testes Plane de fronteiras efetivamente tocadas; repetir testes CoS se o contrato consumidor mudar. Opt-ins reais e ambiente publicado têm evidência separada.

Comandos previstos, a executar durante implementação a partir da raiz:

```bash
docker compose -f docker-compose-test.yml run --rm --build api-tests pytest plane/radar/tests
pnpm --filter web test:radar
pnpm check
docker compose -f docker-compose-test.yml run --rm api-tests python manage.py makemigrations radar --check --dry-run
```

Aplicar também Ruff/check de formatação Python conforme a configuração do backend. Preparação e teardown do stack seguem [RUNNING_TESTS.md](../../apps/api/tests/RUNNING_TESTS.md). Não rodar setup sobrescrevendo configuração existente nem usar o stack em uso como banco de teste.

Usar migrations compatíveis por expansão e backfills verificáveis antes de retirar campos/writers. Preservar resultados antigos de `CommandExecution`, event IDs, identidades e provenance; não reescrever histórico para satisfazer o contrato novo. Para intents pendentes, mudança de código/semântica exige novo preview/review conforme a proteção U0 existente. Cada rollout registra versão, schema instalado, contagens, conflitos e estratégia de reversão.

O plano prepara os contratos necessários aos prompts [2.2–2.6](../../../DOCS_PROJETO_RADAR_COMPLETO/radar_prompts_por_fase.md), mas não equivale à entrega integral deles. Person já consta no snapshot atual; Issue/Evidence exigem decisão sobre convivência com `management_item`/Document, e Meeting precisa de configuração própria. Isso pertence à expansão de tipos. Telas completas dos builders e novos kinds do Property Builder são entregas de produto adicionais; as correções U1 exigem caminho de configuração por commands, sem escrita ORM direta.

**Fora deste plano:** C14, otimização dos locks de workspace, e C23, navegação configurável/placeholders, permanecem U2. Preservar o lock conservador durante a refatoração U1. Scripts, workflows arbitrários, rule engine geral, event sourcing completo e migração indiscriminada do envelope comum para EAV também ficam fora do escopo.

**Entrega inicial concluída:** fases 0 e 1. **Próxima entrega:** fase 2, schema efetivo e leitura consistente. **Primeiro gate para escrita dos builders:** fases 2 e 3 concluídas e validadas. **Conclusão de U1:** fases 4–6 e cenário integrado aprovados, com todos os 16 achados rastreados.
