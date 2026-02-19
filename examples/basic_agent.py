"""
Basic example: LangChain agent with x402 payment capability.

This example shows how to create an agent that can access paid APIs
using the x402 protocol. The agent automatically handles payment
negotiation when it encounters a 402 response.

Prerequisites:
    pip install langchain-x402 langchain-openai

    export WALLET_PRIVATE_KEY="your-private-key"
    export OPENAI_API_KEY="your-openai-key"

Usage:
    python basic_agent.py
"""

import os

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from langchain_x402 import X402Wallet, X402PaymentTool


def main():
    # Initialize wallet with USDC budget
    wallet = X402Wallet(
        private_key=os.environ["WALLET_PRIVATE_KEY"],
        network="eip155:8453",  # Use "eip155:84532" for Base Sepolia testnet
        budget_usd=5.00,  # Maximum $5 spend limit
    )

    print(f"Wallet initialized: {wallet.address}")
    print(f"Budget: ${wallet.budget_usd:.2f} USDC")

    # Create the x402 payment tool
    x402_tool = X402PaymentTool(
        wallet=wallet,
        auto_pay=True,  # Automatically pay when within budget
    )

    # Initialize the LLM
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Create a simple ReAct agent
    template = """You are a helpful assistant that can access paid APIs.

You have access to the following tools:
{tools}

Tool names: {tool_names}

When you need data from a paid API, use the x402_request tool.
The tool will automatically handle payment if the price is within your budget.

Question: {input}

{agent_scratchpad}"""

    prompt = PromptTemplate.from_template(template)

    agent = create_react_agent(llm, [x402_tool], prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=[x402_tool],
        verbose=True,
        handle_parsing_errors=True,
    )

    # Example: Access a paid API endpoint
    result = agent_executor.invoke({
        "input": "Get the premium market analysis from https://api.agentrails.io/api/x402/protected/analysis"
    })

    print("\n" + "=" * 50)
    print("Result:", result["output"])
    print("=" * 50)

    # Print payment summary
    summary = wallet.get_payment_summary()
    print(f"\nPayment Summary:")
    print(f"  Total spent: ${summary['spent_usd']:.4f}")
    print(f"  Remaining: ${summary['remaining_usd']:.4f}")
    print(f"  Payments made: {summary['payment_count']}")


if __name__ == "__main__":
    main()
