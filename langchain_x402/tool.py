"""
X402 Payment Tool for LangChain agents.

This tool enables LangChain agents to make HTTP requests to x402-enabled APIs,
automatically handling payment negotiation when a 402 response is received.
"""

import base64
import json
from typing import Any, Optional, Type

import httpx
from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from .wallet import X402Wallet


class X402RequestInput(BaseModel):
    """Input schema for X402PaymentTool."""

    url: str = Field(description="The URL to request")
    method: str = Field(default="GET", description="HTTP method (GET, POST, etc.)")
    body: Optional[str] = Field(default=None, description="Request body for POST/PUT")
    headers: Optional[dict[str, str]] = Field(
        default=None, description="Additional headers"
    )
    max_price_usd: Optional[float] = Field(
        default=None,
        description="Maximum price willing to pay for this request (in USD). "
        "If not specified, uses wallet's remaining budget.",
    )


class X402PaymentTool(BaseTool):
    """
    LangChain tool for making HTTP requests with automatic x402 payment handling.

    When a server returns HTTP 402 Payment Required, this tool:
    1. Parses the payment requirements from X-PAYMENT-REQUIRED header
    2. Checks if the price is within budget
    3. Signs an EIP-3009 payment authorization
    4. Retries the request with the X-PAYMENT header
    5. Returns the response data

    Example:
        wallet = X402Wallet(
            private_key=os.environ["WALLET_PRIVATE_KEY"],
            network="base-mainnet",
            budget_usd=10.00
        )

        tool = X402PaymentTool(wallet=wallet)
        agent = create_react_agent(llm, tools=[tool])
        agent.invoke("Fetch data from https://api.example.com/premium")
    """

    name: str = "x402_request"
    description: str = (
        "Make HTTP requests to APIs that may require payment. "
        "Automatically handles x402 payment protocol if the API requires payment. "
        "Use this for accessing premium APIs, paid data sources, or any x402-enabled endpoint. "
        "You can specify a max_price_usd to limit how much you're willing to pay."
    )
    args_schema: Type[BaseModel] = X402RequestInput

    wallet: X402Wallet
    timeout: float = 30.0
    auto_pay: bool = True  # If False, will return payment requirements instead of paying

    def _parse_payment_requirements(self, header_value: str) -> dict[str, Any]:
        """Parse the X-PAYMENT-REQUIRED header (base64-encoded JSON)."""
        try:
            decoded = base64.b64decode(header_value)
            return json.loads(decoded)
        except Exception as e:
            raise ValueError(f"Failed to parse payment requirements: {e}")

    def _build_payment_header(
        self,
        requirements: dict[str, Any],
        signature: str,
        nonce: bytes,
    ) -> str:
        """Build the X-PAYMENT header with signed authorization."""
        payload = {
            "x402Version": requirements.get("x402Version", 1),
            "scheme": requirements.get("scheme", "exact"),
            "network": requirements.get("network"),
            "payload": {
                "signature": signature if signature.startswith("0x") else f"0x{signature}",
                "authorization": {
                    "from": self.wallet.address,
                    "to": requirements["payTo"],
                    "value": str(requirements["maxAmountRequired"]),
                    "validAfter": "0",
                    "validBefore": str(requirements["validUntil"]),
                    "nonce": f"0x{nonce.hex()}",
                },
            },
        }
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def _run(
        self,
        url: str,
        method: str = "GET",
        body: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        max_price_usd: Optional[float] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """
        Execute the HTTP request with x402 payment handling.

        Args:
            url: The URL to request
            method: HTTP method
            body: Request body for POST/PUT
            headers: Additional headers
            max_price_usd: Maximum price willing to pay
            run_manager: Callback manager

        Returns:
            Response body as string, or error message
        """
        request_headers = headers or {}

        with httpx.Client(timeout=self.timeout) as client:
            # Initial request
            response = client.request(
                method=method,
                url=url,
                content=body,
                headers=request_headers,
            )

            # If not 402, return response directly
            if response.status_code != 402:
                if response.status_code >= 400:
                    return f"Error {response.status_code}: {response.text}"
                return response.text

            # Handle 402 Payment Required
            payment_header = (
                response.headers.get("PAYMENT-REQUIRED")
                or response.headers.get("X-PAYMENT-REQUIRED")
            )
            if not payment_header:
                return "Error: Received 402 but no PAYMENT-REQUIRED header"

            try:
                requirements = self._parse_payment_requirements(payment_header)
            except ValueError as e:
                return f"Error parsing payment requirements: {e}"

            # Extract payment details
            amount_units = int(requirements.get("maxAmountRequired", 0))
            amount_usd = float(self.wallet.units_to_usd(amount_units))
            pay_to = requirements.get("payTo")
            valid_until = int(requirements.get("validUntil", 0))
            network = requirements.get("network")

            # Check network compatibility
            if network and network != self.wallet.network:
                return (
                    f"Error: Network mismatch. API requires {network}, "
                    f"wallet is configured for {self.wallet.network}"
                )

            # Check price limit
            effective_max = max_price_usd or self.wallet.remaining_usd
            if amount_usd > effective_max:
                return (
                    f"Payment required: ${amount_usd:.4f} USDC to {pay_to}. "
                    f"Exceeds limit of ${effective_max:.4f}. "
                    f"Set higher max_price_usd to proceed."
                )

            # Check budget
            if not self.wallet.can_afford(amount_usd):
                return (
                    f"Payment required: ${amount_usd:.4f} USDC. "
                    f"Insufficient budget: ${self.wallet.remaining_usd:.4f} remaining."
                )

            if not self.auto_pay:
                return (
                    f"Payment required: ${amount_usd:.4f} USDC to {pay_to}. "
                    f"Set auto_pay=True to automatically pay."
                )

            # Sign the payment
            try:
                signature, nonce = self.wallet.sign_payment(
                    to_address=pay_to,
                    amount_units=amount_units,
                    valid_before=valid_until,
                    resource_url=url,
                )
            except ValueError as e:
                return f"Payment signing failed: {e}"

            # Build payment header
            payment_value = self._build_payment_header(requirements, signature, nonce)

            # Retry with payment
            request_headers["PAYMENT-SIGNATURE"] = payment_value
            paid_response = client.request(
                method=method,
                url=url,
                content=body,
                headers=request_headers,
            )

            if paid_response.status_code >= 400:
                return (
                    f"Error after payment: {paid_response.status_code} - "
                    f"{paid_response.text}"
                )

            # Log payment response if present
            payment_response = (
                paid_response.headers.get("PAYMENT-RESPONSE")
                or paid_response.headers.get("X-PAYMENT-RESPONSE")
            )
            if payment_response and run_manager:
                try:
                    pr_data = json.loads(base64.b64decode(payment_response))
                    run_manager.on_text(
                        f"Payment settled: tx={pr_data.get('txHash', 'unknown')}"
                    )
                except Exception:
                    pass

            return paid_response.text

    async def _arun(
        self,
        url: str,
        method: str = "GET",
        body: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        max_price_usd: Optional[float] = None,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Async version of _run."""
        request_headers = headers or {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Initial request
            response = await client.request(
                method=method,
                url=url,
                content=body,
                headers=request_headers,
            )

            # If not 402, return response directly
            if response.status_code != 402:
                if response.status_code >= 400:
                    return f"Error {response.status_code}: {response.text}"
                return response.text

            # Handle 402 Payment Required
            payment_header = (
                response.headers.get("PAYMENT-REQUIRED")
                or response.headers.get("X-PAYMENT-REQUIRED")
            )
            if not payment_header:
                return "Error: Received 402 but no PAYMENT-REQUIRED header"

            try:
                requirements = self._parse_payment_requirements(payment_header)
            except ValueError as e:
                return f"Error parsing payment requirements: {e}"

            # Extract payment details
            amount_units = int(requirements.get("maxAmountRequired", 0))
            amount_usd = float(self.wallet.units_to_usd(amount_units))
            pay_to = requirements.get("payTo")
            valid_until = int(requirements.get("validUntil", 0))
            network = requirements.get("network")

            # Check network compatibility
            if network and network != self.wallet.network:
                return (
                    f"Error: Network mismatch. API requires {network}, "
                    f"wallet is configured for {self.wallet.network}"
                )

            # Check price limit
            effective_max = max_price_usd or self.wallet.remaining_usd
            if amount_usd > effective_max:
                return (
                    f"Payment required: ${amount_usd:.4f} USDC to {pay_to}. "
                    f"Exceeds limit of ${effective_max:.4f}. "
                    f"Set higher max_price_usd to proceed."
                )

            # Check budget
            if not self.wallet.can_afford(amount_usd):
                return (
                    f"Payment required: ${amount_usd:.4f} USDC. "
                    f"Insufficient budget: ${self.wallet.remaining_usd:.4f} remaining."
                )

            if not self.auto_pay:
                return (
                    f"Payment required: ${amount_usd:.4f} USDC to {pay_to}. "
                    f"Set auto_pay=True to automatically pay."
                )

            # Sign the payment
            try:
                signature, nonce = self.wallet.sign_payment(
                    to_address=pay_to,
                    amount_units=amount_units,
                    valid_before=valid_until,
                    resource_url=url,
                )
            except ValueError as e:
                return f"Payment signing failed: {e}"

            # Build payment header
            payment_value = self._build_payment_header(requirements, signature, nonce)

            # Retry with payment
            request_headers["PAYMENT-SIGNATURE"] = payment_value
            paid_response = await client.request(
                method=method,
                url=url,
                content=body,
                headers=request_headers,
            )

            if paid_response.status_code >= 400:
                return (
                    f"Error after payment: {paid_response.status_code} - "
                    f"{paid_response.text}"
                )

            return paid_response.text
