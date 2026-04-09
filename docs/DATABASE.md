# 🗄️ Guia de Banco de Dados (Supabase)

O Sistema Sofia depende exclusivamente do **Supabase** (PostgreSQL) para gerência de histórico e agendamentos. A integridade desta arquitetura é essencial.

---

## 🏗️ Estruturas Essenciais (Migrations)

Sempre que a estrutura de banco precisar ser modificada, recomenda-se criar ou testar **migrations SQL** antes de aplicá-las via UI dashboard do Supabase DDL.

### Exemplo: Camada Administrativa (Conforme `migration_admin.sql`)

- Foram criadas proteções automáticas envolvendo a tabela `authorized_admins` usando gatilhos (`TRIGGER` e `FUNCTION`).
- Cuidado ao inserir contatos de testes (`phone`). Recomenda-se gerar scripts de testes com números fake (Ex: `5511999999999`) para não corromper restrições `UNIQUE`.

### ⚡ Tipos de Enums de Status

Para facilitar lógicas e garantir consistência, as tabelas de **appointments** são protegidas com restrições (`CHECKS`):
- `scheduled` (Agendado tradicional)
- `waiting` (Esperando pelo atendimento - Kanban)
- `in_treatment` (Sendo atendido - Kanban)
- `confirmed` (Confirmado pelo paciente)
- `completed` (Concluído)
- `cancelled` (Cancelado por paciente ou clinica)

Qualquer código backend que use o banco só atualizará se for com um desses status exatos.

---

## 🛡️ Prevenção a Dormência (Keep-Alive)

Como utilizamos instâncias da Camada Gratuita (Free Tier) do Supabase ou similar, instâncias sofrem paralisação ("Pause") automática após longos dias de inatividade de queries nativas em HTTP/WS.

### Como contornamos isso?
O fluxo em `projeto_agendamento/src/main.py` aciona Jobs Automáticos (`jobs.py`) via APScheduler. Entre esses jobs, a classe de base de dados fará consultas vazias (tipo `ping()`) uma vez ao dia para forçar tráfego ativo no WebSocket do Supabase realtime e nas requisições HTTP do banco.
- Caso precise configurar a frequência desse Job, verificar os módulos `/src/services/jobs.py`.

---

## 🧰 Manuseio de Webhooks 

Existe um Webhook ativo (para sincronicar com Google Calendar na raiz de agendamentos). Em caso de corrupção ou exclusão acidental:
1. Revise se o Header de segurança de Webhook (`SUPABASE_WEBHOOK_SECRET`) configurado no Supabase bate com o Header mapeado nas Rotas de Webhook do projeto no FastAPI.
2. Certifique-se que o Supabase aciona atualizações via **HTTP POST** no endpoint `/webhook/supabase`.
