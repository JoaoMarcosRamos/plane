# U1 fase 2 — decisões de implementação

Data: 06/10/2026. Escopo: C07, C11, C12 e parte estrutural de C17.

## Instalação e ownership

`WorkspaceSchemaState` guarda revisão, origem, versão/hash do pacote, base materializada e IDs sob gestão. `SchemaUpgrade` registra instalações e upgrades; os comandos usam a transação, lock de Workspace e provenance existentes. `is_system` é apenas um indício conservador para o baseline legado, não uma autorização para sobrescrever campos.

A migration `0012_workspace_schema` congela a materialização Core 3.2.0. Workspaces com metadata recebem origem `legacy`, revisão 1 e versão/hash desconhecidos, mesmo quando a configuração coincide com o pacote. Diferenças, ausências e colisões com definições locais são registradas. Workspaces vazios continuam sem instalação. A migration conserva IDs e fatos.

Instalação nova é explícita e administrativa em `POST /radar/schema/` (`operation: install`). Os initializers Python permanecem fachadas de provisioning auditado, agora sujeitos à autoridade administrativa. GETs não instalam nem completam schema. Instalar novamente não reativa nem recria definições retiradas.

Upgrade compara base instalada, configuração local e pacote candidato por campo, inclusive campos de config. Lists são valores atômicos. IDs, customizações sem conflito e inativação/soft-delete intencionais são preservados. Colisões não geridas e alterações concorrentes produzem conflitos. Preview retorna hash candidato, revisão, mudanças, preservações e bloqueios de migração; execução exige revisão/hash revisados. Kind changes são conservadoramente recusadas; choices/defaults, required e cardinalidade são verificados contra os fatos. Migração de fatos não é executada automaticamente.

## Leitura operacional e histórico

`active.py` centraliza Object/ObjectType, definições, valores e relações. Endpoints e referências precisam estar ativos, não excluídos e no mesmo workspace; valores precisam corresponder ao tipo do Object. Lista, detalhe, snapshots, Today, Risk Review e contexto de runtime usam essa política. O endpoint de provenance consulta `all_objects` explicitamente, com autorização, e mantém o histórico de recursos retirados; esse histórico não entra no contexto corrente.

## Revisão e cache

`Object.version` versiona fatos. `WorkspaceSchemaState.revision` versiona metadata. O flush incrementa a revisão uma vez por transação de metadata, incluindo escritores internos auditados; não incrementa todos os Objects. Instalação começa em 1. Revisão/base-only upgrade também invalida o contrato.

O catálogo agregado `GET /radar/schema/` é construído sob lock de Workspace. Snapshots de propriedades/relações retornam `schema_revision`, catálogos legados conservam arrays e expõem `X-Radar-Schema-Revision`. Today, contexto e capabilities de runtime anunciam revisão. O fingerprint de aprovação também inclui a revisão. Replay confirmado precede a precondição de schema; propostas pendentes sob metadata anterior ficam obsoletas.

Escritas genéricas de sessão exigem `X-Radar-Expected-Schema-Revision`; o envelope genérico de `/commands/` exige `expected_schema_revision`. Intenções v1 já confirmadas podem replay sem o campo novo. Callers Python confiáveis e runtime v1 podem omitir essa precondição durante compatibilidade, mas sempre passam pela validação atual e pelo fingerprint de aprovação. Colaboração usa autoridade e versões de fatos, sem exigir precondição de metadata em uploads. Não se amplia a autoridade de nenhum canal.

O cliente usa catálogo agregado e compara versão dos fatos + revisão do schema. Respostas antigas não restauram metadata removida; revisões diferentes não formam um snapshot válido. Revisão nova invalida o uso do snapshot, mas conserva sua última representação enquanto atualiza, preservando rascunhos. Formulários pedem revisão explícita antes de nova escrita. Polling de 30 segundos, foco da janela e conflito HTTP atualizam o catálogo. A intenção incerta conserva a revisão original no retry. O fallback de clientes injetados antigos é limitado aos clientes antigos injetados em testes; o serviço de produção fornece o catálogo agregado.

`authority_revision` de sessão depende da membership/role e é separado do schema; o servidor revalida usuário/membership em cada acesso. Capabilities detalhadas por campo, lifecycle e registro único de comandos continuam na fase 3. Revisão de metadata não substitui autoridade nem fingerprint.

## Kinds e descritores

`ontology/contracts.py` é o registro estrutural dos 11 kinds existentes, suas chaves de config, defaults e descritores de relações. Model saves rejeitam config estrutural inválida antes de persistir; comandos de metadata também verificam compatibilidade factual e referências de invariants. Constraints de kind/cardinalidade e revisão positiva permanecem explícitas no banco.

`pnpm check:radar-contracts`, integrado ao `pnpm check`, compara kinds e chaves de config e cardinalidades com o cliente. `text/string` e `url/uri` são aliases reservados para migração, não novos kinds persistidos. Referências de relações do pacote a feedback/meeting/learning/routine são nomes reservados fora do slice inicial, sem criar tipos ou autorizar capacidades implícitas. C17 permanece aberto até o registro de capabilities da fase 3.
