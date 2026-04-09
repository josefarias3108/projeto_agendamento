# 📊 5. Estrutura de Logs e Auditoria

Aqui eu recomendo separar em 3 níveis distintos para facilitar o monitoramento e debug do sistema.

---

## 🛠️ 5.1. Log Técnico

**Objetivo:** Utilizado exclusivamente para depuração e rastreabilidade de código.

**Campos:**
- `request_id`
- `session_id`
- `phone`
- `handler`
- `action`
- `status`
- `error_message`
- `duration_ms`
- `created_at`

**Exemplos de Ações:**
- `webhook recebido`
- `mensagem enviada`
- `falha no Supabase`
- `falha na Evolution`
- `falha na Calendar API`

---

## 💬 5.2. Log Conversacional

**Objetivo:** Para entender o comportamento do usuário e refinar a Inteligência Artificial.

**Campos:**
- `session_id`
- `patient_id`
- `role`
- `current_state`
- `detected_intent`
- `user_message`
- `bot_message`
- `classification`
- `fallback_used`
- `created_at`

---

## 👁️‍🗨️ 5.3. Log de Auditoria

**Objetivo:** Para registro de atividades e ações sensíveis feitas por secretária, médico ou admin.

**Campos:**
- `actor_type`
- `actor_id`
- `actor_phone`
- `target_entity`
- `target_id`
- `action_type`
- `old_value`
- `new_value`
- `justification`
- `created_at`

**Exemplos de Ações:**
- `secretária cancelou consulta`
- `médico marcou atendimento concluído`
- `admin autorizou novo número`
- `secretária enviou disparo em massa`