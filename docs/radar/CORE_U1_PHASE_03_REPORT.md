# RADAR Core U1 — Fase 3, entrega 3A

**Data:** 06/10/2026, America/Bahia. **Escopo:** registro de capabilities e plano completo de efeitos, primeira das três entregas da fase 3. [Plano](CORE_U1_IMPLEMENTATION_PLAN.md), [ADR](CORE_U1_PHASE_03_ADR.md), [evidências](../../output/core-u1-phase-03-20261006/README.md).

## Verificação das entregas anteriores

A inspeção confirmou implementação das fases 0–2, migrations 0011/0012 e seus contratos no filesystem. A baseline isolada reproduziu **356 testes backend aprovados e 4 opt-ins ignorados**, correspondente ao relatório da fase 2. O rodapé do plano estava desatualizado ao anunciar fase 2 como próxima; foi corrigido para acompanhar as entregas 3A/3B/3C.

A conferência da política operacional também encontrou colaboração usando lookup de Object sem filtrar tipo inativo. Os adapters de leitura/upload/download e o handler de colaboração passam a usar a consulta operacional comum; histórico/provenance continua acessível pelo caminho histórico autorizado.

## Entrega

- **C09:** roles/membership comuns, referências por capability e plano transacional compartilhado para preview, grants, versões, locks, review e execução.
- **C17:** registro único de 21 capabilities existentes, contratos de input gerados, catálogo do runtime sem `DEFINITIONS` e paridade de tipos de campo com o cliente.
- Preview autorizado em `POST /api/workspaces/{slug}/radar/commands/preview/`, sem ledger, provenance ou fatos persistidos. Retorna revisão, versões completas, necessidade de review e efeitos simbólicos.
- DTOs e `RadarService.previewCommand` para consumo do contrato pelo cliente; nenhuma tela de builder foi ativada.
- Planejamento cobre campos explícitos/defaults/derivados, relações adicionadas/retiradas, registros e payloads privados. Execução que acrescenta ou altera efeitos fora do plano reverte atomicamente.
- Replanejamento nas três fronteiras de aprovação e verificação de dependências. Fingerprint inclui o registro. Replay confirmado usa o plano persistido e grant atual, sem executar o handler novamente.
- Provisioning novo declara `UnlinkObjects` para a remoção de atribuições composta por delegação. Grants existentes não são ampliados automaticamente: devem ser revisados caso delegação precise retirar relações.

A leitura auxiliar de um guard fica versionada no plano e protegida pelo lock conservador. Referências do input e Objects escritos precisam de versões explícitas; dependências apenas lidas podem usar a versão observada pelo servidor, preservando o contrato de escrita da UI atual. O preview permite revisar/enviar o mapa completo. A diferença é documentada no ADR e coberta por testes.

## Validação

| Verificação                | Resultado                                                              |
| -------------------------- | ---------------------------------------------------------------------- |
| Baseline RADAR             | 356 aprovados, 4 opt-ins ignorados                                     |
| Regressão RADAR            | **399 aprovados, 4 opt-ins ignorados**, 43 casos novos                 |
| Frontend                   | **115 aprovados em 16 arquivos**, um caso novo                         |
| Workspace                  | **56/56 tarefas**, incluindo contratos, lint, format e types           |
| Contratos CoS selecionados | **27 aprovados**, com SQLite em memória e transporte simulado          |
| Python                     | Ruff e formatação dos arquivos alterados aprovados                     |
| Migrations                 | `makemigrations radar --check --dry-run`: nenhuma alteração estrutural |

Resultados finais e comandos reproduzíveis estão em [evidências](../../output/core-u1-phase-03-20261006/README.md) e `result.json`. As contagens de baseline e reexecuções não são somadas à suíte final.

O fechamento dirigido aprovou **45 casos**, incluindo o adapter CoS real, os 43 casos da entrega 3A e o gate C16 de interfaces. São reexecuções separadas, sem somar à regressão final.

A primeira regressão identificou um import privado entre módulos; a interface foi publicada, preservando o gate C16 existente. A verificação das versões auxiliares identificou uma incompatibilidade com uma transição U0 em Object vinculado; a versão de leitura ficou no plano, preservando as precondições explícitas de escrita. Logs diagnósticos são mantidos separadamente do resultado final.

Não houve alteração de UX/TSX ou teste de navegador nesta entrega. O preview foi exercitado pelo transporte de sessão real, commands/guards/ledger e PostgreSQL isolado. O service tem unit test de DTO e caminho HTTP. O adapter CoS real usa um transporte HTTP em processo para a API Django; não equivale a testar Telegram/provider ou o ambiente publicado.

## Migration, rollout e saldo

Não há nova coluna/model/migration. `makemigrations radar --check --dry-run` verifica essa condição. Schema revision e versões dos fatos continuam separados; a ontologia 3.2.0 e protocolos v1 permanecem. Ledgers/eventos/provenance antigos não são reescritos.

As políticas novas podem exigir grants adicionais sobre efeitos antes cobertos por listas conservadoras ou incompletas. Grants antigos não são ampliados em background. Código novo invalida propostas pendentes pelo contrato de implementação; uma nova intenção exige preview/review. Confirmed replay mantém o resultado histórico.

**Saldo:** C09 e C17 concluídos nesta entrega. São **13 achados corrigidos e 10 pendentes**, dos quais **8 U1 e 2 U2**. A fase 3 permanece em andamento: **3B, C02 (criação por capability/metadata)** e **3C, C01 (lifecycle declarativo limitado)** são as próximas entregas, antes do gate de escrita dos builders. Fases 4–6 permanecem pendentes. A fonte de prazos/atribuição e identidade de runtime continua no escopo de C18/C19.

O worktree anterior foi preservado; não houve commit, deploy ou alteração do stack Plane em uso. A evidência é local/isolada, sem declarar homologação integral de U1.
