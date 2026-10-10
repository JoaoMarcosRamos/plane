# Análise do mockup UX e da integração com o RADAR atual

> **Histórico da segunda/terceira rodada.** O estado atual e o parecer revisado da quarta rodada estão em [UX_MOCKUP_REVIEW_ROUND4.md](UX_MOCKUP_REVIEW_ROUND4.md). Vários achados de UX deste documento foram corrigidos; consulte a revisão atual antes de planejar alterações.

Data: **10/10/2026**. **Revisão 2: mockup da terceira rodada**, comparado à análise anterior da segunda rodada. Escopo: código atual deste worktree, incluindo alterações ainda não commitadas. Análise de viabilidade; nenhuma implementação funcional ou alteração de ambiente foi realizada.

## Parecer

**A integração é viável e o mockup oferece uma direção de UX melhor para o gestor. A integração completa, porém, envolve trabalho no frontend e no backend.**

O visual usa a mesma infraestrutura do produto: React, MobX, Propel, Blocks, layouts genéricos do Plane e rotas no shell de workspace. O backend já dispõe de objetos, propriedades, relações, capacidades calculadas por usuário, comandos transacionais, versões, histórico e revisão humana. Essa base permite aproveitar as telas sem refazer o Core.

O trabalho principal é construir o **Interaction Model real**: projetar os dados canônicos em conceitos como combinado, retorno, próximo passo e item de atenção, e converter cada gesto em um comando válido. Trocar `RadarMockupStore` por chamadas HTTP mantendo suas regras atuais produziria falhas e resultados diferentes dos apresentados pelo mockup.

Recomendação: **avançar com integração incremental**, começando pela experiência visual e pelas leituras que os contratos atuais sustentam. A entrega integral das telas depende de decisões explícitas sobre evidências, aprovação, estados, identidade e persistência dos rituais.

## O que mudou nesta revisão

**O mockup está mais maduro como experiência.** A terceira rodada corrige a sobrecarga de Hoje, melhora a hierarquia do combinado e torna o primeiro uso demonstrável. Essas alterações reduzem trabalho de desenho da interface. Os contratos reais de aprovação, conclusão, delegação e revisão de riscos continuam com as mesmas diferenças identificadas anteriormente. O novo Desfazer acrescenta uma dependência de comandos de compensação; o onboarding acrescenta persistência e processamento de capturas em lote.

| Ponto da análise anterior                         | Situação na terceira rodada                                                    | Parecer atualizado                                                                                               |
| ------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Hoje com muitos cards e botões antes da fila      | Resultados em linhas; visões em abas; um ritual principal e menu secundário    | Melhorado substancialmente: a captura atual apresenta os seis itens de atenção na área visível                   |
| Foco separado da atenção                          | Itens focados ficam no topo da fila com selo Foco                              | Melhorado; definir contagem, expiração diária e apresentação de itens concluídos                                 |
| Painel com muitos campos de uma vez               | Autonomia, responsável, estado, prioridade e projeto passam para Mais detalhes | Melhorado; responsabilidade continua relevante e pode aparecer de forma resumida junto ao executor               |
| Verbo Decidir pouco coerente com Aprovar/Rejeitar | Decidir abre os dois resultados, com aviso de consulta pendente                | Resolvido como interação; permanece a incompatibilidade com a aprovação canônica                                 |
| Ausência de primeiro uso                          | Quatro passos: contexto, resultados, capturas e horários                       | Resolvido como demonstração; há dependências e lacunas para novos usuários sem vault                             |
| Configurações apenas mostrava toast               | Menu permite simular primeiro uso e restaurar exemplos                         | Achado anterior atualizado; configuração real do agente continua fora desse menu                                 |
| Reversibilidade das ações                         | Toast Desfazer com janela de dez segundos                                      | Acrescentada ao mockup; restauração global é inadequada como mecanismo do produto e apaga alterações posteriores |
| Integração com API e persistência                 | Continua store local, dados fictícios e data fixa                              | Não resolvido nesta rodada; não houve integração funcional com o backend                                         |

Não transportar o diagnóstico visual da segunda rodada como se ainda descrevesse a tela atual. A densidade de Hoje e do painel foi efetivamente reduzida.

## Evidência e limites da revisão

- Inspecionados: componentes e store dos mockups; componentes, serviços e stores reais; contratos de comandos; projeção Today; schema Core 3.2.0 e comportamento padrão instalado pelo pacote.
- Nesta revisão, inspecionadas visualmente seis capturas da terceira rodada: Hoje, Combinado, Decidir, primeiro uso, Hoje após primeiro uso e Desfazer. A revisão anterior também inspecionou Projetos, Inbox, Pessoas, revisão semanal e captura. São imagens existentes do preview, não capturas novas do shell autenticado.
- Consultada a visão de UX em `DOCS_PROJETO_RADAR_COMPLETO/RADAR_UX_VIEW`, que já prevê uma camada intermediária entre ontologia e interface.
- Reexecutado `pnpm --filter web test:radar`: **178 testes aprovados em 23 arquivos**, incluindo os 19 testes de lógica dos mockups. A terceira rodada acrescentou cobertura para ritual por hora, checkpoint e primeiro uso.
- Executadas quatro verificações diagnósticas temporárias, fora do repositório, sobre o store/helper atual: restauração antiga apaga captura posterior; foco mantém item concluído; abrir o dia não atualiza a data de revisão; sexta-feira continua indicando revisão mesmo após revisão no mesmo dia. As quatro passaram, confirmando os comportamentos descritos, não sua correção.
- Reexecutado `pnpm --filter web check:types`: **aprovado**, com avisos de tooling sobre `vite-tsconfig-paths` e tipo de módulo do PostCSS.
- Não reexecutados: backend, CoS, build completo, E2E autenticado, testes mobile/teclado e ambiente do piloto. Evidências anteriores de E2E não homologam as novas telas.
- O catálogo efetivo pode ter customizações por workspace. Os limites de estados e propriedades abaixo descrevem o pacote padrão e os contratos no código; uma implementação deve consultar `/schema/` e as capacidades do objeto.

Referência dos mockups: [README da entrega](../../output/ux-mockups-20261008/README.md).

## Avaliação da experiência

### O que vale preservar

1. **Navegação pelo trabalho do gestor.** Hoje, Inbox, Projetos e Pessoas são entradas mais próximas da rotina que a navegação por tipos internos. As páginas genéricas continuam úteis como acesso secundário e fallback.
2. **Contexto sem sair da fila.** O painel lateral permite decidir, cobrar e editar mantendo o item de origem à vista. A geometria segue o peek do Plane e evita criar outro sistema de componentes.
3. **Responsabilidade e execução separadas.** “Responde” e “Executa” traduzem `owned_by` e `assigned_to`. Isso ajuda a acompanhar delegações sem atribuir responsabilidade final ao executor.
4. **Prazo e retorno separados.** A distinção é consistente com os termos de delegação já persistidos no backend.
5. **Resultado esperado e próxima ação no projeto.** A tela melhora a leitura gerencial ao mostrar entrega e continuidade, sem tratar percentual de tarefas concluídas como resultado do negócio.
6. **Captura de baixa fricção e estrutura corrigível.** Uma frase, sugestões visíveis e uma pergunta de lacuna são boas escolhas. O usuário deve poder corrigir qualquer campo inferido antes de um efeito significativo.

### Ajustes antes de uso real

- Hoje ficou mais compacto: resultados em linhas e visões em abas trazem a fila para cima. Validar o critério de reconhecimento do resultado, agora truncado em uma única linha, com texto completo acessível por expansão, tooltip ou revisão.
- Os avisos de ausência de executor, prazo ou próxima ação são úteis. Devem distinguir **dado ausente**, **dado ainda não carregado** e **fato confirmado**. Uma consulta incompleta não pode gerar “Projeto travado” ou “Nada pendente”.
- “Copiar e marcar como consultado/comunicado” mistura preparação de mensagem com ocorrência do fato. Separar “Copiar mensagem” de “Registrar que consultei/comuniquei”, com data, autor e, quando necessário, evidência.
- A página Pessoas oferece uma visão útil da distribuição do trabalho. Contagem de itens não equivale à capacidade disponível: a revisão semanal deve apresentá-la como carga registrada, sem presumir esforço ou disponibilidade.
- A sidebar do mockup fica oculta abaixo de `md`, sem navegação alternativa dentro desse shell. O painel lateral é um `aside` customizado, sem lógica explícita de mover/restaurar foco. Validar acesso mobile, teclado e a interação com diálogos antes de promover a tela.
- O item aberto vive apenas em `openItemId`. Para produção, usar URL ou parâmetro do peek para permitir reload, link direto e Voltar do navegador.
- Busca continua mostrando toast. Configurações agora contém simulação de primeiro uso e restauração dos exemplos. Na integração, preservar acesso à configuração real do agente e separar controles de demonstração de operações do usuário; a busca pode começar pela consulta por título já existente.

## O que existe de verdade hoje

| Base             | Implementação disponível                                                      | Consequência                                                                                        |
| ---------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Shell e rotas    | Grupos `(radar)` e `(radar-mockups)` como irmãos no workspace                 | O mockup já tem encaixe de rota, mas seu layout não recebe o provider real automaticamente          |
| Dados e metadata | `RadarRootStore`, `RadarService`, catálogo de schema, propriedades e relações | Reutilizar identidade, cache, revisão de schema e controle de versão                                |
| Ações permitidas | `/objects/:id/capabilities/`, contratos e previews de comandos                | Botões e transições devem vir dessas capacidades; `verbsFor` sozinho não autoriza nada              |
| Today            | Quatro filas persistidas: riscos, decisões, prazos e sugestões                | Pode alimentar a primeira versão do novo Hoje; não contém as cinco visões relacionais               |
| Histórico        | Colaboração, provenance e histórico operacional tipado/paginado               | Pode alimentar detalhes e eventos; não confundir usuário autor com objeto Person executor           |
| Delegação        | `DelegateAction`, executores, `due_at`, `next_review_at`, termos propostos    | Retorno e executores têm fonte canônica; confirmação ainda precisa de um caminho de escrita próprio |
| Agente           | Binding, contexto, execução, estados e revisão de riscos                      | O botão “Revisar riscos” pode ser real usando o fluxo existente                                     |
| Revisão humana   | Propostas com hash de intenção, versões, rationale, Accept/Edit/Reject        | A Inbox pode apresentar essas propostas preservando os contratos atuais                             |

Fontes principais: [provider](../../apps/web/store/radar/provider.tsx), [root store](../../apps/web/store/radar/root.store.ts), [serviço](../../apps/web/services/radar/radar.service.ts), [capacidades e tipos](../../apps/web/services/radar/types.ts), [Today backend](../../apps/api/plane/radar/today.py).

## Viabilidade por tela e comportamento

“Alta” significa que o código atual já contém os dados ou o fluxo central. Ainda exige implementação, tratamento de falha e validação integrada.

| Área                                             | Viabilidade                                                     | Reaproveitamento                                                         | Trabalho faltante                                                                                 |
| ------------------------------------------------ | --------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Sidebar, cabeçalhos e visual das listas          | Alta                                                            | Propel, Blocks, navegação e layouts atuais                               | Encaixar provider real; preservar rotas atuais; navegação mobile                                  |
| Painel lateral de item                           | Alta para leitura; parcial para verbos                          | Object Page, semântica, colaboração, operações e capacidades             | Extrair conteúdo reutilizável, carregar snapshots reais e colocar o peek na URL                   |
| Hoje: atenção atual                              | Alta                                                            | `getToday` e `RadarTodayStore`                                           | Adaptar apresentação sem eliminar filas e conflitos existentes                                    |
| Hoje: Fazer/Decidir/Aguardando                   | Média                                                           | Relações e termos de delegação                                           | Identidade do usuário → Person, filtros, agregação e paginação                                    |
| Hoje: Consultar/Informar                         | Parcial                                                         | Obrigações `requires_consultation`/`requires_notification`               | Registro persistido dos fatos ocorridos, não apenas arrays locais                                 |
| Projetos: contexto, itens, riscos e próxima ação | Média/alta                                                      | Objetos Project; `contains`, `threatens`, `advances`, propriedades       | Agregar relações; definir próxima ação executável e lidar com múltiplos projetos                  |
| Projetos: medidor de resultado                   | Parcial                                                         | Objective.outcome e dados de Indicator                                   | Definir qual indicador representa qual resultado; faltam bindings inequívocos na forma do mockup  |
| Pessoas: trabalho por executor/responsável       | Média/alta                                                      | Person, `assigned_to`, `owned_by`, consultas e notificações              | Agregação; separar Person de workspace member; metadados para equipe/externa/organização          |
| Inbox: sugestões existentes                      | Alta com ajuste do conteúdo                                     | Risk Review real                                                         | Mostrar relações e ações reais, com evidências, edição e revisão de versões                       |
| Inbox: entradas manuais                          | Parcial                                                         | ManagementItem e `CaptureIssue`                                          | Fluxo de triagem, conversão/vínculo a objetos, revisão futura e arquivamento com motivo           |
| Inbox: reunião/e-mail/integrações                | Baixa no escopo atual                                           | Nenhum pipeline correspondente encontrado nas telas/contratos atuais     | Ingestão/extrator/proveniência; não tratar fixtures como fontes disponíveis                       |
| Captura de uma frase                             | Média para rascunho/entrada                                     | Heurística local e criação de ManagementItem                             | Adaptar tipos obrigatórios; não criar decisão estruturada incompleta                              |
| Primeiro uso                                     | Média para contexto e captura; parcial para resultados/horários | Importador do vault, Person/Project, criação e heurística                | Detectar primeiro uso, aceitar usuário sem vault, persistir progresso e garantir retry por linha  |
| Desfazer                                         | Parcial                                                         | Versões, provenance e Command Layer                                      | Compensação específica por ação; há operações sem inversa permitida no contrato atual             |
| Abrir/fechar dia, foco e amanhã                  | Parcial                                                         | Dados para parte da fila e comandos já existentes                        | Persistência por usuário/workspace/data e verbos ausentes                                         |
| Revisão semanal, resultados e diário             | Parcial                                                         | Objective, histórico, dados de risco/ação; runtime com `context_summary` | Snapshot semanal, seleção de resultados, respostas, vínculo de evidências e consulta das revisões |

## Incompatibilidades que precisam ser resolvidas

### 1. Aprovar no mockup não é o fluxo de aprovação atual

O novo botão **Decidir** abre corretamente a escolha entre Aprovar e Rejeitar. O aviso sobre consulta pendente também ficou contextual. Porém, `run(..., "approve")` ainda muda diretamente o status para `decided`, aceitando justificativa opcional. No backend, `ApproveDecision` exige humano, Person verificado com `can_approve`, proposta completa, evidências e aprovador independente do autor. O comando registra a aprovação; a transição para `decided` é governada pelo guard `decision_approval`.

**Implicação:** no piloto individual, uma decisão criada pelo próprio gestor não pode ser aprovada por ele nesse fluxo. A UX precisa mostrar a condição real. Se o produto quer permitir “tomar minha própria decisão”, isso exige revisar o contrato de negócio; renomear o botão não resolve.

Fontes: [handler de aprovação](../../apps/api/plane/radar/commands/handlers.py), [lifecycle padrão](../../apps/api/plane/radar/ontology/package.py).

### 2. Concluir e reabrir não são alterações livres de status

O mockup aceita uma nota ou uma confirmação gerada localmente como evidência e muda para `done`. `CompleteAction` exige `outcome` e `evidence_id` de um Document válido. O backend grava snapshot e relação `verifies`, e impede completar novamente ou reabrir uma ação já concluída.

**Caminho viável:** uma interação curta pode registrar uma evidência proporcional como Document e executar o comando de conclusão. Os contratos existentes permitem adicionar evidência e concluir, mas não oferecem um único gesto transacional “criar evidência e concluir” pronto. Um comando composto seria necessário se o requisito for tudo ou nada.

O Kanban do mockup também chama `setStatus` ao arrastar. Em produção, um drop em Concluído deve abrir o fluxo de evidência/aprovação exigido pela capacidade, ou ser recusado. Mover para Planejado não pode reabrir silenciosamente.

Fontes: [CompleteActionInput](../../apps/api/plane/radar/commands/inputs.py), [conclusão](../../apps/api/plane/radar/commands/handlers.py), [drop do mockup](../../apps/web/components/radar/mockups/projects-screen.tsx).

### 3. Estados da UX diferem do vocabulário e do lifecycle padrão

- `blocked` não existe como estado de Action. “Bloqueado” pode ser uma projeção de `waiting` mais um motivo persistido; `blockedReason` não é propriedade padrão. Não se deve classificar qualquer `waiting` como bloqueado.
- `rejected` não existe em Decision: o Core possui `proposed`, `decided`, `superseded`, `revoked`. Rejeitar uma sugestão do agente e rejeitar uma proposta de decisão são atos diferentes. Mapear automaticamente para `revoked` mudaria o significado.
- Action possui `cancelled` no vocabulário, mas o lifecycle padrão não declara uma transição para ele. ManagementItem também tem estados de triagem no vocabulário que o lifecycle padrão não disponibiliza como movimentos livres.
- `isOpen` considera Risk `accepted` encerrado. O Core só considera `closed` terminal, e Today mantém riscos aceitos relevantes na atenção. Transportar essa regra esconderia riscos ainda sujeitos a acompanhamento.
- O mockup usa `decided` como fechado para a fila de trabalho. Isso pode ser uma boa projeção, mas não deve substituir o terminal canônico de cada tipo.

**Regra de integração:** distinguir “encerrado para esta visão” de “terminal no Core” e respeitar transições calculadas pelo servidor.

Fontes: [regras locais](../../apps/web/components/radar/mockups/interaction-model.ts), [schema](../../apps/api/plane/radar/ontology/core-3.2.0.json), [lifecycle](../../apps/api/plane/radar/ontology/package.py).

### 4. A atenção do mockup não preserva toda a atenção atual

No mockup, decisão entra em Atenção apenas com prazo em até sete dias. Decision não tem `due_date` no schema padrão. A adaptação direta faria decisões propostas sem prazo desaparecerem da atenção. Today atual inclui todas as propostas.

Além disso, o mockup reduz o prazo a uma data; o backend atual distingue `due_date`, `due_at`, prazo vencido e **conflito entre fontes de prazo**. Hoje e Adiar devem usar a projeção operacional canônica, preservar o horário quando aplicável e manter conflitos visíveis.

**Caminho:** manter as filas atuais como base e acrescentar retorno, bloqueio e visões pessoais por contrato explícito. Se decisões precisam de prazo, definir sua persistência em metadata de workspace ou estado de interação versionado.

Fontes: [attentionFor](../../apps/web/components/radar/mockups/interaction-model.ts), [Today real](../../apps/api/plane/radar/today.py), [tipos operacionais](../../apps/web/services/radar/operational.types.ts).

### 5. Delegar tem base real; confirmar ainda não tem o fluxo apresentado

`DelegateAction` já persiste executores, prazo com fuso, próximo retorno e termos em estado `proposed`. Exige contexto e identidades explícitas para suas referências, além da autoridade do responsável ou gestor configurado. Não é somente editar `assigned_to`.

O histórico aceita dados tipados de confirmação, inclusive preservados pelo backfill. Porém, o registro de capabilities inspecionado não oferece um comando de aceite do executor correspondente ao novo botão “Registrar confirmação”. **Estrutura de armazenamento não equivale a fluxo de produto disponível.** A troca de rótulo melhora a clareza, mas não acrescenta o caminho de escrita.

O mockup ainda registra a confirmação atribuindo a atividade ao Person executor, embora o clique seja do gestor. A implementação precisa distinguir “executor confirmou autenticado” de “gestor registrou uma confirmação recebida”, com autor real e fonte. `autonomy` também não possui campo padrão.

Fontes: [delegação](../../apps/api/plane/radar/commands/operations.py), [registro de capabilities](../../apps/api/plane/radar/commands/capabilities.py), [store local](../../apps/web/components/radar/mockups/mockup.store.ts).

### 6. A revisão de riscos real entrega outro tipo de sugestão

O mockup cria um novo risco e, opcionalmente, uma ação; “Aceitar as duas” altera ambos localmente. O Risk Review atual produz propostas de `LinkObjects` para uma relação `threatens` entre objetos existentes, e de `CreateAction` para mitigação. Não propõe `RegisterRisk` nesse contrato.

**Caminho mais curto:** apresentar as propostas reais na Inbox, mantendo Accept/Edit/Reject, rationale, evidências, intenção e versões. Para sugerir riscos novos, será necessário ampliar skill/contrato CoS, fachada Plane, grants e revisão humana. Aceitar dois componentes também não garante atomicidade entre duas resoluções HTTP.

`reviewProjectRisks` é uma simulação local; a tela espera 1,4 segundo e cria uma fixture. A versão real deve usar os estados de execução do runtime e tratar indisponibilidade, ausência de binding, timeout, falha e contexto truncado.

Fontes: [tipos reais de proposta](../../apps/web/services/radar/risk-review.types.ts), [service](../../apps/web/services/radar/radar.service.ts), [simulação](../../apps/web/components/radar/mockups/mockup.store.ts).

### 7. Captura e triagem precisam preservar entrada, fonte e campos obrigatórios

`parseCapture` é uma heurística determinística por regex, nomes e palavras-chave, não um modelo de IA. Isso é aceitável para oferecer sugestões, mas precisa de calendário real, validação de datas e desambiguação de pessoas/projetos.

Uma frase reconhecida como Decision não contém necessariamente `context`, `decision` e `rationale`, exigidos na criação real. Um score isolado de risco também não substitui `likelihood × impact`, que é derivado pelo Core.

O Core já possui ManagementItem para a entrada ainda não estruturada. `CaptureIssue` cria Case, ManagementItem e Document com origem, mas depende de contexto/runtime. Uma captura mínima pode começar como ManagementItem e converter depois por um fluxo explicitamente definido.

Na Inbox local, Assumir remove a entrada e cria outro item. A versão persistida deve preservar fonte, histórico e vínculo com o item derivado, evitando perder a entrada quando a criação falhar. “Revisar em” tem `next_review` como base, porém referência/recusa/arquivamento e conversão não têm o workflow completo demonstrado.

Fontes: [parser](../../apps/web/components/radar/mockups/interaction-model.ts), [inputs](../../apps/api/plane/radar/commands/inputs.py), [triagem local](../../apps/web/components/radar/mockups/mockup.store.ts).

### 8. Relações do mockup simplificam ou extrapolam o Core

- `projectId` é único no mockup; o Core associa itens por relações e pode admitir associação a mais de um projeto. Para riscos, `threatens` também expressa relação com projetos/objetivos, sem equivaler automaticamente a contenção.
- O fixture da ação “Atualizar o cronograma da mobilização” depende de uma Decision. O `depends_on` padrão aceita Objective, ManagementItem e Action nas duas pontas, **não Decision**. A relação `blocks` padrão tem ManagementItem como origem. Esse exemplo exige outro encadeamento válido ou evolução explícita da metadata.
- Project não tem diretamente `result`, `objective` ou uma medida selecionada. Objective e Indicator fornecem partes dos dados, mas a projeção precisa resolver relações como `advances` e escolher qual indicador representa o resultado mostrado.
- Person contém `role`, `team`, `email` e `timezone`. `affiliation` e `organization` não são propriedades padrão. Não presumir que pessoa externa é usuário do workspace ou que ausência de login define sua filiação.

Fontes: [schema](../../apps/api/plane/radar/ontology/core-3.2.0.json), [dados locais](../../apps/web/components/radar/mockups/mock-data.ts).

### 9. “Sem notícias” e “próxima ação” precisam de critérios mais fortes

`silentDays` busca atividade do executor e, se não encontra, usa atividade de qualquer autor. Uma edição recente do gestor pode, assim, fazer desaparecer a ausência de retorno. O backend usa IDs de usuário/actor na autoria e IDs de Person nas relações: o pareamento exige identidade verificada, não comparação direta de strings.

`projectNextAction` escolhe a Action `todo`/`in_progress` com menor prazo sem validar dependências, próximo passo preenchido ou confirmação de execução. O diagnóstico deve distinguir “não encontramos próxima ação registrada” de “projeto comprovadamente parado”.

Na revisão semanal, `doneThisWeek` seleciona itens fechados com qualquer atividade recente; isso não prova que a conclusão ocorreu na semana. Usar `completed_at`, eventos de conclusão/decisão e evidências correspondentes.

Fontes: [silentDays](../../apps/web/components/radar/mockups/interaction-model.ts), [projectNextAction](../../apps/web/components/radar/mockups/interaction-model.ts), [revisão](../../apps/web/components/radar/mockups/review-screen.tsx).

### 10. Persistência dos rituais e agregações é trabalho adicional

Focos, resultados da semana, primeiro item de amanhã, última revisão e diário vivem em memória. `saveWeeklyReview` substitui os resultados pela próxima semana e não conserva um snapshot dos anteriores; o parâmetro `states` recebido não é usado para arquivar a revisão.

É necessário estado persistido por **workspace + usuário + período**, com versão e histórico. Preferências efêmeras de abertura de painel podem ficar no frontend; diário e resultados não devem depender de localStorage como registro principal.

As consultas genéricas de objetos retornam por padrão 50 registros, máximo 100 por página; relações e histórico também têm paginação. Carregar todos os objetos e depois fazer um request de propriedades/relações para cada um seria caro e produziria contadores incompletos se algum cursor fosse ignorado.

**Caminho:** projeções agregadas no backend para Hoje, Projetos e Pessoas, com consultas em lote, contadores completos e páginas de itens. O Today já mostra esse padrão com propriedades em lote. Carregar semântica detalhada somente ao abrir o item.

Fontes: [rituais locais](../../apps/web/components/radar/mockups/mockup.store.ts), [paginação](../../apps/api/plane/radar/api/pagination.py), [consulta de objetos](../../apps/api/plane/radar/api/object_queries.py).

### 11. Desfazer restaura estado global e não equivale a um comando inverso

`checkpoint()` guarda items, inbox, references, weekResults, feedback, focusIds e tomorrowFirstId. `withUndo()` executa a mudança, cria toast e oferece restaurar esse snapshot por dez segundos. É uma demonstração de reversibilidade, mas não isola o efeito que se pretende desfazer.

**Caso reproduzido:** criar checkpoint → iniciar uma ação A → capturar um item B → restaurar checkpoint. A volta ao estado anterior e **B desaparece**, embora B não pertença à ação A. O teste atual de undo também restaura a exclusão de uma entrada feita depois do checkpoint, confirmando o escopo global deliberado. Vários toasts ativos deixam o usuário desfazer snapshots antigos em qualquer ordem.

Para produção, cada inversa precisa apontar para o comando original e revalidar versões, dependências e autoridade. Exemplos:

| Operação                    | Política viável de reversibilidade                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Editar um prazo/campo comum | Compensar somente o campo alterado se a versão/valor ainda permite; manter histórico                                     |
| Iniciar ou retomar          | Verificar se existe transição inversa válida; o lifecycle padrão não oferece todas as inversas                           |
| Concluir ou aprovar         | Não prometer undo universal: conclusão não pode ser reaberta no contrato atual; aprovação tem registro e guarda próprios |
| Delegar                     | Reverter executores/termos como novo ato governado, sem ressuscitar confirmações invalidadas automaticamente             |
| Aceitar sugestão            | Compensar efeitos e dependências do comando executado; não remover silenciosamente provenance/aprovação                  |
| Copiar mensagem             | O conteúdo já copiado ou comunicado externamente não é revertido pelo estado do RADAR                                    |

Se o produto quiser uma janela de cancelamento antes de executar uma ação, essa é outra alternativa que exige estado explícito de pendência e execução idempotente após a janela. Não mostrar sucesso persistido antes da confirmação do servidor.

A cobertura visual também não é universal: o drop no Kanban, o seletor de estado, as edições de propriedades e “Descartar o restante” dos candidatos de reunião não usam `withUndo`. O README deve ser entendido como descrição dos fluxos cobertos, não garantia de reversibilidade para qualquer gesto.

Fontes: [checkpoint/restore](../../apps/web/components/radar/mockups/mockup.store.ts), [withUndo](../../apps/web/components/radar/mockups/ui.tsx), [drop](../../apps/web/components/radar/mockups/projects-screen.tsx), [descartar candidatos](../../apps/web/components/radar/mockups/inbox-screen.tsx).

### 12. Horários e marcadores dos rituais ainda não estão conectados

O primeiro uso salva `ritualTimes` em memória, mas `RitualControl` chama `ritualFor(new Date().getHours(), lastReview)` sem usar essas preferências. A regra continua: abrir antes de 12h, fechar a partir de 15h, revisar semanalmente após sete dias ou na sexta à tarde. Escolher “seg 08:30” para revisão não altera essa regra. “Reservado” apenas muda um booleano local; não cria compromisso de calendário nem lembrete.

O helper considera revisão pendente em toda sexta-feira, mesmo com `lastReview` igual à própria sexta-feira; esse caso foi reproduzido. `lastReview` só muda ao salvar a revisão semanal. Abrir/fechar o dia não o atualiza, então a faixa “Você não revisa desde…” pode continuar acusando três dias sem revisão apesar de uso diário. Separar última revisão diária, última semanal, horários preferidos e último uso relevante.

Focos também não carregam data. Um item concluído permanece em `focusItems`, e o botão Abrir o dia some pela simples existência de IDs de foco. Esse comportamento foi reproduzido; para produção, definir foco por dia e distinguir foco cumprido de pendência crítica. O contador de Atenção usa `hoje.attention.length`, mas a fila soma focos fora dessa atenção, então pode mostrar mais linhas que o número da aba. Isso pede uma distinção explícita entre focos e alertas, ou uma contagem da união.

Fontes: [ritualFor](../../apps/web/components/radar/mockups/interaction-model.ts), [RitualControl e fila](../../apps/web/components/radar/mockups/today-screen.tsx), [ritualTimes e foco](../../apps/web/components/radar/mockups/mockup.store.ts), [diálogos](../../apps/web/components/radar/mockups/rituals.tsx).

### 13. Primeiro uso aproxima o mockup do piloto, com dependências próprias

O novo fluxo resolve uma lacuna relevante de adoção: parte do contexto importado e transforma pendências em trabalho. A integração pode reutilizar o importador do vault e os contratos de criação. Porém:

- O acesso é uma simulação no menu, não detecção automática de primeiro uso persistido.
- A tela pressupõe pessoas e projetos vindos do vault; oferecer também caminho para quem ainda não tem dados ou importação.
- O preview de captura em lote informa tipo/data/pessoa, mas não oferece correção inline antes de “Organizar”. Cada linha ainda pode criar uma decisão sem os campos obrigatórios ou um risco sem sua avaliação canônica.
- `captureMany` processa todas as linhas localmente. No backend, cada linha precisa de identificador de intenção estável, resultado individual e retry que não duplique itens; decidir se a operação inteira é transacional ou admite sucesso parcial.
- Conferência de contexto, linhas capturadas e “Reservado” são estados locais do componente; voltar depois não restaura o progresso declarado na tela. Resultados e horários também não sobrevivem a reload.
- A etapa semanal exige só título; `howWeKnow` pode virar “a confirmar”. É válido como rascunho, mas a interface deve manter visível essa lacuna.
- O comando de demonstração `startFresh` esvazia arrays locais. No produto, “começar” precisa apenas abrir o onboarding; não deve apagar dados importados/existentes.

Fontes: [primeiro uso](../../apps/web/components/radar/mockups/first-use.tsx), [captura em lote e simulação](../../apps/web/components/radar/mockups/mockup.store.ts), [importador real](../../apps/api/plane/radar/vault_import.py).

## Arquitetura de integração recomendada

Fluxo de leitura: **API Plane → projeções de interação → store MobX por workspace/sessão → telas**.

Fluxo de escrita: **gesto → capacidade disponível → preview quando necessário → Command Layer → confirmação do servidor → atualização das projeções**.

1. **Conservar a base real.** `RadarStoreProvider` já recria os stores ao trocar usuário/workspace e revisa a autoridade/schema. A nova experiência deve herdar esse comportamento.
2. **Criar modelos de apresentação tipados.** Um item deve carregar ID e tipo canônicos, versão, revisão de schema, papel da pessoa, prazo/retorno com origem, fontes dos sinais e ações disponíveis. Evitar outro modelo de domínio editável em paralelo.
3. **Separar projeção de autoridade.** Labels como “Combinado” podem ser estáticos; estados editáveis e verbos disponíveis dependem do catálogo e das capacidades atuais. Tipos customizados precisam de fallback para Object Page.
4. **Resolver a identidade pessoal no servidor.** O mockup fixa `ME_ID`; a sessão real usa User e o domínio usa Person. A API existente de `person-identities` permite configuração via POST, mas falta uma leitura dedicada da identidade pessoal para alimentar “Meu” sem depender de agente. Não inferir por nome/email.
5. **Reaproveitar o conteúdo da Object Page no peek.** Semântica, colaboração, operações e ações reais podem formar um corpo compartilhado, com wrappers de página completa e painel lateral.
6. **Centralizar efeitos compostos.** Delegar, concluir com nova evidência, converter entrada e registrar consulta são intenções de negócio. Quando precisarem atomicidade, implementá-las como capabilities transacionais; não como cadeias de mutações independentes no browser.
7. **Tratar resultados assíncronos.** Distinguir salvando, salvo, pendente de revisão, conflito, erro e sem permissão. Mostrar sucesso após persistência real; revalidar visões afetadas. A idempotência existente deve cobrir retry/double-click.
8. **Preservar origem e autoria.** Histórico vem de provenance e colaboração reais; quantidade de atividades não é `object.version`. No mockup, os detalhes afirmam “Command Layer · proveniência registrada” mesmo sem API; essa frase deve ser substituída por dados efetivos na versão integrada.

Sugestões de projeções de leitura são desenho proposto, **não endpoints existentes**: um Hoje expandido com escopo pessoal/equipe e visões, uma listagem gerencial de projetos e uma agregação de pessoas. Podem ser incrementos do endpoint atual ou endpoints separados conforme custo e política de acesso.

## Sequência sugerida

| Etapa | Entrega concreta                                                                            | Dependências e limite                                                            |
| ----- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 1     | Nova apresentação de Hoje, sidebar e peek de leitura; acesso à configuração e revisão reais | APIs existentes; manter filas atuais, links e comportamento de erro              |
| 2     | Projetos/Pessoas reais; Fazer/Decidir/Aguardando; captura mínima como entrada               | Projeções em lote, identidade User→Person, regra de associação dos itens         |
| 3     | Verbos existentes no painel: iniciar/retomar, delegar, revisar, concluir e aprovar          | Capacidades reais, evidência e bindings; mostrar bloqueios legítimos da operação |
| 4     | Consulta/comunicação, confirmação recebida, bloqueio e triagem completa                     | Novos registros/comandos ou metadata explícita, com autoria e auditoria          |
| 5     | Foco diário, resultados semanais, revisão e diário persistidos                              | Estado versionado por usuário/período e snapshots históricos                     |

Na etapa 2, incluir um primeiro uso mínimo real: reconhecer o contexto disponível e capturar pendências como entradas persistidas, com resultado por linha. Os resultados semanais e horários avançados entram quando houver persistência correspondente. Na etapa 3, apresentar Desfazer somente para operações cuja inversa seja suportada; concluir/aprovar continuam com revisão e confirmação compatíveis com o Core.

Sugestões de riscos novos e extração de reuniões/integrações são expansões próprias do produto/agente. Não são pré-requisitos para integrar as primeiras telas.

O [plano do piloto](PILOT_PLAN.md) registra congelamento de novas fases e permite corrigir o que impede ou distorce o uso. Portanto, começar pela etapa 1 e pelas necessidades comprovadas do piloto é coerente com a estratégia registrada. Esta análise não altera esse plano nem autoriza mudanças de ambiente.

Não há base para prometer prazo fechado ou porcentagem de reaproveitamento: o resultado depende de preservar ou mudar as regras atuais de aprovação, confirmação e captura. A adaptação visual tem menos incerteza; rituais e workflows novos concentram o trabalho adicional.

## Critérios de aceite da primeira integração

- Os dados vêm do workspace real; reload preserva mudanças, e trocar workspace/usuário não mantém dados da sessão anterior.
- Hoje mantém decisões sem prazo, riscos aceitos relevantes e conflitos de prazo; ausência de dados não aparece como ausência de pendências.
- O peek abre por link direto e mantém a lista; fechar/Voltar/restaurar foco funciona em teclado e mobile.
- Membro e guest recebem ações compatíveis com suas capacidades; mudanças de autoridade/schema invalidam intenções antigas.
- Concluir/aprovar/arrastar não contorna evidência, aprovação independente ou transição válida.
- Delegar mantém prazo canônico, fuso, retorno e executores; não inventa confirmação nem autoria de terceiros.
- Inbox apresenta propostas e fontes reais, preserva edição/rejeição e não promete criação de novo risco ou envio externo indisponíveis.
- Contadores são completos com mais de 50/100 objetos e múltiplas páginas de relações; detalhes não geram carregamento por objeto para toda a lista.
- Testes unitários cobrem as projeções e seus limites; E2E cobre browser → API → PostgreSQL e, para revisão de risco, CoS → aprovação → efeito persistido.
- Desfazer A preserva uma alteração B posterior, inclusive feita por outro usuário; nenhuma inversa elimina auditoria ou contorna lifecycle.
- Preferências de ritual realmente orientam a recomendação; revisão já concluída não aparece novamente como pendente no mesmo período.
- Focos pertencem a um dia; concluídos têm apresentação consistente e contagens refletem o conteúdo mostrado.
- Primeiro uso funciona com e sem vault, preserva progresso, permite corrigir inferências e não duplica itens em retry/reload.

**Decisão proposta:** aprovar o mockup como direção visual e de interação, implementar uma primeira fatia sobre os contratos atuais e tratar os comportamentos restantes como requisitos explícitos. A arquitetura existente suporta essa evolução; os contratos do mockup ainda não estão prontos para uso real sem adaptação.
