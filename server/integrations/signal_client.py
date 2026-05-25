import httpx
from config import settings


async def send_message(recipient: str, message: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{settings.signal_api_url}/v2/send",
            json={
                "message": message,
                "number": settings.signal_bot_number,
                "recipients": [recipient],
            },
        )
