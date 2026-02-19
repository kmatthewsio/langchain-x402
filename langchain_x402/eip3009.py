"""
EIP-3009 signature utilities for x402 payments.

EIP-3009 enables gasless USDC transfers via signed authorizations.
The payer signs a TransferWithAuthorization message, and the recipient
submits the transaction (paying gas).
"""

import os
import secrets
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data


# USDC contract addresses by network (CAIP-2 keys, with legacy aliases)
USDC_CONTRACTS: dict[str, str] = {
    # CAIP-2 format (canonical)
    "eip155:8453": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "eip155:84532": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "eip155:1": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "eip155:11155111": "0x1c7D4B196Cb0C7B01d064914d0da28F12c7d0b86",
    "eip155:5042002": "0x3600000000000000000000000000000000000000",
    # Legacy aliases (backwards compat)
    "base-mainnet": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "ethereum-mainnet": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "ethereum-sepolia": "0x1c7D4B196Cb0C7B01d064914d0da28F12c7d0b86",
    "arc-testnet": "0x3600000000000000000000000000000000000000",
}

# Chain IDs by network (CAIP-2 keys, with legacy aliases)
CHAIN_IDS: dict[str, int] = {
    # CAIP-2 format (canonical)
    "eip155:8453": 8453,
    "eip155:84532": 84532,
    "eip155:1": 1,
    "eip155:11155111": 11155111,
    "eip155:5042002": 5042002,
    # Legacy aliases (backwards compat)
    "base-mainnet": 8453,
    "base-sepolia": 84532,
    "ethereum-mainnet": 1,
    "ethereum-sepolia": 11155111,
    "arc-testnet": 5042002,
}


@dataclass
class TransferAuthorization:
    """EIP-3009 TransferWithAuthorization parameters."""

    from_address: str
    to_address: str
    value: int  # Amount in smallest units (6 decimals for USDC)
    valid_after: int  # Unix timestamp
    valid_before: int  # Unix timestamp
    nonce: bytes  # 32 random bytes

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for signing."""
        return {
            "from": self.from_address,
            "to": self.to_address,
            "value": self.value,
            "validAfter": self.valid_after,
            "validBefore": self.valid_before,
            "nonce": self.nonce,
        }


def generate_nonce() -> bytes:
    """Generate a random 32-byte nonce for EIP-3009."""
    return secrets.token_bytes(32)


def build_eip712_message(
    authorization: TransferAuthorization,
    network: str,
) -> dict[str, Any]:
    """
    Build EIP-712 typed data for TransferWithAuthorization.

    Args:
        authorization: The transfer authorization parameters
        network: Network name (e.g., "base-mainnet")

    Returns:
        EIP-712 typed data structure
    """
    usdc_address = USDC_CONTRACTS.get(network)
    chain_id = CHAIN_IDS.get(network)

    if not usdc_address or not chain_id:
        raise ValueError(f"Unsupported network: {network}")

    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": "USD Coin",
            "version": "2",
            "chainId": chain_id,
            "verifyingContract": usdc_address,
        },
        "message": {
            "from": authorization.from_address,
            "to": authorization.to_address,
            "value": authorization.value,
            "validAfter": authorization.valid_after,
            "validBefore": authorization.valid_before,
            "nonce": "0x" + authorization.nonce.hex(),
        },
    }


def sign_transfer_authorization(
    private_key: str,
    authorization: TransferAuthorization,
    network: str,
) -> str:
    """
    Sign an EIP-3009 TransferWithAuthorization.

    Args:
        private_key: Hex-encoded private key (with or without 0x prefix)
        authorization: The transfer authorization parameters
        network: Network name (e.g., "base-mainnet")

    Returns:
        Hex-encoded signature
    """
    # Normalize private key
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # Build EIP-712 message
    typed_data = build_eip712_message(authorization, network)

    # Sign the message - pass types without EIP712Domain (library adds it)
    message_types = {
        k: v for k, v in typed_data["types"].items() if k != "EIP712Domain"
    }

    account = Account.from_key(private_key)
    signed = account.sign_typed_data(
        typed_data["domain"],
        message_types,
        typed_data["message"],
    )

    return signed.signature.hex()


def get_wallet_address(private_key: str) -> str:
    """
    Get the wallet address from a private key.

    Args:
        private_key: Hex-encoded private key

    Returns:
        Checksummed wallet address
    """
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    account = Account.from_key(private_key)
    return account.address
