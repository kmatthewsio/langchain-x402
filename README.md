# langchain-x402

[![PyPI version](https://badge.fury.io/py/langchain-x402.svg)](https://pypi.org/project/langchain-x402/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Enable AI agents to pay for APIs with USDC using the x402 protocol.**

langchain-x402 integrates the [x402 payment protocol](https://x402.org) with LangChain, allowing your AI agents to autonomously access paid APIs without managing API keys or subscriptions.

## What is x402?

x402 is the HTTP-native payment protocol that finally implements the `402 Payment Required` status code. Instead of API keys and monthly subscriptions, software pays software—per request, in USDC, with cryptographic proof.

**How it works:**
1. Agent requests a resource
2. Server returns `402 Payment Required` with price info
3. Agent signs a USDC payment authorization (EIP-3009)
4. Agent retries with payment proof
5. Server settles on-chain, returns data

All in a single HTTP round-trip.

## Installation

```bash
pip install langchain-x402
```

## Quick Start

```python
import os
from langchain_x402 import X402Wallet, X402PaymentTool
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent

# 1. Create a wallet with a USDC budget
wallet = X402Wallet(
    private_key=os.environ["WALLET_PRIVATE_KEY"],
    network="eip155:8453",  # Base mainnet (CAIP-2 format)
    budget_usd=10.00
)

# 2. Create the payment tool
tool = X402PaymentTool(wallet=wallet)

# 3. Add to your agent
llm = ChatOpenAI(model="gpt-4o")
agent = create_react_agent(llm, tools=[tool], prompt=your_prompt)
executor = AgentExecutor(agent=agent, tools=[tool])

# 4. Agent can now access any x402-enabled API
result = executor.invoke({
    "input": "Get the premium analysis from https://sandbox.agentrails.io/api/x402/protected/analysis"
})
```

## Try It with the Sandbox

The [AgentRails Sandbox](https://sandbox.agentrails.io) is a free test environment with x402-protected endpoints you can hit right away. No signup required to see the 402 flow in action.

### 1. Check available endpoints and pricing

```bash
curl https://sandbox.agentrails.io/api/x402/pricing
```

```json
{
  "endpoints": [
    { "resource": "/api/x402/protected/analysis", "amountUsdc": 0.01 },
    { "resource": "/api/x402/protected/data", "amountUsdc": 0.001 }
  ],
  "supportedNetworks": [
    "eip155:5042002", "eip155:84532", "eip155:11155111",
    "eip155:8453", "eip155:1"
  ],
  "payTo": "0x6255d8dd3f84ec460fc8b07db58ab06384a2f487"
}
```

### 2. See a 402 response

```bash
curl -i https://sandbox.agentrails.io/api/x402/protected/analysis
# → 402 Payment Required
# → PAYMENT-REQUIRED: <base64-encoded payment requirements>
```

### 3. Point your agent at the sandbox

```python
wallet = X402Wallet(
    private_key=os.environ["WALLET_PRIVATE_KEY"],
    network="eip155:84532",  # Base Sepolia testnet (CAIP-2 format)
    budget_usd=1.00
)

tool = X402PaymentTool(wallet=wallet)

# The tool handles the 402 → sign → retry flow automatically
result = tool.invoke({
    "url": "https://sandbox.agentrails.io/api/x402/protected/analysis"
})
```

### Sandbox Endpoints

| Endpoint | Cost | Description |
|----------|------|-------------|
| `GET /api/x402/protected/analysis` | $0.01 USDC | AI analysis (premium) |
| `GET /api/x402/protected/data` | $0.001 USDC | Data endpoint (micropayment) |
| `GET /api/x402/pricing` | Free | Pricing for all protected endpoints |
| `GET /api/x402/stats` | Free | Payment statistics |

Full API reference: [sandbox.agentrails.io/swagger](https://sandbox.agentrails.io/swagger)

## Features

### Automatic Payment Handling
The `X402PaymentTool` automatically detects 402 responses and handles payment negotiation:

```python
tool = X402PaymentTool(
    wallet=wallet,
    auto_pay=True,  # Automatically pay when within budget
    timeout=30.0,   # Request timeout in seconds
)
```

### Budget Control
Set spending limits at the wallet level:

```python
wallet = X402Wallet(
    private_key=key,
    network="eip155:8453",
    budget_usd=5.00  # Agent can't spend more than $5
)

# Check remaining budget
print(f"Remaining: ${wallet.remaining_usd}")

# Check if can afford a specific amount
if wallet.can_afford(0.01):
    print("Can afford $0.01 request")
```

### Per-Request Price Limits
Limit how much an agent can pay for a single request:

```python
# In the tool input
result = tool.invoke({
    "url": "https://sandbox.agentrails.io/api/x402/protected/analysis",
    "max_price_usd": 0.05  # Won't pay more than $0.05 for this request
})
```

### Payment History
Track all payments made by the wallet:

```python
for payment in wallet.payments:
    print(f"{payment.resource_url}: ${payment.amount_usd}")

# Get summary
summary = wallet.get_payment_summary()
print(f"Total spent: ${summary['spent_usd']}")
print(f"Payments made: {summary['payment_count']}")
```

### Multi-Network Support
Supports multiple EVM networks using [CAIP-2](https://github.com/ChainAgnostic/CAIPs/blob/main/CAIPs/caip-2.md) identifiers:

```python
# Base (recommended - low fees)
wallet = X402Wallet(private_key=key, network="eip155:8453")

# Ethereum
wallet = X402Wallet(private_key=key, network="eip155:1")

# Testnets
wallet = X402Wallet(private_key=key, network="eip155:84532")   # Base Sepolia
wallet = X402Wallet(private_key=key, network="eip155:5042002") # Arc testnet
```

> Legacy network names (`base-mainnet`, `base-sepolia`, etc.) are still accepted for backwards compatibility.

## API Reference

### X402Wallet

```python
X402Wallet(
    private_key: str,      # Hex-encoded private key
    network: str,          # CAIP-2 network ID (e.g., "eip155:8453")
    budget_usd: float,     # Maximum USD to spend
)
```

**Properties:**
- `address` - Wallet address
- `spent_usd` - Total USD spent
- `remaining_usd` - Remaining budget
- `payments` - List of PaymentRecord objects

**Methods:**
- `can_afford(amount_usd)` - Check if budget allows payment
- `sign_payment(to, amount, valid_before)` - Sign EIP-3009 authorization
- `get_payment_summary()` - Get spending summary dict
- `reset_budget(new_budget)` - Reset budget and clear history

### X402PaymentTool

```python
X402PaymentTool(
    wallet: X402Wallet,    # Wallet for payments
    auto_pay: bool = True, # Auto-pay when within budget
    timeout: float = 30.0, # HTTP timeout
)
```

**Tool Input Schema:**
```python
{
    "url": str,                    # Required: URL to request
    "method": str = "GET",         # HTTP method
    "body": str | None,            # Request body
    "headers": dict | None,        # Additional headers
    "max_price_usd": float | None, # Per-request price limit
}
```

## Networks

V2 uses [CAIP-2](https://github.com/ChainAgnostic/CAIPs/blob/main/CAIPs/caip-2.md) network identifiers:

| Network ID (CAIP-2) | Chain ID | Environment | Legacy Alias |
|---------------------|----------|-------------|-------------|
| `eip155:8453` | 8453 | Production | `base-mainnet` |
| `eip155:84532` | 84532 | Testnet | `base-sepolia` |
| `eip155:1` | 1 | Production | `ethereum-mainnet` |
| `eip155:11155111` | 11155111 | Testnet | `ethereum-sepolia` |
| `eip155:5042002` | 5042002 | Testnet | `arc-testnet` |

## Security Considerations

1. **Never commit private keys** - Use environment variables or secret managers
2. **Set appropriate budgets** - Limit what agents can spend
3. **Use testnets first** - Test with `eip155:84532` (Base Sepolia) before mainnet
4. **Monitor spending** - Check `wallet.get_payment_summary()` regularly

## Examples

See the [examples/](examples/) directory:
- `basic_agent.py` - Simple ReAct agent with payment capability
- `multi_api.py` - Agent accessing multiple paid APIs

## How It Differs From API Keys

| API Keys | x402 |
|----------|------|
| 1 key per service | 1 wallet for all services |
| Monthly subscriptions | Pay per request |
| Human signup required | Zero onboarding |
| Credential rotation | No credentials to leak |
| Service-level limits | Agent-level budgets |

## Related Packages

- [crewai-x402](https://pypi.org/project/crewai-x402/) - x402 integration for CrewAI

## Resources

- [x402 Protocol Spec](https://x402.org)
- [AgentRails Documentation](https://agentrails.io/docs)
- [AgentRails Swagger (Sandbox)](https://sandbox.agentrails.io/swagger)
- [EIP-3009 Specification](https://eips.ethereum.org/EIPS/eip-3009)
- [LangChain Custom Tools](https://python.langchain.com/docs/modules/tools/custom_tools)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read our contributing guidelines and submit PRs to the [GitHub repository](https://github.com/kmatthewsio/langchain-x402).
