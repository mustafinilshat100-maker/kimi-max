from sqlalchemy import create_engine, Column, String, Float, Integer, BigInteger, DateTime, Boolean, Index, Text, event, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import func
from datetime import datetime, timezone, timedelta
import os
import threading
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()

def utc_now():
    """Return timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)

class TokenMetrics(Base):
    """Historical metrics for token analysis - used for velocity calculations"""
    __tablename__ = 'token_metrics'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=utc_now, index=True)
    token_address = Column(String(100), index=True)
    chain = Column(String(20), index=True)
    symbol = Column(String(50))
    name = Column(String(200))
    
    # Price & Market
    price = Column(Float)
    price_change_5m = Column(Float)
    price_change_1h = Column(Float)
    price_change_24h = Column(Float)
    market_cap = Column(Float)
    
    # Volume
    volume_24h = Column(Float)
    volume_5m = Column(Float)
    volume_1h = Column(Float)
    
    # Transactions
    tx_count_24h = Column(Integer)
    tx_count_5m = Column(Integer)
    buy_count_5m = Column(Integer)
    sell_count_5m = Column(Integer)
    buy_volume_5m = Column(Float)
    sell_volume_5m = Column(Float)
    
    # Liquidity
    liquidity = Column(Float)
    liquidity_change_5m = Column(Float)
    
    # Metadata
    pair_address = Column(String(100))
    dex_id = Column(String(50))
    token_age_hours = Column(Float)
    top_holder_share = Column(Float)
    holders_count = Column(Integer)
    
    # Calculated Metrics
    buy_pressure = Column(Float)
    volume_velocity = Column(Float)
    volume_acceleration = Column(Float)
    tx_growth = Column(Float)
    liquidity_velocity = Column(Float)
    holders_velocity = Column(Float, default=1.0)
    
    __table_args__ = (
        Index('idx_token_time', 'token_address', 'timestamp'),
        Index('idx_chain_time', 'chain', 'timestamp'),
    )

class Signal(Base):
    """Generated signals for trading"""
    __tablename__ = 'signals'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=utc_now)
    signal_type = Column(String(20))  # PUMP, DIP
    
    # Token info
    token_address = Column(String(100), index=True)
    chain = Column(String(20))
    symbol = Column(String(50))
    name = Column(String(200))
    
    # Signal data
    price_at_signal = Column(Float)
    pump_score = Column(Float)
    dip_score = Column(Float)
    alpha_score = Column(Float)
    
    # Metrics at signal time
    volume_velocity = Column(Float)
    buy_pressure = Column(Float)
    tx_growth = Column(Float)
    liquidity_velocity = Column(Float)
    whale_activity = Column(Boolean)
    
    # Classification
    signal_strength = Column(String(20))  # STRONG_BUY, WATCH, WEAK
    
    # Risk check
    rug_pull_risk = Column(Boolean, default=False)
    liquidity_ratio = Column(Float)
    
    # Result tracking
    price_30m_later = Column(Float)
    price_change_30m = Column(Float)
    verified = Column(Boolean, default=False)
    win = Column(Boolean)
    
    # NaN detection and validation
    nan_detected = Column(Boolean, default=False)
    metrics_valid = Column(Boolean, default=True)
    debug_info = Column(Text)

    __table_args__ = (
        Index('idx_signal_time', 'created_at', 'signal_type'),
        Index('idx_token_signal', 'token_address', 'created_at'),
    )

class ActiveToken(Base):
    """Currently tracked tokens"""
    __tablename__ = 'active_tokens'
    
    token_address = Column(String(100), primary_key=True)
    chain = Column(String(20), primary_key=True)
    symbol = Column(String(50))
    name = Column(String(200))
    
    first_seen = Column(DateTime, default=utc_now)
    last_updated = Column(DateTime, default=utc_now)
    
    # Current state
    price = Column(Float)
    liquidity = Column(Float)
    volume_24h = Column(Float)
    market_cap = Column(Float)
    token_age_hours = Column(Float)
    
    # Risk flags
    is_rug_pull_risk = Column(Boolean, default=False)
    is_high_risk = Column(Boolean, default=False)
    
    # Signal count
    signals_generated = Column(Integer, default=0)

class SignalResult(Base):
    """Track signal performance for statistics"""
    __tablename__ = 'signal_results'
    
    id = Column(Integer, primary_key=True)
    signal_id = Column(BigInteger, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    # Token info
    token_address = Column(String(100), index=True)
    chain = Column(String(20))
    symbol = Column(String(50))
    
    # Signal data
    signal_type = Column(String(20))
    price_at_signal = Column(Float)
    alpha_score = Column(Float)
    signal_strength = Column(String(20))
    
    # Price tracking (auto-updated)
    price_after_5m = Column(Float)
    price_after_15m = Column(Float)
    price_after_30m = Column(Float)
    
    # ROI calculation
    roi_5m = Column(Float)
    roi_15m = Column(Float)
    roi_30m = Column(Float)
    
    # Win/Loss
    win_15m = Column(Boolean)
    win_30m = Column(Boolean)
    
    # Status
    is_complete = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('idx_result_signal', 'signal_id'),
        Index('idx_result_token', 'token_address', 'created_at'),
        Index('idx_result_complete', 'is_complete'),
    )


class PriceHistory(Base):
    """OHLCV history for timeframe analysis"""
    __tablename__ = 'price_history'
    
    id = Column(Integer, primary_key=True)
    token_address = Column(String(100), index=True)
    chain = Column(String(20))
    timeframe = Column(String(10))  # 1m, 5m, 15m, 1h
    timestamp = Column(DateTime, default=utc_now)
    
    # OHLCV
    open_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    close_price = Column(Float)
    volume = Column(Float)
    
    __table_args__ = (
        Index('idx_price_token_tf', 'token_address', 'timeframe', 'timestamp'),
    )


# Global engine and session factory (thread-safe for SQLite)
_engine = None
_SessionFactory = None
_lock = threading.Lock()

def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and other pragmas for better SQLite performance"""
    cursor = dbapi_conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL')
    cursor.execute('PRAGMA synchronous=NORMAL')
    cursor.execute('PRAGMA cache_size=-64000')  # 64MB cache
    cursor.execute('PRAGMA temp_store=MEMORY')
    cursor.close()

def init_database(db_path: str = None) -> object:
    """
    Initialize SQLite database with WAL mode.
    Thread-safe singleton pattern.
    """
    global _engine, _SessionFactory
    
    with _lock:
        if _engine is not None:
            return _engine
        
        if db_path is None:
            db_path = os.getenv('DATABASE_PATH', '/root/.openclaw/workspace/crypto_hunter/hunter.db')
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # SQLite with WAL mode for concurrent access
        _engine = create_engine(
            f'sqlite:///{db_path}',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,  # Single connection for SQLite
            echo=False
        )
        
        # Set WAL mode and performance pragmas
        event.listen(_engine, 'connect', _set_sqlite_pragma)
        
        # Create tables
        Base.metadata.create_all(_engine)
        
        # Create session factory
        _SessionFactory = sessionmaker(bind=_engine)
        
        logger.info(f"SQLite database initialized: {db_path}")
        return _engine

def get_session() -> Session:
    """Get a new database session (thread-safe)"""
    global _engine, _SessionFactory
    
    if _engine is None:
        init_database()
    
    return _SessionFactory()

def cleanup_old_data(session: Session, hours: int = 72):
    """Remove data older than specified hours"""
    cutoff = utc_now() - timedelta(hours=hours)
    
    # Cleanup TokenMetrics
    session.query(TokenMetrics).filter(TokenMetrics.timestamp < cutoff).delete()
    
    # Cleanup PriceHistory (keep more recent for analysis)
    price_cutoff = utc_now() - timedelta(hours=hours * 2)
    session.query(PriceHistory).filter(PriceHistory.timestamp < price_cutoff).delete()
    
    # Cleanup incomplete SignalResults older than 1 hour
    result_cutoff = utc_now() - timedelta(hours=1)
    session.query(SignalResult).filter(
        SignalResult.created_at < result_cutoff,
        SignalResult.is_complete == False
    ).delete()
    
    session.commit()
    logger.info(f"Cleanup completed: removed data older than {hours}h")
