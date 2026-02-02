"""
X402 Wallet for managing USDC payments in AI agents.

The wallet handles:
- Budget tracking
- EIP-3009 signature generation
- Payment history
"""

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .eip3009 import (
    TransferAuthorization,
    generate_nonce,
    get_wallet_address,
    sign_transfer_authorization,
)


@dataclass
class PaymentRecord:
    """Record of a payment made by the wallet."""

    timestamp: float
    to_address: str
    amount_usd: Decimal
    amount_units: int
    network: str
    nonce: str
    signature: str
    resource_url: str


@dataclass
class X402Wallet:
    """
    Wallet for x402 payments.

    Manages USDC budget and signs EIP-3009 authorizations for AI agents.

    Example:
        wallet = X402Wallet(
            private_key=os.environ["WALLET_PRIVATE_KEY"],
            network="base-mainnet",
            budget_usd=10.00
        )

        # Check if we can afford a payment
        if wallet.can_afford(0.01):
            signature = wallet.sign_payment(to_address, amount_units, valid_before)
    """

    private_key: str
    network: str = "base-mainnet"
    budget_usd: float = 10.0
    _spent_usd: float = field(default=0.0, init=False)
    _payments: list[PaymentRecord] = field(default_factory=list, init=False)
    _address: Optional[str] = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize wallet address from private key."""
        self._address = get_wallet_address(self.private_key)

    @property
    def address(self) -> str:
        """Get the wallet address."""
        if self._address is None:
            self._address = get_wallet_address(self.private_key)
        return self._address

    @property
    def spent_usd(self) -> float:
        """Total USD spent from this wallet."""
        return self._spent_usd

    @property
    def remaining_usd(self) -> float:
        """Remaining budget in USD."""
        return max(0.0, self.budget_usd - self._spent_usd)

    @property
    def payments(self) -> list[PaymentRecord]:
        """List of all payments made."""
        return self._payments.copy()

    def can_afford(self, amount_usd: float) -> bool:
        """
        Check if the wallet can afford a payment.

        Args:
            amount_usd: Amount in USD

        Returns:
            True if remaining budget >= amount
        """
        return self.remaining_usd >= amount_usd

    def units_to_usd(self, units: int) -> Decimal:
        """
        Convert USDC smallest units to USD.

        USDC has 6 decimals, so 1_000_000 units = $1.00

        Args:
            units: Amount in smallest units

        Returns:
            Amount in USD as Decimal
        """
        return Decimal(units) / Decimal(1_000_000)

    def usd_to_units(self, usd: float) -> int:
        """
        Convert USD to USDC smallest units.

        Args:
            usd: Amount in USD

        Returns:
            Amount in smallest units
        """
        return int(Decimal(str(usd)) * Decimal(1_000_000))

    def sign_payment(
        self,
        to_address: str,
        amount_units: int,
        valid_before: int,
        resource_url: str = "",
    ) -> tuple[str, bytes]:
        """
        Sign an EIP-3009 payment authorization.

        Args:
            to_address: Recipient address
            amount_units: Amount in smallest units (6 decimals)
            valid_before: Unix timestamp when authorization expires
            resource_url: URL of the resource being paid for (for logging)

        Returns:
            Tuple of (signature hex string, nonce bytes)

        Raises:
            ValueError: If budget exceeded
        """
        amount_usd = float(self.units_to_usd(amount_units))

        if not self.can_afford(amount_usd):
            raise ValueError(
                f"Budget exceeded: need ${amount_usd:.4f}, "
                f"have ${self.remaining_usd:.4f} remaining"
            )

        # Generate random nonce
        nonce = generate_nonce()

        # Create authorization
        authorization = TransferAuthorization(
            from_address=self.address,
            to_address=to_address,
            value=amount_units,
            valid_after=0,  # Immediately valid
            valid_before=valid_before,
            nonce=nonce,
        )

        # Sign it
        signature = sign_transfer_authorization(
            self.private_key,
            authorization,
            self.network,
        )

        # Record the payment
        self._spent_usd += amount_usd
        self._payments.append(
            PaymentRecord(
                timestamp=time.time(),
                to_address=to_address,
                amount_usd=Decimal(str(amount_usd)),
                amount_units=amount_units,
                network=self.network,
                nonce=nonce.hex(),
                signature=signature,
                resource_url=resource_url,
            )
        )

        return signature, nonce

    def get_payment_summary(self) -> dict:
        """
        Get a summary of wallet activity.

        Returns:
            Dictionary with budget, spent, remaining, and payment count
        """
        return {
            "address": self.address,
            "network": self.network,
            "budget_usd": self.budget_usd,
            "spent_usd": self.spent_usd,
            "remaining_usd": self.remaining_usd,
            "payment_count": len(self._payments),
        }

    def reset_budget(self, new_budget_usd: Optional[float] = None) -> None:
        """
        Reset the wallet budget and clear payment history.

        Args:
            new_budget_usd: New budget amount, or None to keep current budget
        """
        if new_budget_usd is not None:
            self.budget_usd = new_budget_usd
        self._spent_usd = 0.0
        self._payments.clear()
