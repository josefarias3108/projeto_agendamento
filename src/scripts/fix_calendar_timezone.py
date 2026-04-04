"""
fix_calendar_timezone.py
─────────────────────────
Apaga os eventos desincronizados do Google Calendar (horário errado) e
os recria com o horário correto (America/Sao_Paulo) usando o fix do _strip_tz.

Uso:
    python src/scripts/fix_calendar_timezone.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FixTimezone")


def main():
    logger.info("=" * 60)
    logger.info("🔧 Corrigindo fuso horário dos eventos no Google Calendar")
    logger.info("=" * 60)

    from src.database.client import db_service
    from src.services.google_calendar import calendar_service

    if not db_service.client:
        logger.error("❌ Supabase não conectado.")
        return

    # 1. Busca todas as consultas scheduled COM google_event_id (os que criamos com fuso errado)
    logger.info("📋 Buscando consultas com google_event_id para corrigir...")
    try:
        res = (
            db_service.client
            .table("appointments")
            .select("id, patient_id, start_time, end_time, google_event_id")
            .eq("status", "scheduled")
            .not_.is_("google_event_id", "null")
            .order("start_time")
            .execute()
        )
        appointments = res.data or []
    except Exception as e:
        logger.error(f"❌ Erro ao buscar consultas: {e}")
        return

    total = len(appointments)
    if total == 0:
        logger.info("✅ Nenhum evento para corrigir.")
        return

    logger.info(f"📌 {total} evento(s) para recriar com fuso correto.\n")

    success_count = 0
    error_count = 0

    for i, appt in enumerate(appointments, start=1):
        appt_id = appt.get("id")
        old_event_id = appt.get("google_event_id")
        patient_id = appt.get("patient_id")
        start_time = appt.get("start_time")
        end_time = appt.get("end_time")

        logger.info(f"[{i}/{total}] Consulta {appt_id}")
        logger.info(f"  🕐 Horário no banco: {start_time}")
        logger.info(f"  🗑️  Deletando evento antigo: {old_event_id}")

        # 2. Deleta evento antigo (horário errado)
        deleted = calendar_service.delete_event(old_event_id)
        if not deleted:
            logger.warning(f"  ⚠️  Não foi possível deletar o evento antigo (pode já não existir)")

        # 3. Busca dados do paciente
        try:
            res_p = (
                db_service.client
                .table("patients")
                .select("name, insurance")
                .eq("id", patient_id)
                .execute()
            )
            patient = res_p.data[0] if res_p.data else {}
        except Exception as e:
            logger.warning(f"  ⚠️  Erro ao buscar paciente: {e}")
            patient = {}

        patient_name = patient.get("name") or "Paciente"
        insurance = patient.get("insurance") or "Não informado"

        summary = f"Consulta: {patient_name}"
        description = f"📋 Convênio: {insurance}\n📱 Agendado via Bot WhatsApp."

        logger.info(f"  👤 {patient_name} | ✅ Recriando com fuso America/Sao_Paulo")

        # 4. Recria evento com horário correto (sem Z)
        try:
            new_event_id = calendar_service.create_event(summary, description, start_time, end_time)
        except Exception as e:
            logger.error(f"  ❌ Erro ao criar evento: {e}")
            error_count += 1
            continue

        if not new_event_id:
            logger.error(f"  ❌ Falha ao criar evento")
            error_count += 1
            continue

        # 5. Atualiza google_event_id no Supabase
        try:
            db_service.client.table("appointments").update(
                {"google_event_id": new_event_id}
            ).eq("id", appt_id).execute()
            logger.info(f"  ✅ Novo evento criado: [{new_event_id}]\n")
            success_count += 1
        except Exception as e:
            logger.warning(f"  ⚠️  Evento criado mas falhou ao salvar ID: {e}")
            success_count += 1

    logger.info("=" * 60)
    logger.info(f"✅ Corrigidos: {success_count} | ❌ Falhas: {error_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
