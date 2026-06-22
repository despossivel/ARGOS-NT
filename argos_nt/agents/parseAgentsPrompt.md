
### Prompt de Engenharia: Sanitização de Outputs (Parser Agent)

> "Copilot, o relatório final está completamente poluído porque os outputs brutos do terminal estão sendo passados sem tratamento. O relatório está incluindo barras de progresso, loaders, banners de ferramentas, rodapés e erros de rede. Precisamos que o **Parser Agent** (`ModuleParser`) atue como um filtro cirúrgico.
> **Instruções estritas para a refatoração:**
> 1. Altere o prompt do sistema do `ModuleParser` (em `agents/parser_agent.py`) para que ele aja como um **Sanitizador de Dados Brutos**.
> 2. Diga explicitamente no prompt: *'Sua única função é ignorar todo o lixo de interface do terminal (como loaders, barras de progresso `[###---]`, banners em ASCII, mensagens de erro de timeout ou avisos do sistema). Você deve extrair exclusivamente dados válidos e confirmados de inteligência.'*
> 3. Crie regras de extração específicas para cada ferramenta. Por exemplo:
> * **Para o Holehe:** Extraia apenas o domínio do site e o status se a conta existe (ex: `{"site": "instagram.com", "status": "exists"}`). Ignore sites onde a conta não foi encontrada ou deu erro.
> * **Para o h8mail:** Extraia apenas o nome do vazamento e a senha vazada, se houver. Ignore logs de inicialização.
> * **Para o Maigret/Sherlock:** Extraia apenas as URLs confirmadas onde o perfil foi encontrado com sucesso.
> 
> 
> 4. O `ModuleParser` deve retornar esse resultado em um formato JSON estrito e limpo.
> 5. Altere a função de salvamento no `GraphController` para que **apenas esses dados lapidados** extraídos pelo Parser sejam injetados nos nós e propriedades do Neo4j. Nada de texto bruto do terminal deve entrar no banco de dados.
> 
> 
> Refatore o código agora para garantir que a esteira de dados passe por essa lapidação automática antes de qualquer persistência ou geração de relatório."

