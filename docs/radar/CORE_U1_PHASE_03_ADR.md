# RADAR Core U1 — ADR da entrega 3A

**Data:** 06/10/2026, America/Bahia. **Escopo:** primeira das três entregas da fase 3: registro de capabilities e planejamento de efeitos. Criação configurável e lifecycle pertencem às entregas 3B/3C.

## Registro executável

`commands/capabilities.py` é a fonte dos nomes de commands, inputs tipados, handlers, planners, referências, targets, políticas mínimas e projeções de runtime. `INPUTS` e `OPERATIONS` são views do registro, sem listas paralelas. O catálogo HTTP de schema e os contratos do runtime são projeções desse registro; parâmetros vêm dos campos dos serializers, incluindo validação numérica finita.

Capabilities são registradas por código da aplicação. Metadata não registra Python, scripts ou handlers nem reduz human-only, revisão independente ou guards de evidência. Campos condicionais e regras de negócio continuam nos handlers tipados. O registro inteiro participa do fingerprint de aprovação, além do digest de implementação já existente.

Uploads declaram o transporte multipart autenticado. O input JSON é metadata do arquivo; bytes não aparecem em catálogo, plano ou provenance. O plano inclui apenas vínculo simbólico, tamanho e hash do payload persistido.

## Plano transacional conservador

Reutilizar o mecanismo existente de executar o handler sob um savepoint revertido. O planner exercita os mesmos guards e primitives, registra Objects lidos/modificados/criados, propriedades explícitas/defaults/derivadas, relações, registros, payloads e eventos. A coordenação continua pelo lock de Workspace; não se introduz otimização de locks nesta entrega.

IDs criados são simbólicos por model. Timestamps gerados pelo command e colunas automáticas de auditoria são simbólicos; datas fornecidas pelo caller permanecem literais. Identidades externas criadas conservam o prefixo no símbolo. Nenhuma linha temporária é anunciada como fato persistido.

O conjunto de efeitos fornece autoridade por command, tipo e campo. Relações compostas exigem `LinkObjects`/`UnlinkObjects` conforme o efeito real; defaults e campos derivados também exigem grant. Tentativas de edição no-op continuam exigindo autoridade sobre os campos pedidos. Dependências são observadas por consultas públicas e FKs das mutações, além das referências declaradas pela capability.

A execução real é recapturada e comparada ao plano antes do flush de provenance/outbox. Um campo, registro, referência, payload ou evento adicional provoca conflito e rollback do ledger e dos fatos. O plano é persistido no envelope do servidor e na provenance; o cliente não pode fornecê-lo como autoridade.

## Versões de escrita e dependências auxiliares

Versões explícitas são obrigatórias para referências declaradas pelo input e todos os Objects afetados por uma escrita, inclusive efeitos compostos não declarados inicialmente. Leituras auxiliares de guards podem usar a versão capturada pelo servidor sob o lock do workspace; clients também podem fornecê-la explicitamente. O plano conserva todas as versões e locks, e o preview anuncia o mapa completo.

Essa compatibilidade permite continuar editando um Object vinculado com o snapshot atual da UI quando um guard lê, mas não modifica, um endpoint obrigatório. Uma mudança na dependência entre proposta, review e execução altera o plano e invalida a aprovação; a execução não reaproveita aprovação nem faz rebase automático das versões de escrita.

## Aprovação e replay

Replanejar na criação da intenção, na revisão e antes da execução. Comparar o plano pendente e as precondições, além do schema/implementação/grant e autoridade atuais. Agentes continuam requerendo review humano; comandos human-only e guards de independência/evidência permanecem executáveis.

Execução já confirmada retorna o resultado histórico antes de validar revisões antigas ou reexecutar o handler. A autoridade atual é checada contra o plano persistido. Ledgers v1 anteriores, sem plano, conservam uma declaração de autoridade histórica isolada em `legacy_replay.py`; ela não participa de novas escritas ou reviews.

## Limites

O planner executa trabalho SQL adicional e exige handlers transacionais, sem efeitos externos diretos. Integrações externas devem consumir o outbox após commit. Esta entrega não promete otimização de consultas/locks ou benchmark de latência.

O catálogo descreve contratos de capability, não capacidades efetivas por campo/actor nem formulários completos. Seletores de criação/lifecycle no ObjectType, metadata de apresentação, runtime elegível por tipo e projeções operacionais permanecem nas próximas entregas. Não há nova migration estrutural nesta etapa nem ativação do stack publicado.
