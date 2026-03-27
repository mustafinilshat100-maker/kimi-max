from datetime import datetime, timezone

def safe_parse_timestamp(ts):
    """Parse timestamp to timezone-aware UTC datetime"""
    if ts is None:
        return None
    
    # Already datetime object
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            # Naive datetime — assume UTC
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    
    # PostgreSQL timestamp string → safe UTC
    if isinstance(ts, str):
        try:
            # Handle ISO format with Z
            ts_clean = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except:
            pass
    
    # UNIX timestamp (seconds)
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except:
        pass
    
    # UNIX timestamp (milliseconds)
    try:
        return datetime.fromtimestamp(float(ts) / 1000, tz=timezone.utc)
    except:
        pass
    
    return None


def utc_now():
    """Return current UTC time with timezone info"""
    return datetime.now(timezone.utc)


def safe_diff_seconds(dt1, dt2):
    """Safely calculate difference between two datetimes in seconds"""
    if dt1 is None or dt2 is None:
        return None
    
    dt1 = safe_parse_timestamp(dt1)
    dt2 = safe_parse_timestamp(dt2)
    
    if dt1 is None or dt2 is None:
        return None
    
    try:
        return (dt1 - dt2).total_seconds()
    except:
        return None
