# RADAR — Documentação técnica

Atualizado em 06/10/2026. **E2E da simbiose 1.8 homologado localmente no shell real** (login, backend, runtime CoS e PostgreSQL juntos; provider real em uma execução). Uso em piloto e upload de anexo pela UI continuam pendentes. Nenhum ambiente publicado foi ativado.

| Documento                                                                                    | Uso                                                                        |
| -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| [Auditoria do Core — 2.1](CORE_AUDIT.md)                                                     | 23 achados classificados por impacto, urgência e risco                     |
| [Correções U0 do Core](CORE_U0_REPORT.md)                                                    | Invariantes, contrato de regras, cardinalidade e fronteira de escrita      |
| [Relatório da Fase 1 (HTML)](PHASE_1_REPORT.html)                                            | Visão consolidada 1.1–1.8: arquitetura, workflows, capturas e testes       |
| [E2E da simbiose — 1.8](E2E_SYMBIOSIS.md)                                                    | Fluxo completo no shell real, provider, permissões, idempotência e achados |
| [Colaboração mínima — 1.7](COLLABORATION.md)                                                 | Comments, anexos privados, activity e pendências de piloto                 |
| [Today — 1.6](TODAY.md)                                                                      | Quatro filas de atenção, critérios, consulta e validação                   |
| [Risk Review — 1.5](RISK_REVIEW.md)                                                          | Skill, evidências e Accept/Edit/Reject via Command Layer                   |
| [Agent Config — 1.4](AGENT_CONFIG.md)                                                        | Schema, API/UI, autorização, versões, compatibilidade e ativação           |
| [Agent Runtime — 1.3](AGENT_RUNTIME.md)                                                      | Fachada Plane, adapter CoS, estados/eventos e pausa/retomada               |
| [Validação geral 0–1.4](GENERAL_VALIDATION_REPORT.md)                                        | Regressão ampliada, correções encontradas e limites antes do piloto        |
| [Prontidão após 1.8](NEXT_PHASE_READINESS.md)                                                | Escopo, critérios de aceite e gates antes do piloto                        |
| [Command Layer](COMMAND_LAYER.md)                                                            | Contrato comum de mutação, grants, provenance e approvals                  |
| [Integração CoS → commands](COS_INTEGRATION.md)                                              | Transporte, vínculos canônicos, intenção salva e provisionamento           |
| [Arquitetura](ARCHITECTURE.md)                                                               | Decisões do Core e evolução até runtime/configuração                       |
| [Roadmap de produto](../../../DOCS_PROJETO_RADAR_COMPLETO/RADAR_ROADMAP.md)                  | Status e sequência das fases                                               |
| [Documentação CoS — 044](../../../COS_AGENT_V2/docs/development/044-radar-agent-config.html) | Implementação e explicação do consumo da configuração pelo motor           |

## Evidência da implementação 1.8

[Evidências e reprodução](../../output/e2e-symbiosis-20261005/README.md): **68/68 verificações** numa execução limpa (navegador → login real → shell → API → CoS Deep Agents → PostgreSQL), incluindo rejection, permissões e idempotência; provider real `anthropic:claude-sonnet-4-6` completou o loop pela UI. Corrigido o CORS que bloqueava mutações RADAR no shell real. Piloto pendente.

## Evidência histórica da implementação 1.7

[Evidências e limites](../../output/collaboration-20261005/README.md): **263 backend e 92 frontend aprovados**, quatro opt-in skipped; types/lint/format/Ruff/migrations aprovados. Backend e HTTP real comprovam Command Layer, autoria, isolamento, auditoria, rollback, integridade e concorrência. Navegador verificou comentário/edição/reload, rename/download, guest, membro distinto, exclusão por admin e bloqueio externo com sessão Django/PostgreSQL isolados. Upload pela UI, shell/login completos e piloto permanecem pendentes.

## Evidência histórica da entrega 1.6

[Comandos, logs e screenshots](../../output/today-20261005/README.md): 77 frontend e 234 backend únicos aprovados (regressão + reexecução final de 9 testes Today), quatro opt-in backend desativados. Chrome → API Plane → PostgreSQL isolado verificou quatro grupos, links, rejeição/refresh e estados vazio/erro. Types/lint/format/Ruff aprovados. Shell completo e piloto permanecem pendentes; CoS não foi alterado nesta entrega.

## Evidência histórica da entrega 1.5

[Comandos, logs e limites](../../output/risk-review-20261005/README.md): 229 backend RADAR, 1.182 CoS e 72 frontend aprovados; 11 CoS opt-in desativados. Navegador → Plane HTTP → CoS/Deep Agents scripted → aprovação → domínio/provenance em PostgreSQL isolado. Provider real, login/shell completo e piloto permanecem pendentes.

## Evidência histórica da entrega 1.4

[Comandos, logs e limites da validação](../../output/agent-config-20261004/README.md): **199 backend RADAR + 67 CoS selecionados + 58 frontend = 324 testes aprovados**. HTTP entre processos com adapter real e geração determinística; formulário/MobX no Chrome em fixture isolada. Resultados históricos da implementação, sem reexecução nesta revisão documental.

## Relatórios históricos

Os relatórios registram o escopo e os testes de cada entrega. Sua indicação de “próxima etapa” pertence à data do relatório; o estado atual é o roadmap acima.

- [Foundation — 0.3A](CORE_VERTICAL_SLICE_REPORT.md)
- [Semantic Model — 0.3B](SEMANTIC_MODEL_REPORT.md)
- [Semantic UI — 0.4](SEMANTIC_UI_REPORT.md)
- [Governança de IA — 0.5](GOVERNANCE_SCENARIO_REPORT.md)
- [Spike / CONDITIONAL GO — 0.6](SPIKE_REPORT.md)

Os links entre repositórios pressupõem pastas irmãs. Manifestos de implementação conservam os hashes capturados na entrega; revisões posteriores de documentação não reescrevem essas evidências.
