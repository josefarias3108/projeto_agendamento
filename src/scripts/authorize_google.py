import os
import sys
import os.path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Ajuste de path para rodar como módulo
sys.path.append(os.getcwd())

load_dotenv()

# Escopos necessários
SCOPES = ['https://www.googleapis.com/auth/calendar']

def main():
    """
    Roda um fluxo de autorização local para gerar o token.json.
    Pega Client ID e Secret do .env.
    """
    client_id = os.environ.get("GOOGLE_API_KEY")
    client_secret = os.environ.get("GOOGLE_CALENDAR_URL")

    if not client_id or not client_secret:
        print("❌ Erro: GOOGLE_API_KEY e GOOGLE_CALENDAR_URL não estão no .env.")
        return

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        }
    }

    creds = None
    # Verifica se já existe token.json
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # Se não houver credenciais (inválidas), peça login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("🚀 Iniciando fluxo de autorização no navegador...")
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Salva as credenciais para o próximo uso
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        print("✅ Sucesso! token.json gerado corretamente.")

if __name__ == '__main__':
    main()
