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
           │ scheduling                 → handle_scheduling │
           └─────────────────────────────────────────────┘
                  │
                  ▼
         [Handler executa a lógica]
                  │
                  ▼
         [Evolution API] → Envia resposta ao paciente
                  │
                  ▼ (ao confirmar agendamento)
         [Supabase] INSERT na tabela `appointments`
                  │
                  ▼ (até 2 minutos depois)
         [sync_calendar_job] Detecta nova linha sem google_event_id
                  │
                  ▼
         [Google Calendar API] Cria evento com horário correto (America/Sao_Paulo)
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
│   │   ├── scheduling.py        #    Agendamento e remarcação
│   │   ├── menu.py              #    Menu principal e opções
│   │   └── helpers.py           #    Funções auxiliares compartilhadas
│   ├── database/
│   │   └── client.py            # 🗄️ Singleton Supabase + todos os métodos CRUD
│   ├── services/
│   │   ├── google_calendar.py   # 📅 Singleton Google Calendar API (OAuth2 + auto-refresh)
│   │   ├── jobs.py              # ⏰ APScheduler: lembretes, inatividade, sync calendar
│   │   ├── calendar_sync.py     #    Handler de eventos Supabase → Google Calendar
│   │   ├── realtime_sync.py     #    WebSocket Supabase Realtime (fallback)
│   │   ├── evolution.py         #    Cliente Evolution API (envio de mensagens)
│   │   ├── email_service.py     #    Envio de lembretes por e-mail
│   │   └── sessions.py          #    Gerenciamento da memória de sessões em RAM
│   ├── agents/
│   │   ├── graph.py             # 🤖 Grafo LangGraph para reasoning complexo
│   │   ├── classifier.py        #    Classificador de contexto e ofensas
│   │   ├── tools.py             #    Ferramentas do agente IA
│   │   └── state.py             #    Schema do estado compartilhado
│   ├── scripts/
│   │   ├── authorize_google.py  # 🔑 Gera token.json via OAuth2
│   │   ├── sync_existing_appointments.py  # Migração: sincroniza consultas antigas
│   │   └── fix_calendar_timezone.py       # Utilitário: corrige eventos com fuso errado
│   └── logs/
│       └── agent.log            # 📋 Log estruturado de toda a operação
├── supabase/
│   ├── schema.sql               # DDL completo do banco
│   ├── migration_v2.sql         # Migrações incrementais
│   └── add_google_event_id.sql  # ALTER TABLE para coluna de sync
├── .env                         # ⚠️ Variáveis secretas (NÃO commitado)
├── token.json                   # ⚠️ Token OAuth Google (NÃO commitado)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 📦 Módulos e Responsabilidades

### `main.py` — O Maestro
Não contém lógica de negócio. Apenas:
- Declara as rotas FastAPI (`/webhook/whatsapp`, `/webhook/supabase`)
- Inicializa o `lifespan` (scheduler + listener realtime)
- **Roteia** cada mensagem para o handler correto com base no `conversation_step` da sessão
- Implementa a **Regra de Ouro**: após 2 erros consecutivos, escala para humano

### `handlers/onboarding.py` — Fluxo de Cadastro
Gerencia 12+ etapas de cadastro:
- Validação matemática de CPF com `validate_docbr`
- Lookup de endereço por CEP via API ViaCEP
- Detecção de cadastros duplicados
- Troca de número de telefone vinculado
- Confirmação interativa de dados antes de salvar

### `handlers/scheduling.py` — Fluxo de Agendamento
- Busca datas disponíveis no banco com paginação (7 datas por página)
- Exibe horários livres por data selecionada
- Cancela consultas antigas no fluxo de remarcação
- Finaliza o booking com confirmação completa (valor, endereço, convênio)

### `database/client.py` — Camada de Dados
- Singleton do Supabase, instanciado uma única vez na inicialização
- Métodos: `get_patient_by_phone`, `get_patient_by_cpf`, `create_patient`, `update_patient`, `book_appointment`, `cancel_appointment`, `find_next_available_dates`, `get_hours_menu`
- Toda comunicação com o banco passa exclusivamente por aqui

### `services/google_calendar.py` — Integração Google
- Classe `GoogleCalendarService` (Singleton)
- Auto-renova o `access_token` usando o `refresh_token` salvo em `token.json`
- Método `_strip_tz()`: remove sufixo UTC (`Z` ou `+00:00`) antes de enviar ao Google, garantindo que o horário seja interpretado como `America/Sao_Paulo`
- Operações: `create_event`, `update_event`, `delete_event`

### `agents/classifier.py` — Segurança Conversacional
- Detecta mensagens fora do contexto médico (`off_topic`)
- Detecta ofensas e linguagem inapropriada (`offensive`)
- Usa RegEx determinístico + LLM como fallback para ambiguidades

---

## 📅 Google Calendar Sync

### O Problema Resolvido
O Supabase Free não mantém o Realtime (WebSocket) ativo de forma consistente. A solução implementada **não depende de Realtime**: um Worker interno faz polling a cada 2 minutos.

### Como Funciona

```
A cada 2 minutos (sync_calendar_job):

QUERY 1: SELECT * FROM appointments WHERE status = 'scheduled' AND google_event_id IS NULL
  └─ Para cada resultado → Cria evento no Google Calendar → Salva google_event_id no banco

QUERY 2: SELECT * FROM appointments WHERE status = 'cancelled' AND google_event_id IS NOT NULL
  └─ Para cada resultado → Deleta evento do Google Calendar → Limpa google_event_id no banco
```

### Tratamento de Fuso Horário
O horário no Supabase é salvo como UTC (`2026-04-08T09:00:00+00:00`). Para o Google Calendar exibir `09:00` (e não `06:00`), o serviço:
1. Remove o sufixo de timezone (`+00:00` ou `Z`)
2. Envia o campo `timeZone: 'America/Sao_Paulo'` explicitamente
3. O Google Calendar interpreta `09:00` como horário de Brasília

### Comportamentos por Ação no Banco

| Ação | Resultado no Google Calendar | Tempo |
|---|---|---|
| Nova consulta via WhatsApp | Evento criado automaticamente | Até 2 min |
| Cancelamento via bot | Evento deletado automaticamente | Até 2 min |
| Mudar `status` para `cancelled` no banco | Evento deletado automaticamente | Até 2 min |
| Deletar linha direto no banco | ⚠️ Evento permanece (ID se perde) — prefira cancelar | — |
| Agendar nova consulta diretamente no banco | Evento criado automaticamente | Até 2 min |

> **💡 Boas Práticas:** Sempre mude o `status` para `cancelled` em vez de deletar linhas. O Worker consegue limpar o calendário apenas quando o registro existe no banco.

---

## 🛡️ Segurança e Tratamento de Erros

### Regra de Ouro
Após **2 erros consecutivos** em qualquer fluxo (entrada inválida, erro de API, etc.), o bot para de tentar resolver sozinho e:
1. Envia mensagem de escalonamento para o paciente
2. Muda o estado para `waiting_golden_rule_response`
3. Aguarda o paciente escolher: voltar ao menu ou encerrar

### Gestão de Sessão
- Sessões são armazenadas **em memória RAM** (`active_sessions` dict) por performance
- Sessões inativas por **5 minutos** são encerradas automaticamente pelo `check_inactivity_job`
- Sessões inativas por **15 minutos** são detectadas no `process_message` como failsafe
- `fromMe: true` é filtrado no webhook para evitar loop de auto-resposta

### Autenticação de Webhooks
O endpoint `/webhook/supabase` valida um `x-webhook-secret` no header, configurável via variável de ambiente `SUPABASE_WEBHOOK_SECRET`.

---

## ⏰ Jobs e Automações Internas

O bot usa **APScheduler (AsyncIOScheduler)** com 3 jobs assíncronos:

| Job | Frequência | Responsabilidade |
|---|---|---|
| `check_inactivity_job` | A cada **30 segundos** | Encerra sessões inativas há +5 minutos |
| `sync_calendar_job` | A cada **2 minutos** | Cria/deleta eventos no Google Calendar conforme o banco |
| `send_reminders_job` | A cada **60 minutos** | Envia lembretes de consulta 24h e 2h antes (WhatsApp + E-mail) |

---

## 🗄️ Banco de Dados

### Tabelas principais

| Tabela | Função |
|---|---|
| `patients` | Dados dos pacientes (nome, CPF, CEP, e-mail, convênio, JID) |
| `appointments` | Consultas agendadas (`status`, `start_time`, `end_time`, `google_event_id`) |
| `doctors` | Cadastro dos médicos |
| `business_hours` | Horários de funcionamento para cálculo de disponibilidade |
| `blocked_slots` | Horários bloqueados manualmente pelo médico |
| `patient_exams` | Arquivos de exames enviados pelo paciente |

### Coluna `google_event_id`
Adicionada em `appointments` para manter o vínculo bidirecional entre o banco e o Google Calendar. O Worker usa essa coluna para evitar duplicatas e para saber qual evento deletar quando uma consulta é cancelada.

---

## 🧰 Tecnologias Utilizadas

| Tecnologia | Versão | Papel |
|---|---|---|
| **Python** | 3.14+ | Linguagem principal |
| **FastAPI** | 0.115+ | Framework web / webhook receiver |
| **Uvicorn** | Latest | Servidor ASGI de produção |
| **Supabase** | Client 2.x | Banco de dados PostgreSQL (BaaS) |
| **Google Calendar API** | v3 | Integração de agenda |
| **Evolution API** | v2 | Gateway de mensageria WhatsApp |
| **APScheduler** | 3.x | Jobs periódicos assíncronos |
| **LangGraph** | Latest | Grafo de raciocínio do agente IA |
| **Groq / OpenAI** | Latest | LLM para classificação e NLP |
| **validate_docbr** | Latest | Validação matemática de CPF |
| **Docker** | Latest | Containerização |

---

## ⚙️ Configuração do Ambiente

### Pré-requisitos
- Python 3.14+
- Docker e Docker Compose
- Conta no Supabase (plano Free funciona)
- Projeto no Google Cloud com Calendar API ativada
- Instância da Evolution API v2 configurada

### 1. Variáveis de Ambiente
Crie um arquivo `.env` na raiz com:
```env
# ── Supabase ───────────────────────────────────────
SUPABASE_URL=https://SEU_PROJETO.supabase.co
SUPABASE_API_KEY=sua_anon_key
SUPABASE_WEBHOOK_SECRET=uma_chave_secreta_qualquer

# ── Evolution API (WhatsApp) ───────────────────────
EVOLUTION_INSTANCE_URL=http://localhost:8081
EVOLUTION_INSTANCE_NAME=principal_v2
EVOLUTION_API_KEY=sua_api_key

# ── Google Calendar (GoogleCalendarService) ────────
# Configure via src/scripts/authorize_google.py
# O token.json será gerado automaticamente.

# ── Inteligência Artificial ────────────────────────
GROQ_API_KEY=sua_groq_key
OPENAI_API_KEY=sua_openai_key  # opcional, se usar OpenAI
```

### 2. Autenticação Google Calendar
```bash
# Coloque o credentials.json do Google Cloud na raiz e rode:
python src/scripts/authorize_google.py
# Abrirá o navegador para autorizar → token.json será gerado
```

### 3. Banco de Dados
```bash
# Execute o schema no painel SQL do Supabase:
# Cole o conteúdo de supabase/schema.sql e execute
```

### 4. Iniciar o Servidor
```bash
# Desenvolvimento (com auto-reload)
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Produção (Docker)
docker-compose up -d
```

### 5. Migrar Consultas Existentes (primeira vez)
```bash
# Sincroniza todos os agendamentos do banco para o Google Calendar
python src/scripts/sync_existing_appointments.py
```

---

## 📏 Regras de Arquitetura Modular

Este projeto obedece às seguintes convenções para garantir que o código permaneça limpo, testável e escalável:

### 🚀 Princípio: `main.py` como Maestro
O arquivo principal **nunca** contém lógica de negócio pesada, SQL dieto ou textos de mensagem. Sua responsabilidade é exclusivamente:
1. Declarar as rotas (webhooks)
2. Inicializar o scheduler e o lifespan
3. Rotear mensagens para os handlers corretos

### 📂 Onde cada coisa mora

| Camada | Pasta | Regra |
|---|---|---|
| **Textos** | `src/config/messages.py` | Nenhum texto hardcoded nos handlers |
| **Fluxos** | `src/handlers/` | Um arquivo por grande fluxo (`onboarding.py`, `scheduling.py`) |
| **Banco** | `src/database/client.py` | Todo SQL centralizado aqui; handlers nunca acessam o banco diretamente |
| **APIs Externas** | `src/services/` | Cada integração isolada (Google, Evolution, E-mail) |
| **IA** | `src/agents/` | LangGraph, prompts e classificadores |

### 🧪 Gatilho de Modularização
Quando o `main.py` ultrapassar **500 linhas**, a lógica excedente **deve** ser extraída para um handler ou service.

---

## 📋 Scripts Utilitários

| Script | Comando | Função |
|---|---|---|
| Autorizar Google | `python src/scripts/authorize_google.py` | Gera `token.json` via OAuth2 |
| Sincronizar histórico | `python src/scripts/sync_existing_appointments.py` | Envia consultas sem evento para o Google Calendar |
| Corrigir fuso horário | `python src/scripts/fix_calendar_timezone.py` | Recria eventos com timezone errado |

---

*Documentação mantida pela equipe. Atualizar sempre que novas funcionalidades forem adicionadas.*
