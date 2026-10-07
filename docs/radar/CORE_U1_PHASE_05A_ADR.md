# RADAR Core U1 — Fase 5A: identidade e contexto

**Data:** 06/10/2026, America/Bahia. **Decisão:** C19, primeira entrega independente da fase 5. [Plano](CORE_U1_IMPLEMENTATION_PLAN.md).

## Contrato de integração

`ObjectType.rules.runtime` declara `enabled`, `identity` e `contexts`. Ausência equivale a `{"enabled": false}`. Habilitação usa apenas estratégia registrada (`dated_token_v1`) e prefixo de 2–16 caracteres maiúsculos. Contextos elegíveis são as categorias `company` e `manager`; o contexto concreto continua no binding imutável, por exemplo `company:test`.

O formato existente `PREFIX-YYYYMMDD-TOKEN` permanece. Metadata não fornece regex, código ou scripts. Os IDs são únicos por workspace, inclusive registros retirados. Nenhum ID, timestamp ou provenance existente é reescrito. Mudar formato ou restringir contextos com bindings incompatíveis exige migração explícita; desabilitar a integração é uma revogação permitida que conserva o histórico.

O opt-in não cria binding, grant ou credential. A instalação administrativa do pacote declara explicitamente os 11 tipos semeados como elegíveis; tipos adicionais começam sem integração. O administrador configura o descritor pelo command de metadata com revisão esperada e provisiona cada binding. Grants com lista explícita continuam exigindo inclusão do tipo; um grant `*` conserva a abrangência já autorizada, condicionado ao opt-in e binding explícitos.

## Writers e leitura corrente

Provisioning e efeitos compostos compartilham `bind_identity`. Uma criação composta pode montar relações após gerar a identidade: o planner e o dispatcher verificam o grafo final e revertem todos os efeitos caso o mínimo obrigatório falhe. Binding explícito de Object existente valida as relações antes de escrever.

`runtime_identities` aplica tipo/Object ativo, opt-in, estratégia registrada e categoria de contexto. Telegram e Plane usam essa mesma política, além dos grants e escopos de suas credenciais. Revogação da integração da Person invalida a autenticação dos dois canais. Nova credencial exige grant vigente, membership de escrita, Person ativa e binding no contexto; escopo explícito precisa incluir essa Person.

Capabilities e contexto anunciam a revisão efetiva. O catálogo deriva tipos elegíveis e targets do registro; dependências obrigatórias de tipo das operações também são registradas. ReviewObject aceita tipos customizados elegíveis pelo mesmo handler, com evidência, review humano e provenance. Tipos sem status não recebem status implícito. Pré-condições/fingerprint continuam invalidando intenções pendentes; replay confirmado conserva seu resultado e exige autoridade vigente.

## Migração e reversão

`0015_type_runtime` instala o descritor congelado apenas nos tipos semeados geridos, preserva descritores explícitos e atualiza a base instalada pelos IDs geridos. A base registra o default do pacote mesmo quando existe opt-out local, para preservar essa customização no merge de três vias. Revisão avança uma vez; reaplicação é idempotente. O hash do pacote só se alinha no upgrade administrativo explícito.

Antes de downgrade, exportar descritores locais: o código anterior recusa a seção runtime. A reversão remove essa seção, sem remover Objects ou identidades. A reaplicação restaura os defaults geridos; opt-outs e descritores customizados dependem da exportação para restauração. Voltar ao código antigo perde o suporte a tipos customizados no runtime e sua política nova de revogação; não é rollback funcional equivalente.

## Limites

C18 (prazo/atribuição/histórico), C13 (consultas delimitadas) e a homologação integrada continuam pendentes. Não há UI nova de provisioning nem novas estratégias de identidade. CoS conserva o protocolo v1 e o snapshot global como identificação do pacote; a seleção de tipos operacionais passa pelo schema efetivo do workspace. Sem alterações no CoS ou ativação do ambiente publicado.
