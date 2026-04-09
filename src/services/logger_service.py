import os
import json
import logging
import traceback
import asyncio
from datetime import datetime
from src.services.email_service import send_email

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")

# Ensure logs directory exists at startup
os.makedirs(LOGS_DIR, exist_ok=True)

async def _append_log(log_type: str, data: dict):
    """
    Assíncrono: Escreve uma linha JSONL localmente de acordo com o mês/ano.
    Não afeta a banda do banco de dados principal.
    """
    try:
        now = datetime.now()
        data["created_at"] = now.isoformat()
        
        filename = f"{log_type}_{now.strftime('%Y-%m')}.jsonl"
        filepath = os.path.join(LOGS_DIR, filename)
        
        def write_file():
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
                
        # Offload para não parar o event loop
        await asyncio.to_thread(write_file)
    except Exception as e:
        # Fallback para print padrão se ocorrer um erro na própria gravação de log
        print(f"Erro Crítico no Sistema de Log ({log_type}): {e}")

async def log_technical(action: str, status: str, handler: str = "main", phone: str = None, session_id: str = None, error_message: str = None, duration_ms: int = None):
    """Grava o log técnico e, se for crítico (status='error'), notifica o admin imediatamente por email."""
    data = {
        "logger": "technical",
        "action": action,
        "status": status,
        "handler": handler,
        "phone": phone,
        "session_id": session_id,
        "error_message": error_message,
        "duration_ms": duration_ms
    }
    
    await _append_log("technical", data)
    
    # Detetive para notificação de erro por e-mail:
    if status.lower() == "error":
         msg = f"⚠️ ALERTA DE ERRO CRÍTICO NO ROBÔ (Detetive)\n\nAção: {action}\nHandler: {handler}\nWhatsApp/Sessao: {phone or 'Desconhecido'}\nErro Crítico: {error_message}"
         try:
             asyncio.create_task(asyncio.to_thread(send_email, "gutofatias.32@gmail.com", f"CRITICAL ERRO BOT - {action}", msg))
         except Exception as e_mail:
             print(f"Falha ao enviar e-mail de detetive: {e_mail}")

async def log_conversational(patient_id: str, role: str, current_state: str, detected_intent: str, user_message: str, bot_message: str, classification: str = None, fallback_used: bool = False, session_id: str = None):
    """Trilha dos comportamentos conversacionais do paciente para IA analisar depois."""
    data = {
        "logger": "conversational",
        "session_id": session_id,
        "patient_id": patient_id,
        "role": role,
        "current_state": current_state,
        "detected_intent": detected_intent,
        "user_message": user_message,
        "bot_message": bot_message,
        "classification": classification,
        "fallback_used": fallback_used
    }
    await _append_log("conversational", data)

async def log_audit(actor_type: str, action_type: str, target_entity: str, actor_phone: str = None, actor_id: str = None, target_id: str = None, old_value: str = None, new_value: str = None, justification: str = None):
    """Arquivo restrito de rastreamento de uso sensível das funções da secretária/admin/médico."""
    data = {
        "logger": "audit",
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_phone": actor_phone,
        "action_type": action_type,
        "target_entity": target_entity,
        "target_id": target_id,
        "old_value": old_value,
        "new_value": new_value,
        "justification": justification
    }
    await _append_log("audit", data)
