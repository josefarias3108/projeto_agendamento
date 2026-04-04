import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("CardioAgent")

SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", 587))
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")


async def send_email_reminder(to_email: str, patient_name: str, appointment_time: str, reminder_type: str):
    """
    Envia e-mail de lembrete de consulta.
    reminder_type: "24h" ou "2h"
    """
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.warning("E-mail não configurado no .env. Lembrete por e-mail ignorado.")
        return False

    if not to_email:
        return False

    if reminder_type == "24h":
        subject = "🩺 Lembrete: Sua consulta com Dr. João é amanhã!"
        body = f"""\
Olá, {patient_name}! 😊

Passamos para lembrar que você tem uma consulta agendada com o *Dr. João (Cardiologista)* amanhã, às *{appointment_time}*.

✅ Por favor, chegue com 10 minutos de antecedencia.

📄 *Documentos para trazer:*
• Carteirinha do plano de saúde (ou informe que é Particular)
• Documento de identidade: RG, CNH ou qualquer outro documento oficial com foto

Se precisar reagendar, responda esta mensagem ou entre em contato pelo WhatsApp.

Até amanhã!
Equipe do Consultório Dr. João 💙
"""
    else:
        subject = "🩺 Lembrete: Sua consulta é em 2 horas!"
        body = f"""\
Olá, {patient_name}! 😊

Sua consulta com o *Dr. João* está chegando! Marcada para *{appointment_time}* (em aproximadamente 2 horas).

📄 *Não esqueça de trazer:*
• Carteirinha do plano de saúde (ou informe que é Particular)
• Documento de identidade: RG, CNH ou qualquer outro documento oficial com foto

A equipe do Dr. João aguarda você! 💙
"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

        logger.info(f"E-mail de lembrete ({reminder_type}) enviado para {to_email}")
        return True

    except Exception as e:
        logger.error(f"Falha ao enviar e-mail para {to_email}: {e}")
        return False
