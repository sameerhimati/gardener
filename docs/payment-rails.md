# Agent Payment Rails — Comparison Guide
_June 2026 · Harness Hackathon research · verified via live docs_
_**Status for this project: CUT** — unscored by judges. Kept for the post-hackathon trail._

---

## 1. x402 — Coinbase HTTP 402 Payment Protocol

**What it is.** An open protocol repurposing HTTP 402 for machine-native stablecoin micropayments. Client hits an endpoint → gets `402` with payment terms → signs a USDC payment proof → retries with proof → receives the resource. No accounts, no API keys. Chain-agnostic; Base is primary.

**Current state (June 2026).** Production. 165M+ transactions, ~$50M volume, 480K+ active agents. x402 Foundation maintains the spec; Coinbase ships reference SDKs.

**SDKs.** Python: `pip install "x402[fastapi]"` (v2.12.0, May 2026). JS/TS: `@x402/express`, `@x402/fastify`, `@x402/next`, `@x402/fetch`, `@x402/hono`. Go/Rust community packages.

**Minimal server (FastAPI — charge $0.001/request):**
```python
from fastapi import FastAPI
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import Network
from x402.server import x402ResourceServer

app = FastAPI()
EVM_NETWORK: Network = "eip155:84532"  # Base Sepolia testnet
facilitator = HTTPFacilitatorClient(FacilitatorConfig(url="https://x402.org/facilitator"))
server = x402ResourceServer(facilitator)
server.register(EVM_NETWORK, ExactEvmServerScheme())

routes = {
    "GET /brief": RouteConfig(
        accepts=[PaymentOption(scheme="exact", pay_to="0xYourWallet",
                               price="$0.001", network=EVM_NETWORK)],
        mime_type="application/json",
        description="Cited research brief",
    )
}
app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)

@app.get("/brief")
async def get_brief():
    return {"brief": "..."}
```

**Client/agent paying:**
```python
from x402 import x402Client
client = x402Client()
payload = await client.create_payment_payload(payment_required)
# attach payload to retry request header
```

**Demo safety:** Yes — `eip155:84532` (Base Sepolia) + public facilitator + test USDC from Coinbase faucets. ~30–60 min to a working paying agent.

---

## 2. MPP — Machine Payments Protocol (Stripe + Tempo)

Open standard for machine-to-machine payments, also on HTTP 402, co-authored by Stripe and Tempo, launched March 18, 2026. Supports stablecoins (Tempo), Stripe card charges, Bitcoin Lightning. Submitted to IETF. Early production: 50+ services incl. OpenAI, Anthropic, Dune.

SDKs: TS `mppx` (wevm), Python `pympp`, Rust `mpp-rs`, Go, Ruby. Cloudflare Workers integration documented.

Testnet: testnet pathUSD at `0x20c0000000000000000000000000000000000000` on Tempo test network; live demo at `mpp.stellar.buzz`. Tooling less polished than x402/Base Sepolia. Setup 1–3 hours; `pympp` thinner docs.

**Skip for the hackathon** — no demo-quality upside over x402, more dependencies.

---

## 3. CDP — Coinbase Developer Platform (AgentKit + Agentic Wallets)

CDP is infrastructure, not a protocol — the wallet layer that funds an agent's x402 client. **AgentKit**: framework-agnostic toolkit giving an agent its own crypto wallet with onchain actions (Python + JS). **Agentic Wallets** (Feb 11, 2026): production MPC wallets, per-transaction limits, gasless Base transactions, native x402 support.

```python
pip install coinbase-agentkit

from coinbase_agentkit import AgentKit
kit = AgentKit()   # defaults to base-sepolia

# or explicit:
from coinbase_agentkit import CdpWalletProvider, CdpWalletProviderConfig
wallet = CdpWalletProvider(CdpWalletProviderConfig(
    api_key_name="YOUR_KEY",
    api_key_private="YOUR_SECRET",
    network_id="base-sepolia"   # testnet default
))
```

Free CDP API key at portal.cdp.coinbase.com. 20–40 min to a funded testnet wallet. Combine with x402 for the full demo.

---

## 4. agentic.market

Coinbase-launched (April 2026) public marketplace directory of x402-paywalled services — "app store for paid agent APIs." 1,175+ services (inference, data, search, media, trading) with live USDC pricing. Built entirely on x402. Discovery via REST (`GET /v1/services`, `/v1/services/search?q=...`) or MCP (`npx skills add coinbase/agentic-wallet-skills`). **Self-indexing**: automatically discovers new x402 services by monitoring on-chain payments — run x402 middleware and you're listed for free; your endpoint can be testnet.

---

## Recommendation

**x402 + CDP AgentKit** together: AgentKit creates the agent's wallet, x402 middleware gates your endpoint, the same wallet pays for upstream data. Both Base Sepolia testnet-safe, ~60–90 min total, most visually legible demo (show the 402 response, the signed payment, the balance decrement). agentic.market listing comes free.

**Judge weighting:** Payment rails are table-stakes decoration — they appear in zero scored criteria at this hackathon. A wired x402 paywall signals sophistication but moves your score by one rank at most. **Cap at ≤10% of build time or cut entirely.**

---

## Sources (fetched June 12, 2026)

- [x402 Overview — Coinbase Developer Docs](https://docs.cdp.coinbase.com/x402/welcome)
- [Introducing x402 — Coinbase Blog](https://www.coinbase.com/developer-platform/discover/launches/x402)
- [x402 GitHub (coinbase/x402)](https://github.com/coinbase/x402)
- [x402 Quickstart for Sellers](https://docs.x402.org/getting-started/quickstart-for-sellers)
- [x402 PyPI (v2.12.0)](https://pypi.org/project/x402/)
- [Introducing MPP — Stripe Blog](https://stripe.com/blog/machine-payments-protocol)
- [MPP Quickstart](https://mpp.dev/quickstart)
- [MPP — Cloudflare Agents Docs](https://developers.cloudflare.com/agents/agentic-payments/mpp/)
- [mppx TypeScript SDK](https://github.com/wevm/mppx)
- [AgentKit Overview — Coinbase Developer Docs](https://docs.cdp.coinbase.com/agent-kit/welcome)
- [AgentKit Python Docs](https://coinbase.github.io/agentkit/coinbase-agentkit/python/index.html)
- [AgentKit PyPI](https://pypi.org/project/coinbase-agentkit/)
- [Agentic Wallets Launch](https://www.coinbase.com/developer-platform/discover/launches/agentic-wallets)
- [Agentic.market](https://agentic.market/)
- [AI Agent Payment Protocols 2026 — NomadLab](https://nomadlab.cc/blog/2026/05/ai-agent-payment-protocols-2026-x402-mpp-agentcore-visa-mastercard)
- [What is MPP — GetBlock.io](https://getblock.io/blog/what-is-a-machine-payments-protocol-mpp/)
- [MPP — Stripe Documentation](https://docs.stripe.com/payments/machine/mpp)
