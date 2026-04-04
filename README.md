# 🏥 CardioBot - Agendamento Inteligente

Sistema de automação para clínicas de cardiologia integrado com WhatsApp (Evolution API), Supabase e Google Calendar.

## 🚀 Funcionalidades Atuais

- **Agendamento via WhatsApp**: Fluxo conversacional inteligente para marcação de consultas.
- **Sincronização com Google Calendar**:
    - **Criação Automática**: Novas consultas são enviadas para o calendário em tempo real (job de 2 min).
    - **Cancelamento Automático**: Consultas marcadas como `cancelled` são removidas do Google Calendar.
    - **Tratamento de Fuso Horário**: Correção automática para `America/Sao_Paulo` (horário de Brasília).
- **Lembretes Automáticos**:
    - Envio de mensagem 24h antes da consulta.
    - Envio de mensagem 2h antes da consulta.
    - Notificação via E-mail integrada.
- **Gestão de Pacientes**: Cadastro completo (Nome, Endereço, E-mail, Convênio) via chat.

## 🛠️ Arquitetura do Sistema

O projeto segue uma estrutura modular para facilitar a manutenção:

- `src/main.py`: Maestro do sistema e orquestrador dos jobs.
- `src/handlers/`: Lógica dos fluxos de conversa (Agendamento, Cadastro, etc.).
- `src/database/`: Cliente singleton do Supabase e métodos de CRUD.
- `src/services/`: Integrações externas (Google Calendar, Evolution API, E-mail).
- `src/scripts/`: Utilitários para correção de dados e migrações.

## ⚙️ Sincronização de Calendário (Modo Robusto)

O sistema utiliza um **Worker Interno** que roda a cada 2 minutos. Isso garante que, mesmo em contas gratuitas do Supabase (onde o Realtime pode falhar), a agenda do Google esteja sempre espelhada com o banco de dados.

---
*Status do Projeto: Operacional e Sincronizado.*
