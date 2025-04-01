import os
import logging
from pyrogram import Client, filters
import asyncio
import nest_asyncio
import requests
import json

# Aplicar nest_asyncio
nest_asyncio.apply()

# Configuración del bot
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN = int(os.getenv("ADMIN"))  # ID del administrador
API_KEYS = os.getenv("API_KEYS").split(",")  # Claves separadas por comas
API_BASE_URL = "https://api.render.com/v1"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Función para analizar rangos de índices
def parse_indices(indices_str):
    if indices_str.strip().lower() == "all":
        return list(range(1, len(API_KEYS) + 1))  # Retorna todos los índices comenzando en 1

    indices = set()
    try:
        for part in indices_str.split(","):
            if "-" in part:  # Rango (e.g., 1-3)
                start, end = map(int, part.split("-"))
                indices.update(range(start, end + 1))
            else:  # Índice único (e.g., 3)
                indices.add(int(part))
        
        # Ajustar índices basados en 1 a índices de lista basados en 0
        indices = {i - 1 for i in indices}
    except ValueError:
        raise ValueError("Formato inválido para índices. Usa números, rangos (e.g., 1-3), o 'all'.")
    
    return sorted(indices)

# Función para suspender o activar servicios
def gestionar_servicio(action, indices_str):
    try:
        indices = parse_indices(indices_str)

        # Validar que los índices estén en el rango permitido
        if any(i < 0 or i >= len(API_KEYS) for i in indices):
            return f"Uno o más índices son inválidos. Usa números entre 1 y {len(API_KEYS)}, rangos o 'all'."

        resultados = []
        for api_index in indices:
            api_key = API_KEYS[api_index]
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            service_url = f"{API_BASE_URL}/services"
            
            response = requests.get(service_url, headers=headers)
            response.raise_for_status()
            services = response.json() or []

            if not services:
                resultados.append(f"No se encontraron servicios para la clave en el índice {api_index + 1}.")
                continue

            for servicio in services:
                service_id = servicio.get("service", {}).get("id")
                service_name = servicio.get("service", {}).get("name")
                suspended = servicio.get("service", {}).get("suspended")

                if not all([service_id, service_name, suspended]):
                    continue

                if action == "suspend" and suspended == "not_suspended":
                    response = requests.post(f"{API_BASE_URL}/services/{service_id}/suspend", headers=headers)
                    if response.status_code in [200, 202]:
                        resultados.append(f"Servicio {service_name} suspendido correctamente.")
                    else:
                        resultados.append(f"Error al suspender {service_name}: {response.status_code}")

                elif action == "resume" and suspended == "suspended":
                    response = requests.post(f"{API_BASE_URL}/services/{service_id}/resume", headers=headers)
                    if response.status_code in [200, 202]:
                        resultados.append(f"Servicio {service_name} activado correctamente.")

                        # Inicia el redeploy después de activar
                        redeploy_result = trigger_redeploy(service_id, api_key, service_name)
                        resultados.append(redeploy_result)
                    else:
                        resultados.append(f"Error al activar {service_name}: {response.status_code}")

        return "\n".join(resultados) if resultados else f"No se encontró ningún servicio para {action}."
    except ValueError as e:
        logger.error(f"Error al analizar índices: {str(e)}")
        return f"Error: {str(e)}"
    except Exception as e:
        logger.error(f"Error al gestionar servicio: {str(e)}")
        return f"Se produjo un error: {str(e)}"

# Función para realizar redeploy desde Render
def trigger_redeploy(service_id, api_key, service_name):
    try:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        redeploy_url = f"{API_BASE_URL}/services/{service_id}/deploys"

        response = requests.post(redeploy_url, headers=headers)
        if response.status_code == 201:  # Código que indica "build_in_progress"
            return f"El bot se está reiniciando y el servicio '{service_name}' está en progreso de deploy."
        elif response.status_code in [200, 202]:  # Otros posibles códigos exitosos
            return f"Redeploy iniciado correctamente para el servicio '{service_name}'."
        else:
            return f"Error al iniciar el redeploy: {response.status_code} - {response.text}"
    except Exception as e:
        logger.error(f"Error al iniciar el redeploy: {str(e)}")
        return f"Se produjo un error al intentar redeploy: {str(e)}"

# Filtro para comandos solo del administrador
@bot.on_message(filters.command(["active", "suspend"]) & filters.user(ADMIN))
async def handle_commands(client, message):
    try:
        command, indices_str = message.text.split(" ", 1)
        action = "resume" if command == "/active" else "suspend"
        result = gestionar_servicio(action, indices_str)
        await message.reply_text(result)
    except ValueError:
        await message.reply_text("Por favor, usa el comando correctamente: /active <índices> o /suspend <índices>")
    except Exception as e:
        logger.error(f"Error en el comando: {str(e)}")
        await message.reply_text("Ocurrió un error al procesar tu solicitud.")

async def main():
    await bot.start()
    print("Bot iniciado y operativo.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot detenido manualmente.")
