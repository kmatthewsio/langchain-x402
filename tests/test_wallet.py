"""Tests for X402Wallet."""

import pytest
from decimal import Decimal

from langchain_x402 import X402Wallet


# Test private key (DO NOT USE IN PRODUCTION)
# This is a well-known test key with no real funds
TEST_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
TEST_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class TestX402Wallet:
    """Test X402Wallet functionality."""

    def test_wallet_initialization(self):
        """Test wallet initializes correctly."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-mainnet",
            budget_usd=10.0,
        )

        assert wallet.address == TEST_ADDRESS
        assert wallet.network == "base-mainnet"
        assert wallet.budget_usd == 10.0
        assert wallet.spent_usd == 0.0
        assert wallet.remaining_usd == 10.0

    def test_wallet_without_0x_prefix(self):
        """Test wallet works without 0x prefix on private key."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY[2:],  # Remove 0x
            network="base-mainnet",
            budget_usd=5.0,
        )

        assert wallet.address == TEST_ADDRESS

    def test_can_afford(self):
        """Test budget checking."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-mainnet",
            budget_usd=1.0,
        )

        assert wallet.can_afford(0.5) is True
        assert wallet.can_afford(1.0) is True
        assert wallet.can_afford(1.01) is False

    def test_units_conversion(self):
        """Test USD <-> units conversion."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-mainnet",
            budget_usd=10.0,
        )

        # USDC has 6 decimals
        assert wallet.usd_to_units(1.0) == 1_000_000
        assert wallet.usd_to_units(0.01) == 10_000
        assert wallet.usd_to_units(0.000001) == 1

        assert wallet.units_to_usd(1_000_000) == Decimal("1")
        assert wallet.units_to_usd(10_000) == Decimal("0.01")
        assert wallet.units_to_usd(1) == Decimal("0.000001")

    def test_sign_payment_tracks_spending(self):
        """Test that signing a payment updates spending."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-sepolia",
            budget_usd=1.0,
        )

        # Sign a $0.10 payment
        signature, nonce = wallet.sign_payment(
            to_address="0x1234567890123456789012345678901234567890",
            amount_units=100_000,  # $0.10
            valid_before=9999999999,
            resource_url="https://example.com/api",
        )

        assert signature is not None
        assert len(nonce) == 32
        assert wallet.spent_usd == pytest.approx(0.1, rel=1e-6)
        assert wallet.remaining_usd == pytest.approx(0.9, rel=1e-6)
        assert len(wallet.payments) == 1

    def test_sign_payment_exceeds_budget(self):
        """Test that signing fails when budget exceeded."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-sepolia",
            budget_usd=0.05,
        )

        with pytest.raises(ValueError, match="Budget exceeded"):
            wallet.sign_payment(
                to_address="0x1234567890123456789012345678901234567890",
                amount_units=100_000,  # $0.10 > $0.05 budget
                valid_before=9999999999,
            )

    def test_payment_summary(self):
        """Test payment summary generation."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-mainnet",
            budget_usd=5.0,
        )

        summary = wallet.get_payment_summary()

        assert summary["address"] == TEST_ADDRESS
        assert summary["network"] == "base-mainnet"
        assert summary["budget_usd"] == 5.0
        assert summary["spent_usd"] == 0.0
        assert summary["remaining_usd"] == 5.0
        assert summary["payment_count"] == 0

    def test_reset_budget(self):
        """Test budget reset."""
        wallet = X402Wallet(
            private_key=TEST_PRIVATE_KEY,
            network="base-sepolia",
            budget_usd=1.0,
        )

        # Make a payment
        wallet.sign_payment(
            to_address="0x1234567890123456789012345678901234567890",
            amount_units=100_000,
            valid_before=9999999999,
        )

        assert wallet.spent_usd > 0
        assert len(wallet.payments) == 1

        # Reset with new budget
        wallet.reset_budget(10.0)

        assert wallet.budget_usd == 10.0
        assert wallet.spent_usd == 0.0
        assert len(wallet.payments) == 0
