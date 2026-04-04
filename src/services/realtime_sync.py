"""
realtime_sync.py
────────────────
Escuta mudanças na tabela `appointments` via Supabase Realtime (WebSocket).
Compatível com supabase-py >= 2.0 usando o cliente ASSÍNCRONO (AsyncClient).
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("CardioAgent")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_API_KEY", "")

_running = True


def _make_callback(event_type: str):
    """Fábrica de callback síncrono que agenda a coroutine no loop de eventos."""
    def callback(payload):
        from src.services.calendar_sync import handle_supabase_event

        try:
            normalized = {
                "type": event_type.upper(),
                "table": payload.get("table", "appointments"),
                "record": payload.get("record") or {},
                "old_record": payload.get("old_record") or {},
            }
            logger.info(f"Realtime: evento {event_type} recebido.")

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(handle_supabase_event(normalized))
            except RuntimeError:
                asyncio.run(handle_supabase_event(normalized))

        except Exception as e:
            logger.error(f"Realtime: erro no callback {event_type} — {e}", exc_info=True)

    return callback


async def start_realtime_listener():
    """
    Inicia o listener via cliente ASYNC do Supabase Realtime.
    Chamado como asyncio.create_task() no lifespan do FastAPI.
    """
    global _running
    _running = True

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("Realtime: SUPABASE_URL ou SUPABASE_API_KEY ausente. Listener não iniciado.")
        return

    logger.info("Realtime: iniciando listener assíncrono da tabela `appointments`...")

    while _running:
        try:
            from supabase._async.client import AsyncClient
            from supabase import acreate_client

            client: AsyncClient = await acreate_client(SUPABASE_URL, SUPABASE_KEY)

            channel = client.channel("appointments-calendar-sync")

            channel.on_postgres_changes(
                event="INSERT",
                schema="public",
                table="appointments",
                callback=_make_callback("INSERT"),
            )
            channel.on_postgres_changes(
                event="UPDATE",
                schema="public",
                table="appointments",
                callback=_make_callback("UPDATE"),
            )
            channel.on_postgres_changes(
                event="DELETE",
                schema="public",
                table="appointments",
                callback=_make_callback("DELETE"),
            )

            await channel.subscribe()
            logger.info("✅ Realtime: conectado ao Supabase! Monitorando tabela `appointments`.")

            # Mantém o listener vivo enquanto o bot roda
            while _running:
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("Realtime: listener cancelado (shutdown normal).")
            break
        except Exception as e:
            logger.error(f"Realtime: conexão perdida — {e}. Reconectando em 15s...")
            await asyncio.sleep(15)


async def stop_realtime_listener():
    """Sinaliza o encerramento do listener."""
    global _running
    _running = False
    logger.info("Realtime: listener encerrado.")
