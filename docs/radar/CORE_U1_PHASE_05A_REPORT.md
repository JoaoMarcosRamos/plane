# RADAR Core U1 — Fase 5A

**Data:** 06/10/2026, America/Bahia. **Escopo:** C19, identidade/contexto de runtime por descritor do tipo. Primeira entrega independente da fase 5; C18 permanece em 5B. [Plano](CORE_U1_IMPLEMENTATION_PLAN.md), [ADR](CORE_U1_PHASE_05A_ADR.md), [evidências](../../output/core-u1-phase-05a-20261006/README.md).

## Conferência das entregas anteriores

O worktree contém os contratos, migrations 0011–0014, endpoints, stores, formulários e testes registrados pelas fases 0–4. A regressão inclui os testes U0, 0/1, 2, 3A, 3B/3C e 4, além de runtime, configuração, Risk Review, Today e colaboração. Os 132 testes frontend e as 56 tarefas de `pnpm check` foram repetidos. As capturas de navegador da fase 4 continuam evidência histórica; não foram repetidas nesta entrega sem alteração de fluxo visual.

A primeira execução backend foi iniciada antes de concluir as alterações e carregou parte do código novo durante o teste de provisioning. Seus 476 aprovados/1 falha não constituem baseline reproduzível. A execução dirigida seguinte encontrou uma chave incorreta na fixture nova (`object_type` em vez de `object_type_id`), corrigida. Uma regressão intermediária passou com 514 aprovados/4 opt-ins ignorados. Após o ajuste da montagem de relações em criação composta e seu teste adicional, a validação final usa processo novo e código estabilizado.

## Entrega

- `rules.runtime`: habilitação explícita, estratégia registrada `dated_token_v1`, prefixo e categorias de contexto; ausência é desabilitada. Metadata inválida não persiste. Registro/DTO concordam por checagem de CI.
- Binding administrativo e geração por efeitos compostos compartilham writer, formato, verificação de colisão e identidade imutável. Relações obrigatórias são validadas no binding explícito e no grafo final de criação composta.
- Leitura do contexto Plane e CoS compartilha elegibilidade ativa do workspace, com grants e escopo da credencial. Tipo customizado pode entrar no contexto e ser revisado sem alterar o snapshot global; tipo sem status não recebe status artificial.
- Capabilities anunciam descritores e targets elegíveis sob a revisão efetiva e o grant, com dependências obrigatórias de tipo no registro. Revogação de Person bloqueia ambos os canais; nova credencial exige grant vigente, membership, Person e contexto autorizados.
- CLI deixa de construir o escopo por catálogo global: seleciona tipos elegíveis atuais, com opção de lista explícita; nunca usa wildcard por default. Binding aceita revisão de schema esperada.
- Migration `0015_type_runtime`: preserva identidades, fatos, timestamps, opt-outs e base de upgrade, com revisão e reaplicação idempotente. Nenhuma migração de fatos operacionais de C18 foi executada.
- O script de paridade já exigido por `pnpm check` estava excluído de Git por `scripts/`; uma exceção restrita o torna revisável e versionável.

## Validação

| Verificação                        | Resultado                                                                                                 |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------- |
| RADAR completo, com CoS habilitado | **516 aprovados, 3 opt-ins ignorados**, zero falhas/erros; inclui **38 casos novos** e o adapter CoS real |
| Fronteira Plane                    | **2 aprovados**: Workspace e WorkspaceMember                                                              |
| Frontend                           | **132 aprovados em 18 arquivos**; nenhuma mudança de fluxo visual                                         |
| Workspace                          | **56/56 tarefas** de `pnpm check`; paridade de kinds, capabilities e identidade/contextos confirmada      |
| Python                             | Ruff e formatação aprovados nos 13 arquivos Python alterados                                              |
| Migrations                         | `makemigrations radar --check --dry-run`: sem mudanças estruturais                                        |
| Migration 0015                     | Ida, volta, reaplicação e idempotência; fatos/IDs/timestamps/opt-out preservados; upgrade sem conflitos   |

Os casos novos cobrem defaults sem integração, configuração por command auditado, tipo customizado no catálogo/contexto dos dois canais, formatos, contextos, colisões, imutabilidade, revisão esperada, autoridade administrativa, grants, escopo da Person, revogação/retirada, autoria/provenance, review e replay, intenção obsoleta, geração interna e montagem de grafo obrigatório. Os testes usam PostgreSQL real no stack descartável, sem provider externo.

A verificação da migration executa 0014 → 0015 → 0014 → 0015 em banco descartável, testa a função forward novamente, compara IDs/timestamps/fatos e confirma upgrade sem conflitos após preservar um opt-out local. A revisão segue 5 → 6 → 7 → 8. O adapter CoS de produção usa HTTPX com transporte in-process para a API Django real e PostgreSQL; não é um processo CoS/provider externo em produção.

## Ativação e saldo

Aplicar a cadeia até 0015, executar o preview/upgrade administrativo do pacote e revisar as intenções pendentes sob o novo contrato. Para tipo customizado: editar `rules.runtime` com revisão esperada, provisionar binding explícito e incluir o tipo no grant, se sua lista não for wildcard. Exemplo e política de reversão nas evidências/ADR.

Sem commit, deploy ou ativação do stack em uso. Downgrade exige exportar os descritores locais e não conserva funcionalmente a política nova no código antigo. Não há UI nova de provisioning.

**Saldo:** 19 dos 23 achados corrigidos; 2 U1 (C18, C13) e 2 U2 (C14, C23) pendentes. **Próxima entrega: 5B/C18**, começando pelo ADR de prazo/atribuição e inventário/dry-run de divergências, antes do backfill auditado e histórico paginável. U1 só termina com C13 e a homologação integrada da fase 6.
