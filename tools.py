import random
import string
from datetime import datetime, date, time, timedelta
from typing import Optional


HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def _parse_time(s: str) -> time:
    return datetime.strptime(s, "%H:%M").time()

def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute

def _to_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def get_today_date(query: str) -> dict:
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "day_name": HARI[now.weekday()],
        "iso": now.isoformat(),
    }


TOOL_DECLARATIONS = [
    {
        "name": "get_today_date",
        "description": "Dapatkan tanggal hari ini.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                        "description": "Input pengguna (boleh diabaikan)."},
            },
            "required": ["query"],
        },
    },
    
]



TOOL_FUNCTIONS = {
    "get_today_date": get_today_date,
}
