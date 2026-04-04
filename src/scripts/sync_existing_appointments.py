"""
sync_existing_appointments.py
──────────────────────────────
Sincroniza consultas existentes (scheduled, sem google_event_id) com o Google Calendar.
Usa o mesmo db_service do bot (já funcional).

Uso:
    python src/scripts/sync_existing_appointments.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SyncExisting")


def normalize_iso(dt_str: str) -> str:
    if not dt_str:
        return dt_str
    dt_str = dt_str.split(".")[0].replace("+00:00", "")
    if not dt_str.endswith("Z"):
        dt_str += "Z"
    return dt_str


def main():
    logger.info("=" * 60)
    logger.info("🚀 Sincronização de consultas existentes → Google Calendar")
    logger.info("=" * 60)

    # Importa os serviços (mesmo singleton do bot)
    from src.database.client import db_service
    from src.services.google_calendar import calendar_service

    if not db_service.client:
        logger.error("❌ Supabase não conectado. Verifique o .env.")
        return

    # 1. Busca TODAS as consultas scheduled
    logger.info("📋 Buscando consultas 'scheduled'...")
    try:
        res = (
            db_service.client
            .table("appointments")
            .select("id, patient_id, start_time, end_time, status, google_event_id")
            .eq("status", "scheduled")
            .order("start_time")
            .execute()
        )
        all_appointments = res.data or []
    except Exception as e:
        logger.error(f"❌ Erro ao buscar consultas: {e}")
        return

    # Filtra apenas as sem google_event_id
    appointments = [a for a in all_appointments if not a.get("google_event_id")]

    logger.info(f"📊 Total no banco: {len(all_appointments)} | Sem Google Calendar: {len(appointments)}")

    if not appointments:
        logger.info("✅ Todas as consultas já estão sincronizadas com o Google Calendar!")
        return

    logger.info(f"\n📌 {len(appointments)} consulta(s) para sincronizar:\n")

    success_count = 0
    error_count = 0

    for i, appt in enumerate(appointments, start=1):
        appt_id = appt.get("id")
        patient_id = appt.get("patient_id")
        start_time = appt.get("start_time")
        end_time = appt.get("end_time")

        logger.info(f"[{i}/{len(appointments)}] Consulta {appt_id} — {start_time}")

        # 2. Busca dados do paciente
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
        start_iso = normalize_iso(start_time)
        end_iso = normalize_iso(end_time)

        logger.info(f"  👤 {patient_name} | {insurance}")
        logger.info(f"  🕐 {start_iso} → {end_iso}")

        # 3. Cria evento no Google Calendar
        try:
            g_event_id = calendar_service.create_event(summary, description, start_iso, end_iso)
        except Exception as e:
            logger.error(f"  ❌ Erro Google Calendar: {e}")
            error_count += 1
            continue

        if not g_event_id:
            logger.error(f"  ❌ Falha ao criar evento")
            error_count += 1
            continue

        # 4. Salva google_event_id no Supabase
        try:
            db_service.client.table("appointments").update(
                {"google_event_id": g_event_id}
            ).eq("id", appt_id).execute()
            logger.info(f"  ✅ Evento criado e salvo: [{g_event_id}]\n")
            success_count += 1
        except Exception as e:
            logger.warning(f"  ⚠️  Evento criado mas falhou ao salvar ID: {e}")
            logger.info(f"  ℹ️  google_event_id manual: {g_event_id}\n")
            success_count += 1

    logger.info("=" * 60)
    logger.info(f"✅ Sincronizados: {success_count} | ❌ Falhas: {error_count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
