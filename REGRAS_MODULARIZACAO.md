# 📏 Regras de Arquitetura Modular (Python)

Este documento estabelece o padrão de organização de código para automações e robôs, garantindo que o sistema permaneça limpo, escalável e de fácil manutenção.

---

### 🚀 Princípio Fundamental
**Mantenha o `main.py` como um Maestro.** O arquivo principal não deve conter lógica de negócio pesada, SQL ou mensagens manuais. Ele deve apenas orquestrar o fluxo, gerenciar sessões e rotear mensagens para os especialistas (Handlers).

### 📂 Estrutura de Pastas e Responsabilidades

#### 1. `src/config/`
- **messages.py**: Contém exclusivamente todas as constantes de texto (`MSG_WELCOME`, `MSG_MENU`, etc). Nunca deixe textos longos hardcoded nos handlers.
- **settings.py**: Configurações de variáveis de ambiente e globais.

#### 2. `src/handlers/` (Cérebro dos Fluxos)
- Cada grande fluxo conversacional deve ter seu próprio arquivo (ex: `onboarding.py`, `scheduling.py`, `exams.py`).
- Os handlers recebem o estado da conversa e a mensagem, processam a lógica e alteram o estado (`state`).

#### 3. `src/database/`
- **client.py**: Singleton do banco de dados (Supabase, MySQL) e todos os métodos de CRUD (`get_patient`, `save_exam`, etc).
- **Proibição:** Evite fazer chamadas diretas ao banco nos handlers; use sempre os métodos do `db_service`.

#### 4. `src/services/`
- Encapsula chamadas de APIs externas (Evolution API, envio de e-mails, processamento de pagamentos).

#### 5. `src/agents/`
- Contém a inteligência artificial: Grafos do LangGraph, Prompts de Sistema e Classificadores (verificação de contexto/ofensas).

---

### 🧪 Gatilhos para Aplicação
Sempre que um projeto começar ou quando o arquivo `main.py` ultrapassar **500 linhas**, a regra de modularização **DEVE** ser aplicada retroativamente.

### 💡 Benefícios
1. **Fácil Revisão:** Arquivos menores são lidos e corrigidos muito mais rápido.
2. **Isolamento de Erros:** Se o fluxo de agendamento parou, o fluxo de envio de exames continua funcionando por estar em um arquivo separado.
3. **Escalabilidade:** Adicionar uma nova função ao robô torna-se tão simples quanto criar um novo handler e rotear no `main.py`.
