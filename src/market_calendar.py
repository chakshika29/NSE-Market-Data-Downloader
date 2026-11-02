"""Market calendar and trading session checker for NSE.

NSE normal trading hours: Monday to Friday, 09:15 AM to 03:30 PM IST (UTC+05:30).
Avoids unnecessary requests during closed market hours unless explicitly requested.
"""

from datetime import datetime, time, timezone, timedelta
from typing import Optional


# Indian Standard Time offset: UTC+05:30
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

# Standard NSE Equity Market Session Hours
MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)

# Known NSE Trading Holidays (Month, Day) for general sanity checking
KNOWN_HOLIDAYS_MM_DD = {
    (1, 26),   # Republic Day
    (3, 25),   # Holi (approximate annual)
    (4, 14),   # Ambedkar Jayanti
    (5, 1),    # Maharashtra Day
    (8, 15),   # Independence Day
    (10, 2),   # Gandhi Jayanti
    (11, 1),   # Diwali Laxmi Pujan (approximate)
    (12, 25),  # Christmas
}


def get_current_ist_time() -> datetime:
    """Return current datetime localized to Indian Standard Time (IST)."""
    return datetime.now(timezone.utc).astimezone(IST_OFFSET)


def is_market_open(dt: Optional[datetime] = None) -> tuple[bool, str]:
    """Check whether the NSE equity market is currently open for trading.

    Returns:
        (is_open, reason_string)
    """
    current_dt = dt or get_current_ist_time()

    # 1. Check weekend
    # weekday(): Monday is 0, Sunday is 6
    if current_dt.weekday() in (5, 6):
        day_name = "Saturday" if current_dt.weekday() == 5 else "Sunday"
        return False, f"Market is closed today ({day_name} weekend)."

    # 2. Check known annual holidays
    if (current_dt.month, current_dt.day) in KNOWN_HOLIDAYS_MM_DD:
        return False, f"Market is closed today (declared holiday: {current_dt.strftime('%d-%b')})."

    # 3. Check time of day
    curr_time = current_dt.time()
    if curr_time < MARKET_OPEN_TIME:
        return (
            False,
            f"Market has not opened yet (current IST: {curr_time.strftime('%H:%M:%S')}, opens at 09:15:00 IST).",
        )

    if curr_time > MARKET_CLOSE_TIME:
        return (
            False,
            f"Market is closed for the day (current IST: {curr_time.strftime('%H:%M:%S')}, closed at 15:30:00 IST).",
        )

    return True, f"Market is currently open (current IST: {curr_time.strftime('%H:%M:%S')})."
