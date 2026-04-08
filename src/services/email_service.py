import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger("CardioAgent")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        logger.warning(f"⚠️ Credenciais de E-mail ausentes no .env. Simulação de envio para {to_email}:\nAssunto: {subject}\nCorpo:\n{body}")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Consultório Dr. João <{SMTP_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            
        logger.info(f"E-mail enviado com sucesso para {to_email}!")
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar e-mail para {to_email}: {e}")
        return False

def send_email_reminder(email: str, name: str, time_str: str, label: str):
    subject = f"Lembrete de Consulta: {label}"
    body = f"Olá, {name}!\n\nLembramos que sua consulta com o Dr. João está agendada para {time_str}.\n\nFicamos à disposição!"
    return send_email(email, subject, body)
