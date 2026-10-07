# 0.3B — Decisões do Semantic Model

Referência normativa: JMR_RADAR_ONTOLOGY/ontology/core.yaml, Core 3.2.0. Decisões fechadas antes de gerar a migration.

## Storage e validação

PropertyDefinition pertence a workspace/ObjectType; PropertyValue pertence a workspace/Object e referencia uma definição. Um JSONB por valor guarda o escalar/lista tipado, sem colunas EAV por tipo nem um documento opaco de propriedades no Object. Unicidade parcial (Object, definição) entre valores ativos; índice (workspace, definição) prepara filtros. Sem GIN antecipado: filtros de alta escala poderão usar índices de expressão por definição com evidência de consultas reais.

Tipos: string, string_list, number, integer, boolean, enum, date, datetime, email, uri e user. Não há coerção silenciosa de strings/bools para números. Datas ISO; datetime com timezone; enum fechado; min/max; user deve ser humano ativo membro do workspace. Null não é valor: remover usa command próprio. Valores default são persistidos no create e materializados para Objects legados por command lazy, preservando creator e incrementando versão apenas quando há mudança. GET de valores lê defaults efetivos, sem escrever Objects.

Seed mínimo: objective/project/decision/action/risk (0.3A) e person para ownership; status e atributos desses seis tipos vêm do snapshot normativo, sem inventar vocabulários. Owner é owned_by → Person, não um campo user concorrente. Person não equivale a db.User. O suporte user existe para definições futuras, mas não é semeado como ownership.

## Relações

RelationType pertence ao workspace, com labels forward/reverse, listas de chaves de tipos source/target, allowed_pairs, cardinalidade outgoing 0..1/0..n e self-link explícito. Relation é uma aresta direcionada; backlink é consulta à mesma aresta, sem duplicar o inverso. Unicidade parcial (workspace, tipo, source, target); índices por workspace/source e workspace/target.

O snapshot semeia apenas links cujo domínio e codomínio intersectam os seis tipos do slice. Os domínios completos são preservados como configuração. `creates.allowed_pairs` é obrigatório: Decision→Action não autoriza Decision→Risk. `relates_to` permite self-link conforme ontologia; os demais não. Cardinalidade serializada travando Objects em ordem UUID; ambas as versões incrementam uma vez por alteração, incluindo self-link. Um retry de criação da mesma aresta devolve a existente sem incrementar versões.

Remoção de valor/relação é soft delete transacional com updated_by explícito; creator preservado, versões incrementadas. Recriação produz nova identidade e mantém tombstone. Hard delete continua bloqueado. Objects/tipos/definições inativos ou excluídos não são endpoints válidos. Trocar ObjectType é bloqueado se houver valores ou relações ativos, evitando invalidar silenciosamente o esquema. Não há exclusão de Object/tipo/definição neste slice.

## Divergências e limites

SUPPORTS é alias de advances. CREATES e THREATENS correspondem a creates e threatens. Decision AFFECTS Project não existe no core: affects do pack technology só liga management_item/action a ativos TI. Não semear relação contraditória. Para 0.5, ligar Project→Decision por contains (consultável como contained_in), ou aprovar extensão normativa em trabalho posterior. Esta diferença deve ficar visível no roadmap.

Workspace é o limite de segurança herdado de 0.3A; company/manager scope, grants/policies, action_types operacionais, findings/regras de metodologia, pacotes TI, histórico completo de provenance e builders ficam nas fases posteriores. Este slice é um subconjunto estrutural da ontologia, não implementação integral do runtime normativo.

APIs internas de sessão, views finas e commands com Actor; seed lazy/idempotente sob lock de Workspace, sem Project do Plane. UI genérica e cenário visual ficam em 0.4/0.5; nenhum agent/event/outbox/graph.

## Invariantes estruturais do subconjunto

RADAR-E011 é validada nas duas direções de edição: Objective.due_date ≥ start_date. RADAR-E013 é mantida atomicamente: editar likelihood/impact deriva score com o mesmo Actor e um único incremento de Object.version; editar score manualmente só aceita o produto vigente. A snapshot inclui os checks normativos dessas classes. Identidade UUID e workspace continuam contratos do Core relacional 0.3A; não são reescritos para o formato Markdown da ABox.
