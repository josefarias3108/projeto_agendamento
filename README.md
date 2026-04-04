# 🏥 Sofia AI - Agente Inteligente de Cardiologia 🫀

![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)
![Supabase](https://img.shields.io/badge/Database-Supabase-green.svg)
![Google Calendar](https://img.shields.io/badge/Sync-Google_Calendar-yellow.svg)
![Evolution API](https://img.shields.io/badge/API-Evolution_v2-orange.svg)

A **Sofia** é uma assistente virtual avançada projetada para automatizar o atendimento de clínicas cardiológicas através do WhatsApp. Ela gerencia o fluxo completo: desde o cadastro de novos pacientes até o agendamento de consultas com sincronização automática em tempo real.

---

## 📽️ O que o Robô faz? (Ponta a Ponta)

1.  **Recepção & Triagem**: Identifica se o paciente já é cadastrado através do número de telefone (JID).
2.  **Cadastro Inteligente**: Se for novo, coleta Nome, Endereço, E-mail e Convênio de forma humanizada.
3.  **Agendamento Sofia**:
    -   Consulta horários livres diretamente no banco de dados.
    -   Interpreta datas naturais (ex: "segunda às 9h", "amanhã cedo").
    -   Confirma o agendamento no Supabase.
4.  **Sincronização de Calendário**:
    -   Cria o evento no **Google Calendar** em até 2 minutos após o agendamento.
    -   Corrige automaticamente fusos horários (`America/Sao_Paulo`).
    -   Remove eventos do calendário se a consulta for cancelada no bot ou no banco.
5.  **Lembretes Proativos**: Envia notificações automáticas (WhatsApp + E-mail) 24h e 2h antes de cada consulta.
6.  **Gestão de Inatividade**: Detecta se o usuário parou de responder e encerra a sessão educadamente para liberar o fluxo.

---

## 📏 Regras de Arquitetura Modular

Este projeto segue rigorosamente o padrão de organização para garantir escalabilidade e limpeza:

### 🚀 Princípio Fundamental: `main.py` como Maestro
O arquivo principal apenas orquestra o fluxo, gerencia sessões e roteia mensagens. **Zero lógica de negócio pesada ou SQL aqui.**

### 📂 Estrutura de Pastas
*   `src/config/`: Textos centrais (`messages.py`) e variáveis globais (`settings.py`).
*   `src/handlers/`: Cérebros dos fluxos (ex: `scheduling.py`, `onboarding.py`). Cada arquivo cuida de um processo específico.
*   `src/database/`: Singleton `client.py` com métodos CRUD. **Proibido SQL direto nos handlers.**
*   `src/services/`: Encapsula APIs externas (Evolution API, Google Calendar, E-mails).
*   `src/agents/`: Inteligência Artificial (LangGraph e Classificadores Groq/OpenAI).

---

## 🛠️ Tecnologias Utilizadas

- **Linguagem**: Python 3.14+
- **Database**: Supabase (PostgreSQL)
- **Mensageria**: Evolution API v2 (WhatsApp)
- **Calendário**: Google Calendar API v3
- **IA/NLP**: LangGraph, Groq, OpenAI
- **Agendamento Interno**: APScheduler (verificação de inatividade e sync de calendário)

---

## 🚀 Como Rodar o Projeto

### Pré-requisitos
- Docker & Docker Compose (Recomendado)
- Credenciais do Google Cloud (`credentials.json`)
- API Key da Evolution API

### Configuração
1.  Crie um arquivo `.env` na raiz conforme o modelo abaixo:
    ```env
    # Supabase
    SUPABASE_URL=https://...
    SUPABASE_API_KEY=...
    
    # Evolution API
    EVOLUTION_INSTANCE_URL=...
    EVOLUTION_API_KEY=...
    
    # AI Keys
    GROQ_API_KEY=...
    OPENAI_API_KEY=...
    ```
2.  Inicie os serviços:
    ```bash
    docker-compose up -d
    ```

### Monitoramento
O robô agora conta com um **Worker de Sincronização Robusto**:
- Ele monitora a tabela `appointments` a cada 2 minutos.
- Garante a sincronização mesmo que os Webhooks/Realtime falhem.

---
*Documentação atualizada em: 04/04/2026*
*Responsável: Antigravity AI*
