# RADAR Core U1 — ADR das entregas 3B/3C

**Data:** 06/10/2026, America/Bahia. **Escopo:** segunda e terceira entregas da fase 3. 3B, criação por capability (C02); 3C, lifecycle declarativo limitado (C01). A entrega 3A ([ADR](CORE_U1_PHASE_03_ADR.md)) forneceu o registro de capabilities e o plano transacional de efeitos usados aqui.

## Descritores no schema do workspace

`ObjectType.rules` passa a ter três seções fechadas: `invariants` (U0), `creation` e `lifecycle`. Chaves desconhecidas são recusadas. Não há coluna nova: a seção vive no mesmo JSON versionado que já integra o fingerprint de aprovação, a revisão de schema, a instalação e o upgrade com diff de três vias da fase 2.

Os descritores **selecionam** código registrado; não registram handlers, scripts ou regras arbitrárias. A validação ocorre em duas camadas:

- **Estrutural**, ao salvar o tipo: formato, capability registrada, guard registrado e restrição de tipo declarada pela própria capability/guard.
- **Efetiva**, em toda edição/upgrade de metadata (`validate_effective_schema`) e em toda leitura de execução: propriedade de estado enum ativa, estados declarados, inicial não terminal, carimbos datetime opcionais e não derivados, requisitos do perfil de criação. Uma alteração de definição que invalide o lifecycle é recusada (por exemplo, tornar o estado inicial terminal ou retirar o campo de carimbo).

Um descritor inválido gravado fora desse caminho falha fechado: a criação ou transição é recusada, sem fallback por nome.

## 3B — Criação por capability

`rules.creation.capability` escolhe uma capability com `CreationProfile` registrado: `CreateObject` (genérica e padrão, quando a seção falta), `CreateAction`, `RegisterRisk` ou `CreateDecision`. O perfil declara os tipos que aceita, o serializer de parâmetros, os campos de fachada que são propriedades, as propriedades mínimas não vazias, os estados iniciais aceitos e o handler de efeitos compostos.

- `CreateObject` recebe `properties`, validadas contra as `PropertyDefinition` ativas do workspace, e `parameters`, validados pelo serializer do perfil selecionado. Referências como owner, executores, evidências e Objects ameaçados deixam de ser propriedades. Uma propriedade válida extra em tipo semeado é aceita sem ampliar serializers fechados.
- `CreateAction`, `RegisterRisk` e `CreateDecision` preservam seus inputs e passam a ser fachadas do mesmo caminho (`create_declared`). Ganham `properties` opcional para propriedades extras e só operam se o tipo do workspace selecionar aquela capability.
- `create_typed_object`, inclusive nas criações internas de AddEvidence, CaptureIssue e RecordMeasurement, exige que a capability em uso seja a declarada pelo tipo. Nenhum caller escolhe um caminho que contorne a política do tipo; o administrador pode mudá-la por command auditado.
- O estado inicial vem de `lifecycle.initial`, persistido no workspace, e é gravado explicitamente. O perfil limita os iniciais aceitos (`todo`, `identified`, `proposed` para as fachadas); um descritor incompatível é recusado na configuração. Status explícito diferente do inicial continua recusado na criação.
- A composição na autoridade (CreateObject + capability declarada + LinkObjects), as referências versionadas e o plano de efeitos da 3A continuam iguais.

**Compatibilidade:** `parameters` e `properties` não têm default. Inputs omitidos geram o mesmo `validated_data` e o mesmo `intent_hash` das intenções anteriores. Clientes que enviavam referências compostas dentro de `CreateObject.properties` passam a receber erro de propriedade desconhecida e devem usar `parameters`; a UI atual não usa esse formato. O replay de ledgers v1 sem plano conserva a especialização congelada por tipo em `legacy_replay.py`.

## 3C — Lifecycle declarativo limitado

```json
{
  "property": "status",
  "initial": "todo",
  "transitions": [
    { "from": ["todo"], "to": "in_progress" },
    {
      "from": ["todo", "in_progress", "waiting"],
      "to": "done",
      "capability": "CompleteAction",
      "stamp": "completed_at"
    }
  ]
}
```

- Os estados são as choices da definição enum; os terminais vêm de `config.terminal`. Transições são pares explícitos, sem wildcard, sem laço e sem completar pares automaticamente. A ausência de transição é bloqueio. Sair de estado terminal exige transição declarada a partir dele (Person `inactive → active`).
- `capability` (padrão `UpdateObject`) referencia capabilities que declaram `lifecycle_types`: `UpdateObject` (qualquer tipo), `CompleteAction` (action), `ReviewObject` (qualquer tipo, com `parameter` igual à disposition do input) e `DelegateAction` (commitment). `guard` referencia um guard registrado da mesma capability e tipo; hoje, `decision_approval` (decision, human-only). `stamp` grava o horário do command em um datetime protegido.
- **Um ponto de aplicação:** `governed_patch` roda no writer comum `patch_properties`. Toda escrita de propriedade (UpdateObject, endpoints de propriedade, compatibilidade Python, primitives, runtime e handlers internos) exige a transição declarada para a capability do command corrente. Transição com guard exige que o handler tenha executado o guard registrado no mesmo contexto. O carimbo é gerado pelo engine e recusado como input; campo de estado e carimbos não podem ser removidos.
- Handlers especializados leem do lifecycle o alvo e os estados de origem: CompleteAction (alvo e origem), ReviewObject (mapa de disposition antes fixo em `operations.py`), DelegateAction (superação de Commitment) e o teste de estado ativo da delegação (terminais da definição). Reaplicar um resultado não terminal é idempotente, como `accepted → accepted`; estados terminais continuam exigindo saída declarada.
- A política human-only e as referências dinâmicas de UpdateObject derivam do guard do estado-alvo pedido, **independentemente do estado atual**. O planner observa a política antes e depois de executar o handler sob savepoint; ela precisa ser a mesma nas duas observações.
- Sem lifecycle, um enum chamado `status` continua sendo propriedade comum e não ganha semântica pelo nome. A validação de cardinalidade mínima da U0 continua usando `status` nesses tipos, por conservadorismo.

Guards especializados que não são transições permanecem tipados em código: imutabilidade da Decision tomada, observações de Indicator só por RecordMeasurement e imutabilidade de evidência usada. Nenhum desses guards depende de tabela de transição por nome.

## Migração e ativação

`0013_type_descriptors` é migration de dados. Instala nos tipos semeados existentes uma cópia **congelada** dos descritores do pacote, cuja igualdade com o pacote atual é verificada por teste; tipos que já tenham seção local são preservados. Também atualiza a base instalada das linhas geridas e incrementa a revisão de schema, o que invalida formulários, caches e aprovações pendentes. O `package_hash` não muda; o upgrade explícito seguinte reconcilia o hash sem mudanças de metadata. A reversão remove as seções, inclusive customizações locais, porque o código anterior as recusa; exportar antes de reverter. Fatos, IDs e histórico não são reescritos.

As tabelas do pacote reproduzem exatamente `ORDINARY_TRANSITIONS` e declaram os caminhos especializados que antes estavam em branches por tipo. `RULES_REVISION` passa a `2.1.u1.3c`; o digest de implementação já invalidava propostas pendentes sob o código anterior.

## Limites

Não há builder de tipos ou lifecycle com UI, nem migração automática de fatos. Tipos customizados usam o perfil simples (transições por UpdateObject e dispositions de ReviewObject); workflows arbitrários, guards definidos por metadata e novos handlers especializados ficam fora. A apresentação das ações e transições disponíveis por actor é C20 (fase 4); identidade de runtime para tipos customizados é C19 (fase 5); o critério do Today continua em código.
