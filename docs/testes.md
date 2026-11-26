# Verificação do HelpDesk

## Execução local em 19 de novembro de 2026

O ambiente de teste executou Nginx 1.28, três processos Python independentes com Waitress e dois bancos isolados em PostgreSQL 18. O Nginx usou as regras do projeto com ajustes de porta, caminho de arquivos e endereço do gateway para o Windows. A configuração de demonstração usa PostgreSQL 16 e Gunicorn em contêineres Linux.

| Verificação | Resultado |
| --- | --- |
| Saúde de ponta a ponta | Aprovada. Nginx, gateway e serviços responderam com os bancos conectados. |
| Inicialização concorrente | Aprovada. Dois inicializadores simultâneos por banco concluíram com o bloqueio transacional. |
| Login e segurança | Aprovada. Contas válidas, senha inválida, usuário inexistente, sessão revogada, cabeçalho de escrita e restrições por perfil. |
| Ciclo do chamado | Aprovado. Abertura, escopo por usuário e técnico, atribuição, cinco estados, comentários, resolução, histórico, upload, download, SLA e relatórios. |
| Persistência | Aprovada. Usuário, chamado, histórico e anexo continuaram disponíveis após parar e recriar os processos HTTP. |
| SMTP | Aprovada em servidor local de teste. Após uma falha temporária, o envio foi reagendado e as seis mensagens esperadas foram recebidas. |
| Navegador | Aprovado em login, abertura, comentário e relatório. A visualização estreita manteve a rolagem horizontal dentro da tabela. |

A primeira rodada da suíte de integração encontrou o limite de login do Nginx. O teste passou a aguardar a janela quando recebe HTTP 429, mantendo a proteção ativa. Na segunda rodada, passaram três testes de fluxo e um teste de persistência.

## Reproduzir

Os testes em `tests/integration.py` usam a mesma URL que o navegador. Execute-os em uma instância exclusiva de teste, conforme o [README](../README.md). O workflow de integração verifica a configuração, constrói as imagens, espera os seis contêineres saudáveis e executa as fases de fluxo e persistência. A segunda fase recria também os contêineres dos bancos e reutiliza os volumes.

Disponibilidade e tempo de resposta sob carga são metas. Essa rodada não incluiu teste de carga, medição de disponibilidade em produção ou envio por provedor externo.
