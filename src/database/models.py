"""
Database models for NoTocBot.
Defines User, Debtor, Alias, and Transaction tables.
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger,
    String,
    DateTime,
    Numeric,
    Enum as SQLEnum,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column

Base = declarative_base()


class User(Base):
    """Users table - Telegram users who are creditors."""
    
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    debtors = relationship("Debtor", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, name={self.full_name})>"


class Debtor(Base):
    """Debtors table - People who owe money to users."""
    
    __tablename__ = "debtors"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="debtors")
    aliases = relationship("Alias", back_populates="debtor", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="debtor", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Debtor(id={self.id}, name={self.name}, user_id={self.user_id})>"


class Alias(Base):
    """Aliases table - Nicknames/short names for debtors."""
    
    __tablename__ = "aliases"
    
    id = Column(BigInteger, primary_key=True)
    debtor_id = Column(BigInteger, ForeignKey("debtors.id"), nullable=False, index=True)
    alias_name = Column(String(255), nullable=False)
    
    # Relationships
    debtor = relationship("Debtor", back_populates="aliases")
    
    # Index for fast lookup
    __table_args__ = (
        Index("idx_alias_name", "alias_name"),
    )
    
    def __repr__(self):
        return f"<Alias(id={self.id}, name={self.alias_name}, debtor_id={self.debtor_id})>"


class Transaction(Base):
    """Transactions table - Debt/Credit history."""
    
    __tablename__ = "transactions"
    
    id = Column(BigInteger, primary_key=True)
    debtor_id = Column(BigInteger, ForeignKey("debtors.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)  # Always positive
    type = Column(SQLEnum("DEBT", "CREDIT", name="transaction_type"), nullable=False)
    note = Column(String(500), nullable=True)
    group_id = Column(BigInteger, nullable=True)  # For future grouping
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    debtor = relationship("Debtor", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction(id={self.id}, debtor_id={self.debtor_id}, type={self.type}, amount={self.amount})>"


__all__ = ["Base", "User", "Debtor", "Alias", "Transaction"]
