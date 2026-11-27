# Skills aplicadas no HelpDesk CEUB

O HelpDesk foi desenvolvido para a disciplina de Desenvolvimento Web. Este arquivo registra as competências técnicas demonstradas e indica onde conferi-las no projeto.

| Competência | Aplicação no HelpDesk | Onde conferir |
| --- | --- | --- |
| HTML, CSS e JavaScript | Interface responsiva com CSS próprio, Tailwind CSS, Materialize e a paleta do CEUB. Requisições via Fetch. | [Frontend](frontend/) |
| APIs REST | Microsserviços em Python e Flask com métodos HTTP, JSON, upload multipart e respostas por código de status. | [Usuários](usuarios-service/) e [Chamados](chamados-service/) |
| Arquitetura distribuída | Gateway roteia as requisições. Usuários e chamados têm serviços e bancos PostgreSQL independentes. | [Gateway](gateway/) e [arquitetura](docs/arquitetura.md) |
| Persistência | SQLAlchemy, conexão via Psycopg, transações e volumes persistentes no Compose. | [Configuração do Compose](docker-compose.yml) |
| Segurança web | Sessão opaca revogável, cookie HttpOnly, permissões por perfil, cabeçalho de proteção de escrita e limites de login e anexos. | [Código compartilhado](common/) e [Nginx](frontend/nginx.conf) |
| Infraestrutura | Docker Compose, Nginx, Gunicorn, redes separadas e verificações de saúde. | [Configuração do Compose](docker-compose.yml) |
| Testes e integração contínua | Testes HTTP pelo Nginx e verificação de persistência após recriação dos contêineres. | [Teste de integração](tests/integration.py) e [workflow](.github/workflows/integration.yml) |
| Documentação de APIs | Contrato OpenAPI e Swagger UI na mesma origem da aplicação. | [Especificação](frontend/api-docs/openapi.json) |
| Git e documentação | Organização por componente, histórico de alterações, instruções locais e documentação de arquitetura. | [README](README.md) e [documentação](docs/) |

## Ferramentas de apoio

O Codex apoiou a implementação, a revisão, os testes e a documentação. As skills de documentos e PDF apoiaram os materiais acadêmicos. As skills de Render e Neon apoiaram a avaliação da infraestrutura de hospedagem.
