# RADAR Core U1 — ADR da fase 4

**Data:** 06/10/2026, America/Bahia. **Escopo:** experiência genérica de Rich Objects — formulário de criação por metadata (C03), editor por capacidades efetivas (C20) e apresentação/narrativa principal (C21). Consome os contratos da fase 3 ([3A](CORE_U1_PHASE_03_ADR.md), [3B/3C](CORE_U1_PHASE_03BC_ADR.md)).

## Capacidades efetivas calculadas no servidor (C20)

`GET objects/{id}/capabilities/` devolve, para o actor humano da sessão, a revisão de schema, a versão do Object e:

- `fields`: editável/removível por propriedade, razão, opções permitidas do estado e capability que governa o campo;
- `envelope`: título/conteúdo;
- `state` e `transitions`: transições declaradas a partir do estado atual, com disponibilidade e razão;
- `actions`: capabilities oferecidas como ação da página (`object_action` no registro), com pré-preenchimento;
- `relations`: removibilidade e necessidade de review por aresta;
- `presentation`: layout efetivo (C21);
- `metadata_errors`: configuração inválida, separada de indisponibilidade corrente.

O cálculo é **consultivo**: toda escrita continua revalidada pelo command. Para não duplicar guards:

- transições por `UpdateObject` e ações com input completo (ApproveDecision com o aprovador verificado do próprio actor) são **sondadas pelo planner real** sob savepoint revertido; a falha vira razão (`approval_stale`, `not_permitted`, `requirements_not_met`);
- as restrições especializadas de edição e remoção (Decision tomada, observações de Indicator, evidência usada, histórico de aprovação/conclusão/evidência de decisão) foram extraídas de `_update`/`_unlink` para `update_restrictions` e `relation_restriction`, usadas tanto pela execução quanto pelo cálculo; as mensagens de erro foram mantidas;
- campos derivados, campo de estado e carimbos vêm dos descritores (invariantes e lifecycle).

Ações que exigem referências escolhidas pelo usuário (CompleteAction e sua evidência) aparecem como disponíveis com `requires_input` quando o lifecycle declara a transição a partir do estado atual; o command decide no envio. Transições de runtime (dispositions, delegação) aparecem como `runtime_context`, sem botão. Leitores recebem `read_only_access` sem nenhuma sondagem.

## Execução governada na UI

Ações e transições com guard seguem preencher → **Review** (preview do servidor: campos afetados e necessidade de review) → **Confirm**. A execução usa o envelope comum (`POST /commands/`), com revisão de schema e a intenção estável da store. O Object da página mantém a versão do snapshot que o usuário vê; as demais dependências usam as versões mostradas no preview revisado. Qualquer mudança desde então falha como conflito no servidor, sem rebase. Aprovação pendente é apresentada como "enviado para review, nada mudou".

A regra inicial usava versões em cache de todas as dependências carregadas; a prova de navegador mostrou que um Object tocado por um command anterior (a Person aprovadora, ao ganhar `made_by`) ficava com versão antiga na lista e gerava conflito indevido. A regra foi restrita ao Object da página.

## Criação por metadata (C03)

O diálogo deriva o formulário de `PropertyDefinition` ativas do tipo e do perfil de criação declarado (`rules.creation`):

- obrigatórios: required sem default e `required_properties` do perfil; opcionais em seção recolhível, com defaults visíveis e **não reenviados** quando inalterados;
- fora do formulário: campos derivados, o campo de estado (o inicial do lifecycle é informado) e carimbos;
- parâmetros compostos vêm do contrato do perfil; referências usam a dica `object_types` publicada pelo novo `ObjectReferenceField` dos inputs (seleção simples ou múltipla). Os handlers continuam validando o tipo;
- não há tipo padrão; um perfil ausente do catálogo torna o tipo indisponível, sem fallback;
- relações obrigatórias (1..1) são anunciadas para montagem posterior;
- os controles de propriedade são compartilhados com o editor (`RadarPropertyInput`) e a precondição de revisão de schema da fase 2 impede envio de formulário obsoleto.

## Apresentação e narrativa principal (C21)

`rules.presentation = {"narrative": "content" | <propriedade texto>, "sections": [{key, label, properties}]}` é a quarta seção fechada de `ObjectType.rules`. É apenas layout: não concede escrita nem oculta propriedades — propriedades não listadas aparecem em "Other properties".

- Validação estrita quando a apresentação é editada: narrativa `content` ou propriedade `string` ativa e não derivada; propriedades únicas, ativas e fora da narrativa; até 16 seções.
- Aposentar uma definição referenciada **não** é bloqueado pelo layout: a referência é descartada e sinalizada (`retired_references`); sem a propriedade narrativa, `content` volta a ser a narrativa. O contrato de criação da 3B continua protegendo campos de que um perfil precisa.
- Fallback documentado sem apresentação: narrativa `content` rotulada "Content" e uma seção "Properties" com todas as definições — o layout anterior.
- Com narrativa em propriedade, `content` é rotulado "Notes" como nota complementar; não há dois inputs para a mesma descrição. **Reconciliação de legado:** conteúdo existente é preservado como notas e sinalizado (`legacy_notes`); nada é copiado ou sobrescrito.
- UUID, título e versão continuam como envelope comum.

O pacote declara apresentações para os 11 tipos semeados; `0014_type_presentation` (dados) as instala de forma congelada, preserva layouts locais existentes, atualiza a base instalada e incrementa a revisão de schema. A reversão remove a seção.

## Limites

A página de lista, a navegação por tipo (C23) e os builders de tipo/lifecycle/apresentação não fazem parte desta fase. Capacidades não cobrem ainda AddEvidence com documento aninhado nem operações de runtime com contexto. O cálculo executa trabalho SQL adicional por leitura de página, proporcional às transições e ações oferecidas; não houve benchmark. A homologação integrada e o carregamento delimitado (C13) pertencem à fase 6.
