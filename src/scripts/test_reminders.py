import asyncio
import logging
import sys
import os
from datetime import datetime

# Ajuste de path para rodar como módulo
sys.path.append(os.getcwd())

from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.email_service import send_email_reminder

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestReminders")

async def run_manual_test():
    """
    Busca todos os agendamentos marcados como 'scheduled' e envia lembretes de teste (24h e 2h).
    """
    logger.info("🚀 Iniciando disparo de lembretes de TESTE...")

    if not db_service.client:
        logger.error("Erro: Conexão com Supabase não estabelecida.")
        return

    # Busca agendamentos com dados dos pacientes
    res = (db_service.client.table("appointments")
           .select("id, start_time, patients(name, remote_jid, email, insurance)")
           .eq("status", "scheduled")
           .execute())

    appointments = res.data or []
    if not appointments:
        logger.info("Nenhum agendamento 'scheduled' encontrado para teste.")
        return

    logger.info(f"Encontrados {len(appointments)} agendamentos para teste.")

    for appt in appointments:
        patient = appt.get("patients", {})
        phone = patient.get("remote_jid")
        email = patient.get("email")
        name = patient.get("name", "Paciente de Teste")
        insurance = patient.get("insurance", "Plano")

        try:
            start_dt = datetime.fromisoformat(appt["start_time"].replace("Z", ""))
            time_str_24h = start_dt.strftime("%d/%m/%Y às %H:%M")
            time_str_2h = start_dt.strftime("%H:%M")
        except Exception:
            time_str_24h = appt["start_time"]
            time_str_2h = appt["start_time"]

        logger.info(f"--- Processando: {name} ({phone}) ---")

        # ── TESTE LEMBRETE 24H ─────────────────────────────────
        prefix = "⚠️ *ESTE É UM TESTE DO SISTEMA* ⚠️\n\n"
        
        # WhatsApp 24h
        if phone:
            msg_24h = (
                f"{prefix}"
                f"Olá, {name}! 😊\n\n"
                f"Lembrando que você tem uma consulta com o *Dr. João* amanhã em {time_str_24h}.\n\n"
                f"📄 *Documentos para trazer:*\n"
                f"• Carteirinha do plano ({insurance})\n"
                f"• Documento com foto\n\n"
                "Até lá! 💙"
            )
            await evo_service.send_text_message(phone, msg_24h)
            logger.info(f"[WA 24h] Enviado para {phone}")

        # E-mail 24h
        if email:
            # Note: The email service uses its own template, so we add the prefix to the patient name or body
            # For simplicity in this test, we'll try to add it to the body if possible or just log it is a test
            await send_email_reminder(email, f"{name} (TESTE)", time_str_24h, "24h")
            logger.info(f"[Email 24h] Enviado para {email}")

        await asyncio.sleep(1) # Pequena pausa entre mensagens

        # ── TESTE LEMBRETE 2h ──────────────────────────────────
        # WhatsApp 2h
        if phone:
            msg_2h = (
                f"{prefix}"
                f"Oi, {name}! ⏰\n\n"
                f"Sua consulta com o *Dr. João* é hoje às *{time_str_2h}* — em cerca de 2 horas.\n"
                "Nos vemos em breve! 💙"
            )
            await evo_service.send_text_message(phone, msg_2h)
            logger.info(f"[WA 2h] Enviado para {phone}")

        # E-mail 2h
        if email:
            await send_email_reminder(email, f"{name} (TESTE)", time_str_2h, "2h")
            logger.info(f"[Email 2h] Enviado para {email}")

        logger.info(f"✅ Testes concluídos para {name}.")
        await asyncio.sleep(2)

    logger.info("🎯 Todos os lembretes de teste foram disparados.")

if __name__ == "__main__":
    asyncio.run(run_manual_test())
