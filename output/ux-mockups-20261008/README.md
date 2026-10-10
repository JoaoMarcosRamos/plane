# Mockups de UX do RADAR — 10/10/2026 (quarta rodada)

Mockups navegáveis da visão em `RADAR_UX_VIEW`, feitos com os componentes do Plane e dados fictícios. Nada chama a API do RADAR, o agente ou o banco: o estado vive num store MobX local e volta ao início quando a página recarrega. A análise que motivou esta rodada está em `docs/radar/UX_MOCKUP_INTEGRATION_REVIEW.md`.

A terceira rodada deixou Hoje compacto. A quarta **não muda essa apresentação**: corrige o que o mockup prometia sem poder cumprir. Desfazer desfaz só o que a ação fez; Decidir e Concluir mostram as condições reais; mensagem preparada deixa de ser fato ocorrido; o que ainda está pendente não some; os rituais seguem os horários escolhidos; o primeiro uso aceita correção e falha parcial; a Inbox mostra o que o agente faz hoje; e há navegação mobile, foco gerenciado e o item aberto na URL.

## Onde está

| Caminho                                               | Conteúdo                                                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `apps/web/components/radar/mockups/`                  | Telas, store local, dados fictícios e as regras de interação (`interaction-model.ts`, `undo.ts`) |
| `apps/web/app/(all)/[workspaceSlug]/(radar-mockups)/` | Rotas no app, com sidebar própria (Hoje, Inbox, Projetos, Pessoas)                               |
| `output/ux-mockups-20261008/preview/`                 | Preview Vite isolado, sem login nem backend. `mobile.html` mostra o preview num quadro de 390 px |
| `output/ux-mockups-20261008/screenshots/`             | Capturas desta rodada, desktop e mobile                                                          |

## Como abrir

**No app**, com o stack do RADAR no ar: `/<workspace>/radar/mockups/hoje/`.

**Sem backend**, a partir de `apps/web`:

```sh
./node_modules/.bin/vite --config ../../output/ux-mockups-20261008/preview/vite.config.ts
# http://127.0.0.1:3058/              desktop
# http://127.0.0.1:3058/mobile.html   quadro de 390 px, para ver a navegação mobile
```

Um item aberto fica na URL: `.../hoje/?item=it-xpto-decision`. Link direto, recarregar e o botão Voltar do navegador reabrem ou fecham o painel. Um link para um item que não existe mais mostra "Item não encontrado".

## Controles de demonstração

Em **Configurações**, o grupo "Apenas demonstração" mexe nos dados, no relógio e no cenário. Nada disso existe no produto.

| Controle                                            | O que mostra                                                    |
| --------------------------------------------------- | --------------------------------------------------------------- |
| Primeiro uso, com vault / sem vault                 | Hoje vazio; com o contexto importado, ou só você                |
| Restaurar dados de exemplo                          | Volta ao cenário cheio, relógio e cenário inclusive             |
| Carregando · Erro ao carregar                       | A espera e a falha, sem nunca dizer "nada pendente"             |
| Dados incompletos                                   | Aguardando e Informar não carregam; projetos ficam sem veredito |
| Somente leitura                                     | Consultar sim, alterar não                                      |
| Ir para o fim do dia · Ir para o dia seguinte       | O relógio único anda; rituais e foco reagem                     |
| Agente indisponível · Falha ao criar a próxima ação | Falha única, para ver o erro e a nova tentativa                 |

## O que cada ponto mostra

### Confiança e coerência das ações

| Ponto                      | Comportamento                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Captura    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Desfazer                   | Cada ação registra o que mudou. Desfazer reverte só esses efeitos, campo a campo, e **mantém o que veio depois**, no mesmo item ou em outros. O que foi alterado de novo fica como está, e o toast avisa "Desfeito em parte". O histórico nunca é apagado: desfazer entra como mais uma linha. Só oferece Desfazer o que o contrato permite reverter: adiar, delegar, revisar, ação de mitigação, pedido de aprovação, triagem da Inbox, captura e foco. Concluir, aprovar, devolver, registrar fatos e mudar de estado não têm Desfazer, e o toast não finge ter. Copiar mensagem não muda nada. | 05         |
| Decidir                    | Abre o exame da decisão: evidências com autor e data, a justificativa da proposta e as condições para aprovar. Quem é autor não aprova: o painel diz isso e oferece "Pedir aprovação" a quem pode (a aprovação pedida deixa a decisão "Aguardando revisão"). Sem evidência, oferece "Anexar evidência". Aprovar só habilita quando as condições são cumpridas.                                                                                                                                                                                                                                    | 02, 03     |
| Devolver, não rejeitar     | Rejeitar uma sugestão do agente continua existindo na Inbox. Numa decisão, o gesto é "Devolver para ajuste": exige o motivo e a decisão continua proposta. Não há estado "Rejeitada".                                                                                                                                                                                                                                                                                                                                                                                                             | 03         |
| Concluir                   | Registra uma evidência válida em um passo: uma já anexada (um clique) ou uma linha nova. Sem evidência, não conclui. Também vale no Fechar o dia.                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 04         |
| Seletor de estado e Kanban | Perguntam às mesmas regras dos botões. Concluído abre a evidência, Bloqueado pede o motivo, Aprovada abre Decidir; nada reabre; "Cancelado" e "Planejado" depois de iniciado são recusados com o motivo. O seletor só lista o que é possível.                                                                                                                                                                                                                                                                                                                                                     | —          |
| Mensagem preparada × fato  | "Copiar mensagem" só copia, e avisa se o navegador recusar. "Registrar cobrança realizada", "Registrar consulta realizada" e "Registrar comunicação" são ações separadas, com autor e data. A confirmação registrada pelo gestor aparece como "confirmação registrada por você", nunca como do executor.                                                                                                                                                                                                                                                                                          | 05         |
| O que continua pendente    | Risco aceito segue em acompanhamento e na fila. Decisão sem prazo aparece como "Prazo a definir". Quando duas fontes divergem sobre o prazo, os dois valores ficam visíveis, "Adiar" é recusado e o painel pede para escolher qual vale. Dado ausente ("a confirmar"), carregamento incompleto ("?", "Dados incompletos") e ausência real ("Conferido às 09:00 com todas as fontes") têm textos diferentes.                                                                                                                                                                                       | 01, 06, 09 |

### Continuidade da rotina

| Ponto                   | Comportamento                                                                                                                                                                                                                                                                                                                                                                                                                                     | Captura |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Rituais e horários      | O botão de ritual vem dos horários escolhidos no primeiro uso e do que já foi feito: abrir a partir do horário até o fechamento, fechar daí em diante, revisão semanal quando o horário dela chega numa semana sem revisão. Abrir, fechar e revisão semanal têm marcas próprias; o que foi feito no período deixa de aparecer como pendente ("Feito hoje", "Concluída em 05/10"). "Você não revisa desde…" usa a última revisão de qualquer tipo. | 14      |
| Um só relógio           | Data, hora e fuso vêm de uma referência única, que os testes movem. "Hoje", "amanhã" e "há 2 dias" andam junto.                                                                                                                                                                                                                                                                                                                                   | 14      |
| Horários não são agenda | O passo "Escolha quando revisar" guarda **preferências** ("Guardar preferências"), e o texto diz que nenhum compromisso é criado na agenda.                                                                                                                                                                                                                                                                                                       | —       |
| Foco de hoje            | O foco tem data. Dentro de Atenção, **Foco de hoje** e **Alertas** são grupos separados e sem repetição; foco cumprido aparece como "cumprido" e sai da conta; a aba e a frase "N itens precisam de você" contam exatamente as linhas que pedem ação. Num novo dia o foco antigo não vale e "Abrir o dia" volta a ser oferecido.                                                                                                                  | 01, 14  |
| Primeiro uso            | Com vault ou sem: sem vault, projetos e pessoas entram pelo nome. As pendências passam por conferência antes de criar, com tipo, pessoa, projeto e data corrigíveis. O progresso fica guardado ao sair e voltar. Cada linha tem resultado próprio; numa falha parcial só a que falhou volta a ser tentada, e **nunca duplica**. "Como saberemos" vazio fica como "a confirmar", à vista, e pode ser preenchido na linha de Resultados.            | 13      |
| Inbox do agente atual   | O agente hoje propõe **ligar dois itens que já existem** (um risco que ameaça um projeto) e **uma ação de mitigação**. São duas propostas, cada uma com revisão, evidências, edição (nova versão) e motivo de rejeição. "Aceitar as duas" são dois passos: se um falha, o outro continua valendo e só o que falta é repetido. Sugestão de risco novo e extração de reuniões aparecem como **funcionalidade futura**, sem ação.                    | 07, 08  |

### Clareza e acesso

| Ponto                        | Comportamento                                                                                                                                                                                         | Captura            |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| Quem executa e quem responde | Na linha e no painel: "Executa Carlos · Responde você".                                                                                                                                               | 01, 05             |
| "Como saberemos" completo    | A linha do resultado abre com um clique e mostra o texto inteiro, ou o campo para preencher.                                                                                                          | —                  |
| Carga registrada             | Pessoas e a revisão semanal mostram "itens registrados", sem barra, percentual ou "sobrecarga": o RADAR não sabe o esforço nem a disponibilidade.                                                     | —                  |
| Mobile                       | Abaixo de 768 px a sidebar vira uma barra inferior (Hoje, Inbox, Projetos, Pessoas, Novo), Configurações vai para o topo e o painel ocupa a tela, mantendo o Tab dentro dele. Sem rolagem horizontal. | 15, 16             |
| Foco e teclado               | Ao abrir o painel o foco vai para ele; ao fechar (Esc, botão ou Voltar) volta ao que o abriu. Linhas abrem com Enter ou Espaço. O Kanban tem o mesmo caminho pelo painel.                             | —                  |
| Cenários                     | Carregando, erro, dados incompletos, somente leitura, conflito de prazos e operação aguardando revisão.                                                                                               | 06, 09, 10, 11, 12 |

## Componentes do Plane usados

Propel: `Button`, `IconButton`, `Badge`, `Banner`, `Avatar`, `AvatarGroup`, `Tabs`, `Tooltip`, `Menu` (com grupos), `Dialog`, `Checkbox`, `Input`, `InputField`, `TextArea`, `TextAreaField`, `Collapsible`, `Shortcut`, ícones e `StateGroupIcon`. Blocks: `StateSelect`, `MemberSelect`, `DateSelect`, `PrioritySelect`, `Select`, `Breadcrumbs`, `Header`, `Row`, `EmptyStateCompact`, toasts. Do app: `SidebarNavItem`, `SidebarPropertyListItem`, `BaseListLayout` e `BaseKanbanLayout`.

## Validação

| Verificação                              | Resultado                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tsc --noEmit` em `apps/web`             | Sem erros                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `vitest --config vitest.radar.config.ts` | 211 aprovados em 23 arquivos. Os 52 do mockup cobrem: desfazer A mantendo B, conflito, criação e Inbox restaurada; inversas permitidas; condições de aprovação e evidência; conclusão com evidência; seletor e Kanban pelas regras dos botões; fato × mensagem; cópia que falha; risco aceito e decisão sem prazo; prazos divergentes; rituais por horário e período; um dia novo; foco e contadores; primeiro uso com e sem vault, correção e falha parcial sem duplicar; propostas do agente; URL; cenários |
| `oxlint`                                 | 0 erros; 29 avisos que já existiam (`sort`/`reverse` em cópias, `autoFocus` deliberado)                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `oxfmt --check`                          | Aprovado                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Navegador, desktop 1440×813              | Hoje com foco e alertas; Decidir com autor, sem evidência (anexar) e pedido de aprovação; Concluir com evidência; cobrar com cópia e registro separados; prazos divergentes; Desfazer de A com B criado depois; Inbox com as duas propostas e as prévias futuras; os cinco cenários; primeiro uso sem vault e com falha parcial e nova tentativa (3 de 3, sem duplicar); dia seguinte; link direto e recarga; sem erros no console                                                                            |
| Navegador, 390 px (`mobile.html`)        | Barra inferior, sem rolagem horizontal, painel em tela cheia, foco entra e volta, Esc fecha e limpa a URL, Voltar e Avançar fecham e reabrem o item                                                                                                                                                                                                                                                                                                                                                           |

## Limites e diferenças para o produto real

O que o mockup demonstra e o produto ainda não sustenta, por contrato ou por persistência:

- **Aprovar.** O produto exige proposta completa, evidências, aprovador habilitado e independente do autor. O mockup mostra a condição; "tomar a própria decisão" exigiria mudar o contrato de negócio, não o rótulo.
- **Concluir.** Evidência e conclusão são dois comandos hoje. "Criar a evidência e concluir de uma vez" precisa de um comando composto.
- **Reabrir e voltar de estado.** Não existe no ciclo de vida das ações. "Bloqueado" é uma projeção de "aguardando" com motivo, e decisões não têm "rejeitada".
- **Confirmação do executor.** Não há comando de aceite pelo executor. O mockup registra apenas o que o gestor diz ter recebido.
- **Desfazer.** No mockup é reversão por efeito sobre o estado local. No produto cada reversão é um comando de compensação, revalidado contra a versão atual, com autoridade e auditoria.
- **Consulta, comunicação, cobrança e foco.** Registros e preferências vivem em memória. O produto precisa persisti-los por usuário, período e versão.
- **Rituais e horários.** São preferências; não há agenda nem lembrete. O relógio é uma referência do mockup.
- **Prazos divergentes.** O mockup escolhe uma fonte em um clique; o produto precisa da projeção operacional com a origem de cada prazo.
- **Inbox.** As duas propostas reais são resolvidas em chamadas separadas, sem atomicidade; o mockup representa isso, não a garante. Sugestão de risco novo e leitura de reuniões dependem de novas capacidades do agente.
- **Primeiro uso.** O produto precisa detectar o primeiro uso, persistir o progresso e dar identificador estável a cada linha para repetir sem duplicar.
- **Pessoas, equipe e externas.** "Externa" e "organização" não são propriedades padrão de Pessoa.
- **Busca** e as outras configurações seguem fora do escopo.
- **Shell completo com login.** As rotas passaram no type check, mas não foram abertas no shell autenticado.
