# AGENTS.md

## Projeto

WoFF_Mate é uma aplicação Python para Windows que processa dados do WoFF e mantém uma base SQLite persistente.

## Regras

- Preserve compatibilidade com Python 3.10.
- Não altere dados de campanha sem backup.
- Toda mudança de schema exige teste de migração e reabertura.
- Não versione config.json, bancos, logs, builds ou dados pessoais.
- Não misture refatoração e nova funcionalidade na mesma PR.
- Use imports relativos dentro do pacote woff.
- Adicione testes de regressão para correções de bugs.
- Execute toda a suite antes de concluir.
- Não faça merge direto em main.

## Conclusão

Uma tarefa termina quando os critérios da issue foram atendidos, os testes passaram, o diff foi revisado e uma PR draft foi aberta.