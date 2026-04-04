# 🫀 Sofia AI — Agente de Agendamento para Cardiologia

<div align="center">

![Python](https://img.shields.io/badge/Python-3.14+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Google Calendar](https://img.shields.io/badge/Google_Calendar-API_v3-4285F4?style=for-the-badge&logo=google-calendar&logoColor=white)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Evolution_API_v2-25D366?style=for-the-badge&logo=whatsapp&logoColor=white)

**Assistente virtual com IA para clínicas de cardiologia**
*Agendamentos, lembretes e sincronização de calendário — 100% automatizados no WhatsApp.*

</div>

---

## 📌 Índice

- [Visão Geral](#-visão-geral)
- [Fluxo de Ponta a Ponta](#-fluxo-de-ponta-a-ponta)
- [Arquitetura do Sistema](#-arquitetura-do-sistema)
- [Módulos e Responsabilidades](#-módulos-e-responsabilidades)
- [Google Calendar Sync](#-google-calendar-sync)
- [Segurança e Tratamento de Erros](#-segurança-e-tratamento-de-erros)
- [Jobs e Automações Internas](#-jobs-e-automações-internas)
- [Banco de Dados](#-banco-de-dados)
- [Tecnologias Utilizadas](#-tecnologias-utilizadas)
- [Configuração do Ambiente](#-configuração-do-ambiente)
- [Regras de Arquitetura Modular](#-regras-de-arquitetura-modular)

---

## 🧠 Visão Geral

A **Sofia** é uma agente de atendimento conversacional integrada ao WhatsApp via **Evolution API v2**. Ela opera como recepcionista virtual do consultório do Dr. João (Cardiologista), gerenciando pacientes, consultas e sincronizando tudo com o **Google Calendar** — sem nenhuma intervenção humana.

### ✅ Funcionalidades Principais

| Feature | Descrição |
|---|---|
| **Cadastro Inteligente** | Coleta Nome, CPF (validado matematicamente), Data de Nascimento, CEP (lookup automático via ViaCEP), Endereço e Convênio |
| **Agendamento Conversacional** | Busca os próximos horários livres no banco, apresenta menus numerados e confirma o agendamento |
| **Cancelamento Múltiplo** | **(Novo)** Permite ao paciente selecionar e cancelar uma ou mais consultas simultaneamente via menu numerado |
| **Remarcação** | Cancela a consulta existente e abre novo fluxo de agendamento |
| **Sincronização Google Calendar** | Worker interno cria/deleta eventos automaticamente a cada 2 minutos sem depender de Realtime/Webhooks |
| **Lembretes Automáticos** | Notifica o paciente 24h e 2h antes da consulta via WhatsApp e E-mail |
| **Envio de Exames** | Recebe mídias (PDF, imagens) pelo WhatsApp e as armazena |
| **Gestão de Inatividade** | Sessões inativas por +5 min são encerradas automaticamente |
| **Classificador de Contexto** | Bloqueia mensagens fora do contexto médico (assuntos não relacionados) e filtra ofensas |
| **Regra de Ouro** | Após 2 erros consecutivos, o bot escala para atendimento humano |

---

## 🔄 Fluxo de Ponta a Ponta

```
[Paciente envia mensagem no WhatsApp]
         │
         ▼
[Evolution API → POST /webhook/whatsapp]
         │
         ▼
[main.py] Identifica JID (número WA) e roteador de sessão
         │
         ├─ Sessão NOVA ──────────────────────────────┐
         │                                            │
         │  [Supabase] Busca paciente por phone       │
         │       ├─ ENCONTRADO → step: ask_update     │
         │       └─ NÃO FOUND  → step: ask_is_patient │
         │                                            │
         └─ Sessão ATIVA ─────────────────────────────┘
                  │
                  ▼
         [Classificador de Contexto] (LLM ou RegEx)
                  │ off_topic/offensive → mensagem de aviso e retorna
                  │ ok → continua
                  ▼
         [Roteamento por Step Atual]
           ┌─────────────────────────────────────────────┐
           │ ask_is_patient / register_* → handle_onboarding │
           │ menu / waiting_for_exams   → handle_menu    │
           │ scheduling / cancel_*      → handle_scheduling │
           └─────────────────────────────────────────────┘
                  │
                  ▼
         [Handler executa a lógica]
                  │
                  ▼
         [Evolution API] → Envia resposta ao paciente
                  │
                  ▼ (ao confirmar agendamento/cancelamento)
         [Supabase] UPDATE/INSERT na tabela `appointments`
                  │
                  ▼ (até 2 minutos depois)
         [sync_calendar_job] Detecta mudança no banco
                  │
                  ▼
         [Google Calendar API] Sincronia de eventos (Cria/Deleta)
```

---

## 🏗️ Arquitetura do Sistema

```
projeto_agendamento/
├── src/
│   ├── main.py                  # 🎼 Maestro: rotas, scheduler, lifespan, roteamento
│   ├── config/
│   │   └── messages.py          # 📝 Todas as constantes de texto do bot
│   ├── handlers/                # 🧠 Cérebros dos fluxos conversacionais
│   │   ├── onboarding.py        #    Cadastro, CPF, CEP, convênio
│   │   ├── scheduling.py        #    Agendamento, remarcação e cancelamento múltiplo
│   │   ├── menu.py              #    Menu principal e opções
│   │   └── helpers.py           #    Funções auxiliares compartilhadas
│   ├── database/
│   │   └── client.py            # 🗄️ Singleton Supabase + todos os métodos CRUD
│   ├── services/
│   │   ├── google_calendar.py   # 📅 Singleton Google Calendar API (OAuth2 + auto-refresh)
│   │   ├── jobs.py              # ⏰ APScheduler: lembretes, inatividade, sync calendar
... (rest of tree)
```

*(Continuação do README com detalhes técnicos já configurados)*
