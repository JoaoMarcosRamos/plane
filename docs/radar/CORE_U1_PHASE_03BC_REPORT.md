# RADAR Core U1 — Fase 3, entregas 3B/3C

**Data:** 06/10/2026, America/Bahia. **Escopo:** criação por capability (3B, C02) e lifecycle declarativo limitado (3C, C01), concluindo a fase 3 do [plano U1](CORE_U1_IMPLEMENTATION_PLAN.md). Decisões no [ADR](CORE_U1_PHASE_03BC_ADR.md); comandos e logs nas [evidências](../../output/core-u1-phase-03bc-20261006/README.md). A entrega 3A está no [relatório anterior](CORE_U1_PHASE_03_REPORT.md).

## Verificação de partida

A baseline isolada reproduziu **399 testes backend aprovados e 4 opt-ins ignorados**, igual ao fechamento da 3A. O registro de capabilities e o plano transacional de efeitos da 3A foram usados sem alteração de contrato: criação e transições continuam passando por preview, grants, versões, review e verificação do plano na execução.

## Entrega

**C02 — criação por capability**

- `ObjectType.rules.creation` seleciona uma capability com perfil de criação registrado. `CreateObject` é o padrão; `CreateAction`, `RegisterRisk` e `CreateDecision` são perfis especializados restritos aos tipos para os quais foram escritos.
- `CreateObject` separa `properties`, validadas pelas definições do workspace, de `parameters`, validados pelo perfil do tipo. O redirecionamento por `ObjectType.key` (`_special_input`/`creation_input`) foi removido. Uma propriedade extra válida em Action é persistida sem tocar serializers, conservando relações, `ActionCreated`, finding RADAR-M001 e autoridade composta.
- As três fachadas semânticas mantêm seus inputs, aceitam `properties` opcional e chamam o mesmo caminho de criação/efeitos. Funcionam apenas quando o tipo do workspace seleciona aquela capability.
- Toda criação, inclusive as internas de AddEvidence, CaptureIssue e RecordMeasurement, exige a capability declarada pelo tipo. O estado inicial vem do lifecycle persistido e é limitado pelo perfil; um descritor incompatível é recusado na configuração.

**C01 — lifecycle declarativo limitado**

- `ObjectType.rules.lifecycle` persiste propriedade de estado, inicial e transições explícitas, que referenciam capabilities e guards registrados. Os terminais vêm da definição enum; a saída de um terminal precisa ser declarada.
- O lifecycle é aplicado no writer comum de propriedades. UpdateObject, endpoints de propriedade, compatibilidade Python, primitives, runtime e handlers internos recusam pares não declarados ou executados por outra capability. Transições com guard exigem o guard registrado; carimbos são gerados pelo engine e protegidos contra escrita ou remoção.
- `ORDINARY_TRANSITIONS` foi removido. As tabelas do pacote o reproduzem exatamente e declaram os caminhos especializados: CompleteAction → `done` com `completed_at`, tomada de Decision pelo guard `decision_approval` com `decided_at`, dispositions de ReviewObject para Risk e ManagementItem e superação de Commitment por DelegateAction.
- Um tipo customizado com lifecycle configurado faz transições autorizadas sem branch Python pelo seu nome. Sem lifecycle, um enum `status` continua propriedade comum.
- O catálogo de schema publica os contratos de criação e lifecycle das capabilities e `transition_guards`; os tipos do cliente foram ampliados sem mudança de UX.

**Migration 0013:** dados apenas. Instala os descritores congelados nos tipos semeados, preserva seções locais existentes, atualiza a base instalada e incrementa a revisão de schema. A reversão remove as seções.

## Validação

| Verificação           | Resultado                                                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Baseline RADAR        | 399 aprovados, 4 opt-ins ignorados                                                                                       |
| Regressão RADAR final | **452 aprovados, 4 opt-ins ignorados**, 53 casos novos                                                                   |
| Contratos dirigidos   | **98 aprovados**: adapter CoS real, gate C16, 43 casos 3A e 53 casos 3B/3C                                               |
| Migration 0013        | Ida, volta e reaplicação em banco descartável; fatos, IDs, invariantes e seção local preservados; plano de upgrade vazio |
| Frontend              | **115 aprovados em 16 arquivos**                                                                                         |
| Workspace             | **56/56 tarefas** de `pnpm check`, incluindo paridade de contratos                                                       |
| Python/migrations     | Ruff e formatação aprovados; `makemigrations radar --check --dry-run` sem mudanças estruturais                           |

Os casos novos cobrem tipo novo com required/default, propriedade extra em tipo semeado, separação de parâmetros, requisitos e estado inicial sem bypass, política do tipo escolhendo a capability, descritores inválidos recusados, lifecycle customizado e terminal, carimbo como efeito planejado que exige grant, quatro entradas de escrita com a mesma regra, dispositions e CompleteAction lidos do lifecycle, guard human-only, aprovação pendente invalidada por mudança de lifecycle e migration de dados com seção local.

Durante a implementação, a primeira regressão encontrou dois problemas, corrigidos antes do fechamento. Um default novo em `parameters`/`properties` mudava o input normalizado e quebraria intent hashes e o Risk Review; os campos ficaram sem default. Revisando o planner, outro problema apareceu: a política human-only calculada após o handler sob savepoint dependia do estado já alterado. Ela passou a derivar do estado-alvo pedido, e um teste fixa `human_only=true` no plano persistido da tomada de Decision. Dois testes antigos foram ajustados ao contrato novo: a revisão de regras é comparada com a constante, e referências compostas de `CreateObject` vão em `parameters`.

Não houve alteração de UX/TSX, teste de navegador, deploy ou aplicação ao stack Plane em uso. Os testes do repositório CoS não foram reexecutados; o contrato consumido por ele mudou apenas por chaves aditivas em `command_contracts`, e o adapter real foi exercitado contra a API.

## Compatibilidade e rollout

- Intenções sem `parameters`/`properties` geram o mesmo intent hash; replays confirmados devolvem o resultado histórico. Ledgers v1 sem plano usam a especialização congelada em `legacy_replay.py`.
- **Mudança de contrato:** `CreateObject` com referências compostas dentro de `properties` passa a receber erro de propriedade desconhecida; esses clientes devem usar `parameters`. A UI atual não usa esse formato.
- Propostas pendentes sob o código ou metadata anteriores ficam obsoletas pelo fingerprint e exigem novo preview/review.
- Ativação: aplicar `0013_type_descriptors` após 0011/0012 e, depois, executar o upgrade explícito para alinhar o `package_hash`, sem mudanças de metadata. Antes de reverter, exportar customizações de lifecycle/criação.

## Saldo

Com C01 e C02, a fase 3 está concluída: **15 achados corrigidos e 8 pendentes**, sendo **6 U1** (C03, C13, C18, C19, C20, C21) e **2 U2** (C14, C23). O primeiro gate do plano para escrita dos builders (fases 2 e 3 validadas) foi atingido localmente. Ainda não há builder com UI. As fases 4–6 seguem pendentes, assim como o aceite integrado, e não há homologação de ambiente publicado.
