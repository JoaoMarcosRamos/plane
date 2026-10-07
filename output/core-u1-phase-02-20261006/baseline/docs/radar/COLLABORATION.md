# Colaboração mínima do MVP — 1.7

Implementada localmente em 05/10/2026 na Object Page. A colaboração necessária ao fluxo validado é: registrar esclarecimentos sobre um Object, guardar pequenos arquivos de apoio e consultar quem alterou seu estado. O escopo não inclui colaboração ampla nem encerra os gates do piloto.

## Escopo e reutilização

| Necessidade no fluxo              | Implementação                                                     | Limite deliberado                                                                            |
| --------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Esclarecer risco, decisão ou ação | Comentários em texto simples: criar, editar e excluir logicamente | Sem threads, reactions, mentions, notificações ou edição simultânea                          |
| Guardar arquivo de apoio          | Upload privado, download, rename e exclusão lógica por Object     | Um arquivo por request, 1 byte–2 MiB; sem preview, substituição de bytes ou upload no editor |
| Entender alterações               | Activity paginada derivada da provenance persistida               | Histórico de commands; sem eventos inventados, presença ou publisher assíncrono              |

A route existente e a sessão/membership do Plane são reutilizadas. Button, InputField e TextAreaField vêm de `@makeplane/propel`, por subpath. A UI combina `useUserPermissions` do Plane com flags de autoria calculadas pelo servidor. O estado usa um store MobX separado por workspace, dentro de `RadarStoreProvider`, preservando a arquitetura existente dos stores RADAR em `apps/web/store/radar`.

`ObjectComment`, `ObjectAttachment` e `AttachmentPayload` pertencem exclusivamente a RADAR. Nenhum model, endpoint, store ou FileAsset de Issue armazena o domínio. Os anexos são arquivos de apoio: não criam Document, Relation, EvidenceRecord ou aprovação. Evidência normativa continua a exigir os commands `AddEvidence`, `ApproveDecision` ou `CompleteAction` existentes.

## Commands e autoria

| Command            | Input específico além do envelope comum                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| `AddComment`       | `object_id`, `body` (1–10.000 caracteres após trim)                                                     |
| `EditComment`      | `object_id`, `item_id`, `expected_revision`, `body`                                                     |
| `DeleteComment`    | `object_id`, `item_id`, `expected_revision`                                                             |
| `AddAttachment`    | `object_id`, `filename`, `size`, `sha256`; bytes transitórios enviados pelo adapter multipart confiável |
| `RenameAttachment` | `object_id`, `item_id`, `expected_revision`, `filename`                                                 |
| `DeleteAttachment` | `object_id`, `item_id`, `expected_revision`                                                             |

Todos usam `execute_command`, envelope estrito, Actor derivado da sessão, `expected_versions` exato para o Object, idempotência, lock de workspace e transação PostgreSQL. O upload calcula tamanho/hash no servidor e vincula os bytes ao input normalizado; a API de commands JSON sozinha não pode criar um anexo. Os bytes não entram no envelope, resultado ou diff de provenance. Metadados e hash entram na auditoria.

Esses seis commands são human-only no MVP, mesmo se um grant os mencionar; capabilities do runtime não os anunciam. User ativo, não bot, e membership ativo com role 15/20 são requisitos internos do Command Layer. Guest (role 5) lê/download; não escreve. Usuário externo, membership inativo e User inativo ficam bloqueados.

Edição/rename exige autoria. Exclusão exige autoria ou admin ativo do workspace; admin não pode reescrever comentário/nome alheio. Identidade e workspace enviados no input são rejeitados quando desconhecidos ou incompatíveis. Referências são conferidas simultaneamente contra workspace, Object e item, inclusive no download. Objects/itens excluídos não ficam acessíveis nas consultas de produto.

Cada item tem `revision` própria. Edição/exclusão compara `expected_revision`, incrementa essa revisão e preserva criador/provenance original. Conflitos retornam 409. **Discussão e anexos não incrementam Object.version nem invalidam DecisionApproval**: não são alterações de conteúdo/evidência normativa. A precondição de versão do Object impede aplicar uma intenção sobre outro snapshot sem revisão. Concorrência de edição e upload foi testada com conexões PostgreSQL independentes.

Models de colaboração bloqueiam `save` sem contexto de command e bulk writes de domínio. O único update de queryset autorizado é o preenchimento de referências de provenance pelo flush transacional. Payloads são imutáveis; não existe endpoint para substituir bytes. SQL de manutenção administrativa não é uma API de produto.

## API, activity e UI

- `GET /api/workspaces/:slug/radar/objects/:objectId/collaboration/`: snapshot do Object/version, comments, attachments, flags de autoria e até 50 registros de activity. `activity_next` continua por `?activity_before=<provenance UUID>`; o cursor também precisa pertencer ao Object/workspace. Comments e attachments ativos são retornados integralmente neste MVP.
- `POST /api/workspaces/:slug/radar/commands/`: comments, rename e exclusões pelo envelope comum.
- `POST /api/workspaces/:slug/radar/objects/:objectId/attachments/`: somente multipart `file`, sem campos extras; exige `Idempotency-Key` e `X-Radar-Expected-Versions`.
- `GET /api/workspaces/:slug/radar/objects/:objectId/attachments/:attachmentId/download/`: autenticação e autorização reavaliadas; resposta `attachment`, `application/octet-stream`, `private, no-store` e `nosniff`.
- `GET .../provenance/`: o endpoint existente também inclui os filhos de colaboração, com snapshots antes/depois e histórico de exclusão.

Activity lê registros reais de Provenance que afetam o Object ou seus filhos. Exibe command, autor/principal, data, motivo, source e outcome; IDs de command/correlation/provenance são retornados. Não registra reads/downloads como mudanças de domínio. Auditoria de mutações e outbox ficam no commit do command, sem depender de um consumidor assíncrono.

A UI tem estados de carregamento/erro/vazio, reload, confirmação de remoção, escape de texto simples e retry. Falha de transporte conserva o payload/chave/revisões da intenção em memória; editar o payload cria nova intenção. 403/404/409 oculta o snapshot antigo e requer reload. Sucesso de mutação seguido de erro de leitura é mostrado como “Change saved. Reload…”, evitando reenviar o que já foi confirmado. Respostas de leitura/mutação atrasadas não substituem o Object aberto depois. Draft de comentário novo e arquivo selecionado sobrevivem à falha; a intenção de retry não sobrevive ao fechamento/reload completo do navegador.

## Storage e falhas

O MVP guarda os bytes privados em `radar_attachment_payloads`, no mesmo PostgreSQL do domínio. Isso elimina gravação parcial entre banco e storage externo: metadados, payload, provenance e evento são atômicos. Nenhuma URL pública ou key de bucket é exposta. Size é conferido lendo até 2 MiB + 1, sem confiar em Content-Length/MIME do cliente. Filename rejeita paths e controles; downloads forçam tratamento como arquivo, sem renderização inline. Tamanho e SHA-256 são conferidos antes de servir bytes.

Arquivo vazio/oversized, campos extras, falta de intenção/snapshot e referências inválidas retornam 400/404; autoria/membership retorna 403 (sessão ausente, 401); conflito retorna 409. Falha de leitura/upload ou gravação no banco retorna 503. A transação reverte completamente: não há anexo ativo órfão, payload parcial ou provenance de sucesso. Falhas de banco são logadas no servidor. Conforme o Command Layer existente, tentativas inválidas/falhas revertidas não têm registro durável separado de auditoria de tentativas.

Exclusão é lógica e mantém bytes/histórico, inacessíveis pelo download normal. Não existe restore/purge de produto nesta entrega. Limite por arquivo não é quota de workspace; retenção de bytes excluídos, quotas, backup/restauração e capacidade do PostgreSQL precisam ser definidos para o ambiente do piloto. Storage externo é evolução futura, sem depender dos modelos de Issue ou da baseline MinIO para este upload RADAR.

## Validação e pendências antes do piloto

**263 backend e 92 frontend aprovados**, quatro integrações backend opt-in skipped; types, lint, format, Ruff e migration check aprovados. [Evidências e comandos](../../output/collaboration-20261005/README.md) distinguem testes automatizados, HTTP real e navegador. Migration `0010_object_collaboration` cria as três tabelas próprias. Testes cobrem autoria, guest/externo/inativos, Object/workspace cruzado, campos forjados, revisão/replay, exclusão, auditoria e paginação; bytes/download/hash, limites de upload, falha de leitura/banco, rollback, revogação, corrupção e concorrência. Frontend cobre transporte multipart, retries estáveis, erro após commit, autoridade, texto escapado e respostas atrasadas. Mocks frontend não são usados como evidência de persistência.

Navegador validou comentários/edição/reload, rename/download, leitura do guest, restrição de outro membro, remoção por admin e bloqueio externo contra sessão Django e PostgreSQL reais. O upload multipart foi validado por HTTP entre processos; **seleção e submissão do arquivo pela UI não foram homologadas** nesta sessão, devido à permissão ausente da extensão de automação. Download pela UI criou arquivo local com hash igual ao original. Login da fixture provisiona sessão de teste; shell/login completos do produto continuam pendentes. Editor/membership visual simplificados existem apenas na fixture.

Antes do piloto: aplicar migration no ambiente escolhido; homologar upload pelo navegador comum e sessão/shell reais; confirmar proxy/timeouts/limites de corpo, capacidade/quota e retenção/backup; decidir política de tipos e verificação de arquivos para os usuários do piloto. Bytes são opacos e não recebem scanning/classificação nesta entrega. Homologar o loop completo com provider real e uma versão reproduzível Plane/CoS. Publisher/outbox operacional, métricas e auditoria durável de tentativas permanecem pendências existentes.

Realtime, presence, threads, rich comments, notificações, reactions, anexos no editor/comentário e colaboração com agentes estão fora deste slice. O piloto e colaboração ampla não estão marcados como entregues. Não houve deploy nem alteração/revalidação do CoS nesta fase.
