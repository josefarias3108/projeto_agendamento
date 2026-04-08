import logging
from src.database.client import db_service
from datetime import date

logger = logging.getLogger("CardioAgent")

def calculate_age(birth_date: str) -> int:
    try:
        from datetime import datetime
        d = datetime.fromisoformat(birth_date).date()
        today = date.today()
        # https://stackoverflow.com/questions/2217488/age-from-birthdate-in-python
        return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    except:
        return 0

async def handle_metrics(remote_jid: str, state: dict):
    from src.services.evolution import evo_service
    
    # Busca métricas avançadas
    metrics = db_service.get_monthly_metrics()
    patients = metrics.get("patients", [])
    appointments = metrics.get("appointments", [])
    
    total_appointments = len(appointments)
    no_shows = len([a for a in appointments if a.get("status") in ("cancelled", "no_show")])
    
    insurances = {}
    valid_ages = []
    
    for p in patients:
        ins = p.get("insurance") or "Particular"
        insurances[ins] = insurances.get(ins, 0) + 1
        
        bdate = p.get("birth_date")
        if bdate:
            age = calculate_age(bdate)
            if age > 0:
                valid_ages.append(age)
            
    # Média de idade
    average_age = sum(valid_ages) // len(valid_ages) if valid_ages else 0
            
    # Top Seguros (Ranking total)
    sorted_ins = sorted(insurances.items(), key=lambda item: item[1], reverse=True)
    rank_str = "\n".join([f"- {k}: {v}" for k, v in sorted_ins]) if sorted_ins else "Sem dados ainda."
    
    rate = (no_shows/total_appointments)*100 if total_appointments > 0 else 0
    
    msg = f"📈 *Métricas de Performance (PO)*\n\n"
    msg += f"🔸 Total Agendamentos Registrados: {total_appointments}\n"
    msg += f"🔸 Faltas / Cancelamentos: {no_shows}\n"
    msg += f"🔸 Taxa de Faltas: {rate:.1f}%\n"
    msg += f"🔸 Média de Idade: {average_age} anos\n"
    msg += f"\n🏆 *Ranking Planos de Saúde*\n{rank_str}\n"
    msg += f"\n(Dados baseados no histórico total disponível no formato resumido para WhatsApp).\n"
    msg += "\n↩️ 9️⃣ Voltar ao menu do consultório"
    
    await evo_service.send_text_message(remote_jid, msg)
    state["clinic_step"] = "viewing_report"

