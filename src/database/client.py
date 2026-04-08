import os
import logging
import httpx
from datetime import datetime, date, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("CardioAgent")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY")

# ─────────────────────────────────────────────────────────────
# Regras de Agenda do Dr. João
# ─────────────────────────────────────────────────────────────
WORK_DAYS = [0, 2, 4]          # Segunda(0), Quarta(2), Sexta(4)
SURGERY_DAYS = [1, 3]          # Terça(1), Quinta(3)
WORK_START = 9                  # 09:00
WORK_END = 18                   # 18:00
LUNCH_START = 12                # 12:00
LUNCH_END = 14                  # 14:00
SLOT_MINUTES = 60               # Duração de cada consulta: 1 hora

FERIADOS_BR = [
    date(2026, 1, 1),   # Confraternização Universal
    date(2026, 2, 16),  # Carnaval
    date(2026, 2, 17),  # Carnaval
    date(2026, 4, 3),   # Sexta da Paixão
    date(2026, 4, 21),  # Tiradentes
    date(2026, 5, 1),   # Dia do Trabalho
    date(2026, 6, 4),   # Corpus Christi
    date(2026, 9, 7),   # Independência
    date(2026, 10, 12), # N.S. Aparecida
    date(2026, 11, 2),  # Finados
    date(2026, 11, 15), # Proclamação da República
    date(2026, 12, 25), # Natal
]

TOP5_CONVENIOS = {
    "bradesco": "Bradesco Saúde",
    "amil": "Amil",
    "sulamerica": "SulAmérica",
    "unimed": "Unimed",
    "porto seguro": "Porto Seguro",
}


class SupabaseService:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            self.client = None
            logger.warning("WARNING: Supabase URL/Key ausente no .env.")
        else:
            try:
                self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                self.client = None
                logger.error(f"CRITICAL: Falha ao iniciar supabase. Erro: {e}")

    # ──────────────────── PACIENTES ────────────────────

    def get_patient_by_cpf(self, cpf: str):
        """Busca por CPF (identificador principal). Aceita '.', '-', etc."""
        if not self.client:
            return None
        clean_cpf = "".join(filter(str.isdigit, cpf))
        res = self.client.table("patients").select("*").eq("cpf", clean_cpf).execute()
        return res.data[0] if res.data else None

    def get_patient_by_phone(self, remote_jid: str):
        """Busca por número WhatsApp."""
        if not self.client:
            return None
        res = self.client.table("patients").select("*").eq("remote_jid", remote_jid).execute()
        return res.data[0] if res.data else None

    def create_patient(self, jid: str, name: str, phone: str, email: str = None,
                       address: str = None, cep: str = None, cpf: str = None,
                       birth_date: str = None, insurance: str = None, 
                       insurance_category: str = None):
        if not self.client:
            return None
        clean_cpf = "".join(filter(str.isdigit, cpf)) if cpf else None
        data = {
            "remote_jid": jid,
            "name": name,
            "phone": phone,
            "email": email.lower().strip() if email else None,
            "address": address,
            "cep": cep,
            "cpf": clean_cpf,
            "birth_date": birth_date,
            "insurance": insurance,
            "insurance_category": insurance_category,
        }
        res = self.client.table("patients").insert(data).execute()
        return res.data[0] if res.data else None

    def update_patient(self, patient_id: str, **fields):
        """Atualiza campos do paciente existente."""
        if not self.client:
            return None
        res = self.client.table("patients").update(fields).eq("id", patient_id).execute()
        return res.data[0] if res.data else None

    # ──────────────────── MÉDICOS ────────────────────

    def get_doctor_by_name(self, name: str):
        if not self.client:
            return None
        res = self.client.table("doctors").select("*").ilike("name", f"%{name}%").execute()
        return res.data[0] if res.data else None

    def get_patient(self, patient_id: str) -> dict | None:
        if not self.client:
            return None
        res = self.client.table("patients").select("*").eq("id", patient_id).execute()
        return res.data[0] if res.data else None

    # ──────────────────── DISPONIBILIDADE ────────────────────

    def check_availability(self, date_str: str) -> str:
        """
        Retorna slots disponíveis para uma data, respeitando:
        - Dias de trabalho (Seg/Qua/Sex)
        - Horário comercial (08-19, exceto 12-14)
        - Feriados (apenas informação, cirurgias são imunes)
        """
        # Tenta interpretar a data
        try:
            txt = date_str.lower().strip()
            today = date.today()
            
            # Atalhos comuns
            if txt in ("amanhã", "amanha"):
                target = today + timedelta(days=1)
            elif txt in ("hoje",):
                target = today
            # Dias da semana (português)
            elif any(d in txt for d in ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]):
                weekdays_br = {
                    "segunda": 0, "terça": 1, "quarta": 2, "quinta": 3,
                    "sexta": 4, "sábado": 5, "domingo": 6, "sabado": 5
                }
                day_num = -1
                for k, v in weekdays_br.items():
                    if k in txt:
                        day_num = v
                        break
                
                # Calcula quantos dias faltam para a próxima ocorrência desse dia
                days_ahead = day_num - today.weekday()
                if days_ahead <= 0: # Se for hoje ou já passou na semana atual, pega a próxima semana
                    days_ahead += 7
                target = today + timedelta(days=days_ahead)
            else:
                # Tenta vários formatos numéricos
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        target = datetime.strptime(date_str, fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    return f"Não consegui entender a data '{date_str}'. Por favor informe no formato DD/MM/AAAA."
        except Exception:
            return f"Data inválida: {date_str}."

        weekday = target.weekday()
        day_name = ["segunda-feira", "terça-feira", "quarta-feira",
                    "quinta-feira", "sexta-feira", "sábado", "domingo"][weekday]

        # Feriado?
        if target in FERIADOS_BR:
            return (f"O dia {target.strftime('%d/%m/%Y')} ({day_name}) é feriado nacional. "
                    "O consultório não atende nesta data. Posso verificar outra data para você?")

        # Fim de semana?
        if weekday >= 5:
            return (f"O consultório não funciona aos finais de semana. "
                    "Posso verificar uma segunda, quarta ou sexta para você?")

        # Dia cirúrgico?
        if weekday in SURGERY_DAYS:
            return (f"{day_name.capitalize()} é reservado para cirurgias — o Dr. João "
                    "agenda as cirurgias pessoalmente. Para consultas, posso verificar uma "
                    "segunda-feira, quarta-feira ou sexta-feira.")

        # Dia válido para consultas
        if weekday not in WORK_DAYS:
            return "Não temos atendimento neste dia. Atendemos consultas nas segundas, quartas e sextas."

        # Busca agendamentos existentes nessa data
        booked_times = set()
        if self.client:
            start_of_day = datetime.combine(target, datetime.min.time()).isoformat()
            end_of_day = datetime.combine(target, datetime.max.time()).isoformat()
            res = (self.client.table("appointments")
                   .select("start_time")
                   .eq("status", "scheduled")
                   .gte("start_time", start_of_day)
                   .lte("start_time", end_of_day)
                   .execute())
            for a in (res.data or []):
                try:
                    t = datetime.fromisoformat(a["start_time"])
                    booked_times.add(t.hour)
                except Exception:
                    pass

        # Gera slots livres
        free_slots = []
        h = WORK_START
        while h < WORK_END:
            if h == LUNCH_START:
                h = LUNCH_END
                continue
            if h not in booked_times:
                free_slots.append(f"{h:02d}:00")
            h += 1

        date_label = target.strftime('%d/%m/%Y')
        if not free_slots:
            return (f"Infelizmente não há horários disponíveis em {date_label} ({day_name}). "
                    "Posso verificar outra data?")

        slots_text = ", ".join(free_slots)
        return (f"Horários disponíveis em {date_label} ({day_name}): {slots_text}. "
                "Qual horário prefere?")

    def find_next_available_dates(self, max_days=60, limit_days=7, offset_count=0) -> tuple[str, list[str], bool]:
        """Retorna (mensagem_formatada, lista_de_datas_iso)."""
        found_labels = []
        found_iso = []
        today = date.today()
        end_date = today + timedelta(days=max_days)
        
        # 1. Puxa TODOS os agendamentos dos próximos 60 dias de UMA VEZ (Otimização)
        all_booked = []
        if self.client:
            res = (self.client.table("appointments")
                   .select("start_time")
                   .eq("status", "scheduled")
                   .gte("start_time", today.strftime("%Y-%m-%dT00:00:00Z"))
                   .lte("start_time", end_date.strftime("%Y-%m-%dT23:59:59Z"))
                   .execute())
            all_booked = res.data or []
            
        # 2. Agrupa por data para busca rápida
        booked_by_date = {}
        for b in all_booked:
            try:
                dt_obj = datetime.fromisoformat(b["start_time"].replace("Z", ""))
                iso = dt_obj.strftime("%Y-%m-%d")
                if iso not in booked_by_date: booked_by_date[iso] = set()
                booked_by_date[iso].add(dt_obj.hour)
            except: pass

        # 3. Processa datas disponíveis em memória
        for i in range(1, max_days + 1):
            target = today + timedelta(days=i)
            weekday = target.weekday()
            
            # Pula senao for dia de trabalho, feriado ou cirurgico
            if weekday not in WORK_DAYS or target in FERIADOS_BR or weekday in SURGERY_DAYS:
                continue
                
            iso_str = target.isoformat()
            booked_times = booked_by_date.get(iso_str, set())
            
            # Verifica slots livres
            has_free_slot = False
            h = WORK_START
            while h < WORK_END:
                if h == LUNCH_START:
                    h = LUNCH_END
                    continue
                if h not in booked_times:
                    has_free_slot = True
                    break
                h += 1
            
            if has_free_slot:
                date_label = target.strftime('%d/%m')
                day_name = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][weekday]
                found_iso.append(iso_str)
                found_labels.append(f"{date_label} ({day_name})")

        start_idx = offset_count
        end_idx = offset_count + limit_days
        
        paginated_iso = found_iso[start_idx:end_idx]
        paginated_labels = found_labels[start_idx:end_idx]
        
        if not paginated_labels:
            return "Desculpe, não localizei datas disponíveis.", [], False
            
        menu_items = []
        for i, lbl in enumerate(paginated_labels):
            idx = i + 1
            emoji = "🔟" if idx == 10 else f"{idx}️⃣"
            menu_items.append(f"{emoji} {lbl}")

        msg = "Aqui estão as próximas datas disponíveis 😊\n\n" + "\n".join(menu_items) + "\n"
        
        has_more = len(found_iso) > end_idx
        if has_more:
            msg += "\n8️⃣ Ver mais datas disponíveis"
            btn_voltar = 9
        else:
            btn_voltar = len(paginated_iso) + 1

        msg += f"\n\n↩️ {btn_voltar}️⃣ Voltar ao menu principal\n"
        msg += "\n👉 Digite o número da opção desejada"

        return msg, paginated_iso, has_more

    def get_hours_menu(self, date_iso: str) -> tuple[str, list[int]]:
        """Retorna (mensagem_com_menu, lista_de_horas)."""
        res_text = self.check_availability(date_iso)
        if "Horários disponíveis" not in res_text:
            return res_text, []
            
        # Extrai horas da resposta: "Horários disponíveis em ...: 08:00, 09:00..."
        parts = res_text.split(": ")
        if len(parts) < 2: return "Erro ao extrair horários.", []
        
        hours_str = parts[1].replace(" Qual horário prefere?", "").split(", ")
        menu_items = []
        hours_list = []
        for i, h in enumerate(hours_str):
            menu_items.append(f"{i+1}️⃣ {h}")
            hours_list.append(int(h.split(":")[0]))
            
        btn_voltar = len(hours_list) + 1
        msg = (f"Perfeito! 😊\n\nVeja os horários disponíveis para o dia escolhido:\n\n" +
               "\n".join(menu_items) +
               f"\n\n↩️ {btn_voltar}️⃣ Voltar para escolher outra data\n\n" +
               "👉 Me diga o número da opção que você prefere")
        return msg, hours_list

    # ──────────────────── AGENDAMENTOS ────────────────────

    def book_appointment(self, patient_id: str, doctor_id: str,
                         start_time: str, end_time: str):
        """
        Salva o agendamento no Supabase.
        A sincronização com o Google Calendar é feita automaticamente
        pelo Supabase Webhook → /webhook/supabase → calendar_sync.py
        """
        if not self.client:
            return {"success": False, "error": "Banco de dados indisponível."}
        try:
            # Garante formato ISO preciso com 'Z'
            start_iso = start_time.split(".")[0].replace("+00:00", "")
            end_iso = end_time.split(".")[0].replace("+00:00", "")
            if not start_iso.endswith("Z"): start_iso += "Z"
            if not end_iso.endswith("Z"): end_iso += "Z"

            data = {
                "patient_id": str(patient_id),
                "doctor_id": str(doctor_id),
                "start_time": start_iso,
                "end_time": end_iso,
                "status": "scheduled",
            }
            logger.info(f"Inserindo agendamento no Supabase: {data}")
            res = self.client.table("appointments").insert(data).execute()
            return {"success": True, "data": res.data[0] if res.data else None}
        except Exception as e:
            logger.error(f"Erro ao inserir agendamento: {str(e)}")
            err_msg = str(e)
            if "no_double_booking_idx" in err_msg:
                return {"success": False, "error": "Este horário já foi ocupado. Por favor escolha outro."}
            return {"success": False, "error": err_msg}

    def get_appointments_by_patient(self, patient_id: str):
        """Retorna consultas futuras do paciente."""
        if not self.client:
            return []
        now = datetime.utcnow().isoformat()
        res = (self.client.table("appointments")
               .select("id, start_time, end_time, status, patient_id, doctors(name)")
               .eq("patient_id", patient_id)
               .eq("status", "scheduled")
               .gte("start_time", now)
               .order("start_time")
               .execute())
        return res.data or []

    def get_appointment_by_patient_and_day(self, patient_id: str, target_iso: str):
        """Verifica se o paciente já tem consulta agendada naquele dia específico."""
        if not self.client:
            return None
        
        # Converte ISO string (YYYY-MM-DD) ou (YYYY-MM-DDTHH...) para os limites do dia
        dt_obj = datetime.fromisoformat(target_iso.split("T")[0])
        start_of_day = dt_obj.strftime("%Y-%m-%dT00:00:00Z")
        end_of_day = dt_obj.strftime("%Y-%m-%dT23:59:59Z")
        
        res = (self.client.table("appointments")
               .select("id, start_time")
               .eq("patient_id", patient_id)
               .eq("status", "scheduled")
               .gte("start_time", start_of_day)
               .lte("start_time", end_of_day)
               .execute())
        return res.data[0] if res.data else None

    def cancel_appointment(self, appointment_id: str):
        """
        Atualiza status para 'cancelled' no Supabase.
        O Supabase Webhook detecta a mudança de status e dispara
        o calendar_sync.py para remover o evento do Google Calendar.
        """
        if not self.client:
            return False
        try:
            self.client.table("appointments").update({"status": "cancelled"}).eq("id", appointment_id).execute()
            logger.info(f"Agendamento [{appointment_id}] cancelado no Supabase.")
            return True
        except Exception as e:
            logger.error(f"Erro ao cancelar agendamento [{appointment_id}]: {e}")
            return False

    # ──────────────────── EXAMES ────────────────────

    def save_exam(self, patient_id: str, file_name: str, file_path: str, file_url: str, file_type: str = None):
        if not self.client:
            return None
        data = {
            "patient_id": patient_id,
            "file_name": file_name,
            "file_path": file_path,
            "file_url": file_url,
            "file_type": file_type,
        }
        res = self.client.table("patient_exams").insert(data).execute()
        return res.data[0] if res.data else None

    def get_exams_by_patient(self, patient_id: str):
        if not self.client:
            return []
        res = self.client.table("patient_exams").select("*").eq("patient_id", patient_id).order("created_at", desc=True).execute()
        return res.data or []

        return None, (
            "Infelizmente não localizei esse convênio em nossa lista. "
            "Atendemos pelos seguintes planos: Bradesco Saúde, Amil, SulAmérica, Unimed e Porto Seguro. "
            "Você gostaria de agendar como *Particular* (R$ 450,00)?")

    # ──────────────────── ADMINS / CLINIC ────────────────────

    def check_is_admin(self, remote_jid: str) -> dict | None:
        """Verifica se um número tem acesso administrativo e retorna o cargo."""
        if not self.client: return None
        # Pega apenas os números antes do @ (ex: 552199... @s.whatsapp.net -> 552199...)
        phone_number = remote_jid.split("@")[0]
        res = self.client.table("authorized_admins").select("role, name").eq("phone", phone_number).execute()
        return res.data[0] if res.data else None

    def add_admin(self, phone: str, role: str = "admin", name: str = "Secretária/Admin"):
        if not self.client: return False
        try:
            self.client.table("authorized_admins").insert({"phone": phone, "role": role, "name": name}).execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao adicionar admin: {e}")
            return False

    def remove_admin(self, phone: str):
        if not self.client: return False
        try:
            self.client.table("authorized_admins").delete().eq("phone", phone).execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao remover admin: {e}")
            return False

    def list_admins(self):
        if not self.client: return []
        res = self.client.table("authorized_admins").select("phone, name, role").execute()
        return res.data or []

    # ──────────────────── KANBAN / LISTAGEM ────────────────────

    def get_upcoming_appointment_dates(self, limit=7, offset=0, max_days_ahead=60):
        if not self.client: return []
        hoje = date.today()
        # No supabase postgrest, não temos DISTICT DATE nativo facilmente via SDK sem RPC.
        # Vamos buscar os appts até 60 dias pra frente, e em Python tiramos as datas únicas.
        max_date = hoje + timedelta(days=max_days_ahead)
        res = (self.client.table("appointments")
               .select("start_time")
               .gte("start_time", hoje.isoformat())
               .lte("start_time", max_date.isoformat())
               .neq("status", "cancelled")
               .order("start_time")
               .execute())
        
        dates_set = set()
        unique_dates = []
        for a in (res.data or []):
            try:
                d = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00")).date()
                if d >= hoje and d not in dates_set:
                    dates_set.add(d)
                    unique_dates.append(d)
            except: pass
        
        unique_dates.sort()
        
        # Paginação
        return unique_dates[offset:offset+limit], len(unique_dates)

    def get_appointments_by_date(self, target_date: date):
        if not self.client: return []
        start_of_day = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
        end_of_day = datetime.combine(target_date, datetime.max.time()).isoformat() + "Z"
        
        res = (self.client.table("appointments")
               .select("id, start_time, status, patient_id, patients(name, phone)")
               .gte("start_time", start_of_day)
               .lte("start_time", end_of_day)
               .neq("status", "cancelled")
               .order("start_time")
               .execute())
        return res.data or []

    def get_weekly_schedule(self):
        if not self.client: return []
        hoje = date.today()
        # Traz próximos 5 dias da semana (excluindo FDS se quiser, mas aqui traremos os próximos 7 dias por segurança)
        max_date = hoje + timedelta(days=7)
        res = (self.client.table("appointments")
               .select("id, start_time, end_time, status, patients(name)")
               .gte("start_time", hoje.isoformat())
               .lte("start_time", max_date.isoformat())
               .neq("status", "cancelled")
               .order("start_time")
               .execute())
        return res.data or []

    # ──────────────────── STATUS ────────────────────

    def get_todays_appointments(self, offset_days=0):
        """Lista todas consultas para um dia relativo a hoje."""
        if not self.client: return []
        target_date = date.today() + timedelta(days=offset_days)
        start_of_day = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
        end_of_day = datetime.combine(target_date, datetime.max.time()).isoformat() + "Z"
        
        res = (self.client.table("appointments")
               .select("id, start_time, status, patient_id, patients(name, phone)")
               .gte("start_time", start_of_day)
               .lte("start_time", end_of_day)
               .neq("status", "cancelled")
               .order("start_time")
               .execute())
        return res.data or []

    def update_appointment_status(self, appointment_id: str, new_status: str):
        if not self.client: return False
        try:
            self.client.table("appointments").update({"status": new_status}).eq("id", appointment_id).execute()
            return True
        except Exception as e:
            logger.error(f"Erro ao atualizar status do agendamento {appointment_id}: {e}")
            return False

    # ──────────────────── MÉTRICAS (PO) ────────────────────

    def get_monthly_metrics(self):
        """Busca métricas avançadas baseadas em ajustes.md"""
        if not self.client: return {}
        patients = self.client.table("patients").select("insurance, birth_date").execute().data or []
        appointments = self.client.table("appointments").select("status").execute().data or []
        return {"patients": patients, "appointments": appointments}

    def get_patient_documents(self, cpf: str):
        # Placeholder para documentos
        return []

    def get_patient_by_cpf(self, cpf: str) -> dict | None:
        if not self.client: return None
        res = self.client.table("patients").select("*").eq("cpf", cpf).execute()
        return res.data[0] if res.data else None

    def get_patient_appointments(self, patient_id: str):
        if not self.client: return []
        res = (self.client.table("appointments")
               .select("*")
               .eq("patient_id", patient_id)
               .neq("status", "cancelled")
               .order("start_time")
               .execute())
        return res.data or []

    def get_patient_full_history(self, patient_id: str):
        if not self.client: return []
        res = (self.client.table("appointments")
               .select("*")
               .eq("patient_id", patient_id)
               .order("start_time", desc=True)
               .execute())
        return res.data or []

    def search_patient_flexible(self, query: str):
        """Busca flexível por CPF, Nome ou E-mail."""
        if not self.client: return []
        
        q = query.strip()
        # 1. Se for 11 dígitos, tenta CPF primeiro
        clean_num = "".join(filter(str.isdigit, q))
        if len(clean_num) == 11:
            res = self.client.table("patients").select("*").eq("cpf", clean_num).execute()
            if res.data: return res.data

        # 2. Tenta busca por e-mail (se conter @)
        if "@" in q:
            res = self.client.table("patients").select("*").ilike("email", f"%{q}%").execute()
            if res.data: return res.data

        # 3. Tenta busca por Nome (parcial e insensível a caixa)
        res = self.client.table("patients").select("*").ilike("name", f"%{q}%").execute()
        return res.data or []


db_service = SupabaseService()


async def lookup_cep(cep: str) -> dict | None:
    """
    Consulta a API pública ViaCEP e retorna um dict com os campos de endereço.
    Retorna None se o CEP for inválido ou a API não responder.
    """
    clean = "".join(filter(str.isdigit, cep))
    if len(clean) != 8:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"https://viacep.com.br/ws/{clean}/json/")
            data = r.json()
            if data.get("erro"):
                return None
            return data
    except Exception:
        return None
