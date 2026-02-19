"""
langchain-x402: x402 payment protocol integration for LangChain.

Enable AI agents to pay for APIs with USDC using the x402 protocol.

Example:
    from langchain_x402 import X402Wallet, X402PaymentTool

    wallet = X402Wallet(
        private_key=os.environ["WALLET_PRIVATE_KEY"],
        network="base-mainnet",
        budget_usd=10.00
    )

    tool = X402PaymentTool(wallet=wallet)
    agent = create_react_agent(llm, tools=[tool])
"""

from .eip3009 import (
    CHAIN_IDS,
    USDC_CONTRACTS,
    TransferAuthorization,
    generate_nonce,
    get_wallet_address,
    sign_transfer_authorization,
)
from .tool import X402PaymentTool, X402RequestInput
from .wallet import PaymentRecord, X402Wallet

__version__ = "0.2.0"

__all__ = [
    # Main classes
    "X402Wallet",
    "X402PaymentTool",
    # Input/output types
    "X402RequestInput",
    "PaymentRecord",
    # EIP-3009 utilities
    "TransferAuthorization",
    "sign_transfer_authorization",
    "generate_nonce",
    "get_wallet_address",
    # Constants
    "USDC_CONTRACTS",
    "CHAIN_IDS",
]
