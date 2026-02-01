from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class ContractType(str, Enum):
    OPTION = "option"
    FUTURE = "future"


class PutCall(str, Enum):
    PUT = "put"
    CALL = "call"


class DerivativeContract(Base):
    __tablename__ = "derivative_contracts"

    # Primary key
    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Required fields
    underlying: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    contract_type: Mapped[ContractType] = mapped_column(String(20), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Options-specific fields (nullable for futures)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    put_call: Mapped[PutCall | None] = mapped_column(String(10), nullable=True)

    @property
    def days_to_expiry(self) -> int:
        """Calculate days until expiration."""
        today = date.today()
        delta = self.expiry - today
        return delta.days

    @property
    def is_expiring_soon(self) -> bool:
        """Check if contract is expiring within 5 days."""
        return self.days_to_expiry <= 5
