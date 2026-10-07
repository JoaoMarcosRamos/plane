# RADAR Core U1 — Fase 4

**Data:** 06/10/2026, America/Bahia. **Escopo:** criação por metadata (C03), editor por capacidades efetivas (C20) e apresentação/narrativa principal (C21). [Plano](CORE_U1_IMPLEMENTATION_PLAN.md), [ADR](CORE_U1_PHASE_04_ADR.md), [evidências](../../output/core-u1-phase-04-20261006/README.md).

## Partida

A regressão final das entregas 3B/3C (452 aprovados, 4 opt-ins ignorados) foi a baseline do mesmo worktree. Após a extração das restrições e a nova seção de apresentação, a suíte existente passou inteira antes dos casos novos.

## Entrega

**C20 — capacidades efetivas**

- Endpoint `objects/{id}/capabilities/` com campos, envelope, estado, transições, ações, relações, layout e erros de metadata, calculado para o actor da sessão.
- Disponibilidade de transições e de ApproveDecision obtida pelo planner real sob savepoint revertido; sem escrita, ledger ou provenance.
- Restrições especializadas de edição/remoção extraídas para funções únicas, usadas pelo command e pelo cálculo.
- UI: campo derivado, carimbo e campos de Decision tomada aparecem somente leitura com a razão; o estado oferece só os alvos permitidos ao actor, nunca terminais livres; "Clear" só quando removível; remoção de relação protegida não é oferecida e a que exige review aparece como "Request removal".
- Seção "Actions": transição com guard (tomar Decision), ApproveDecision e CompleteAction com formulário do contrato, preview do servidor e confirmação. Indisponibilidade corrente e metadata inválida são exibidas de forma distinta.

**C03 — criação por metadata**

- Formulário composto das definições do tipo e do perfil de criação; required sem default aparece e é exigido; defaults não alterados não são reenviados; derivados, estado e carimbos ficam fora; inicial do lifecycle informado.
- Parâmetros compostos com seletores de Object filtrados pela dica de tipo do contrato (`ObjectReferenceField`), inclusive múltiplos; relações obrigatórias anunciadas.
- Sem tipo padrão fixo; perfil ausente do catálogo torna o tipo indisponível.

**C21 — apresentação**

- `rules.presentation` com narrativa principal e seções; fallback documentado; propriedades não listadas em "Other properties".
- `content` rotulado "Notes" quando a narrativa é propriedade; conteúdo legado preservado e sinalizado, sem cópia.
- Aposentar propriedade referenciada degrada o layout em vez de bloquear; edição de apresentação é validada estritamente.
- Pacote com apresentação para os 11 tipos; migration de dados `0014_type_presentation`.

## Validação

| Verificação         | Resultado                                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Regressão RADAR     | **477 aprovados, 4 opt-ins ignorados**; 25 casos novos                                                                                 |
| Contratos dirigidos | **123 aprovados**: adapter CoS real, gate C16, casos 3A, 3B/3C e fase 4                                                                |
| Frontend            | **132 aprovados em 18 arquivos**; 17 casos novos de inputs, formulário, ações, seções, store e service                                 |
| Workspace           | **56/56 tarefas** de `pnpm check`; código RADAR sem avisos de lint; avisos preexistentes do app inalterados                            |
| Migration 0014      | Ida, volta e reaplicação em banco descartável; layout local preservado, fatos intactos, schema efetivo válido e plano de upgrade vazio |
| Python/migrations   | Ruff e formatação aprovados; `makemigrations radar --check --dry-run` sem mudanças estruturais                                         |
| Navegador/API/banco | Cinco fluxos aprovados com componentes de produção, API, sessão, commands e PostgreSQL reais; prova independente no banco              |

Fluxos de navegador: criação de um tipo existente apenas no workspace, exigindo o required sem default, seguida de lifecycle até o terminal com carimbo; Risk com score derivado somente leitura e seções próprias; CompleteAction com evidência, preview e confirmação; Decision indisponível ao autor e aprovada e tomada por revisor independente; guest somente leitura. A prova no banco confirma seis intenções da sessão, todas sob a revisão de schema corrente. Capturas e logs estão nas evidências.

A primeira execução no navegador encontrou dois defeitos, corrigidos antes do fechamento:

- **Formulário aninhado:** o editor da narrativa ficava dentro do formulário de título e notas.
- **Conflito na tomada de decisão:** a regra de versões usava o cache da lista para uma Person já alterada pela aprovação; a regra foi restrita ao Object da página e há teste de store para isso.

Na revisão visual, os rótulos de capability foram humanizados. A prova final foi repetida num banco limpo com o código final.

O navegador usou um harness Vite com a `RadarObjectPage` e o diálogo de criação de produção; o editor rico, o seletor de membros e as permissões de UI foram substituídos por stubs, como na fase 2. Não é homologação do shell completo, do provider/CoS real em produção ou de ambiente publicado.

## Compatibilidade e rollout

- Contratos de input mantêm tipos e validação; `object_types` e `object_action` são chaves aditivas do contrato. Respostas de erro de UpdateObject/UnlinkObjects mantêm as mensagens.
- A UI passa a depender do endpoint de capacidades: até carregá-lo, campos ficam somente leitura.
- Ativação: aplicar `0013_type_descriptors` e `0014_type_presentation` e, depois, o upgrade explícito para alinhar o hash do pacote. Antes de reverter, exportar apresentações locais.

## Saldo

Com C03, C20 e C21, a fase 4 está concluída: **18 achados corrigidos e 5 pendentes**, sendo **3 U1** (C13, C18, C19) e **2 U2** (C14, C23). Seguem a fase 5 (runtime e fatos operacionais: C19, C18) e a fase 6 (consultas delimitadas, C13, e homologação integrada dos 16 achados).
