5. Estrutura de logs e auditoria

Aqui eu recomendo separar em 3 níveis.

5.1. Log técnico

Para depuração.

Campos:

request_id
session_id
phone
handler
action
status
error_message
duration_ms
created_at

Exemplo:

webhook recebido
mensagem enviada
falha no Supabase
falha na Evolution
falha na Calendar API
5.2. Log conversacional

Para entender o comportamento do usuário.

Campos:

session_id
patient_id
role
current_state
detected_intent
user_message
bot_message
classification
fallback_used
created_at
5.3. Log de auditoria

Para ações sensíveis de secretária, médico e admin.

Campos:

actor_type
actor_id
actor_phone
target_entity
target_id
action_type
old_value
new_value
justification
created_at

Exemplos:

secretária cancelou consulta
médico marcou atendimento concluído
admin autorizou novo número
secretária enviou disparo em massa