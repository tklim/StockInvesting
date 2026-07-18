import { mutation } from "./_generated/server";

const now = 1_747_716_000_000;

const stocks = [
  {
    ticker: "NVDA",
    companyName: "NVIDIA Corp.",
    exchange: "NasdaqGS",
    sector: "Semiconductors",
    price: 952.89,
    change: 18.1,
    changePercent: 1.94,
    marketCap: "2.34T",
    peRatio: "54.21",
    revenueTtm: "60.92B",
    epsTtm: "17.59",
    dividendYield: "0.03%",
    summary:
      "NVIDIA remains the dominant force in AI infrastructure chips, with strong demand across data centers, gaming, and automotive. Blackwell ramp is on track, driving FY26 growth.",
  },
  {
    ticker: "AAPL",
    companyName: "Apple Inc.",
    exchange: "NasdaqGS",
    sector: "Consumer Electronics",
    price: 216.24,
    change: 2.11,
    changePercent: 0.99,
    marketCap: "3.22T",
    peRatio: "32.18",
    revenueTtm: "385.71B",
    epsTtm: "6.43",
    dividendYield: "0.44%",
    summary:
      "Apple remains a high-quality consumer platform business with resilient services revenue, a massive installed base, and strong capital returns.",
  },
  {
    ticker: "MSFT",
    companyName: "Microsoft Corp.",
    exchange: "NasdaqGS",
    sector: "Software Infrastructure",
    price: 476.91,
    change: 3.84,
    changePercent: 0.81,
    marketCap: "3.54T",
    peRatio: "38.72",
    revenueTtm: "245.12B",
    epsTtm: "11.81",
    dividendYield: "0.62%",
    summary:
      "Microsoft combines durable enterprise software, Azure growth, and broad AI distribution through Copilot and cloud infrastructure.",
  },
  {
    ticker: "TSLA",
    companyName: "Tesla, Inc.",
    exchange: "NasdaqGS",
    sector: "Auto Manufacturers",
    price: 268.73,
    change: 7.42,
    changePercent: 2.84,
    marketCap: "856.42B",
    peRatio: "72.39",
    revenueTtm: "96.77B",
    epsTtm: "3.12",
    dividendYield: "0.00%",
    summary:
      "Tesla is a volatile growth story balancing near-term EV margin pressure against optionality in energy storage, autonomous driving, and robotics.",
  },
  {
    ticker: "AMZN",
    companyName: "Amazon.com Inc.",
    exchange: "NasdaqGS",
    sector: "Internet Retail",
    price: 228.41,
    change: 2.96,
    changePercent: 1.31,
    marketCap: "2.39T",
    peRatio: "41.06",
    revenueTtm: "620.13B",
    epsTtm: "5.28",
    dividendYield: "0.00%",
    summary:
      "Amazon pairs a massive retail logistics network with AWS, advertising, and marketplace monetization. The current thesis centers on margin expansion and AWS AI demand.",
  },
];

const newsByTicker: Record<string, Array<{ headline: string; source: string }>> = {
  NVDA: [
    {
      headline:
        "NVIDIA announces new Blackwell platform for next-gen AI data centers",
      source: "NVIDIA Investor Relations",
    },
    {
      headline:
        "Morgan Stanley raises NVIDIA price target to $1,100 on strong AI demand",
      source: "Morgan Stanley Research",
    },
  ],
  AAPL: [
    {
      headline: "Apple services revenue reaches new high as device demand stabilizes",
      source: "Company filings",
    },
    {
      headline: "Analysts watch AI features as next iPhone cycle approaches",
      source: "MarketWatch",
    },
  ],
  MSFT: [
    {
      headline: "Azure growth remains resilient as AI workloads scale",
      source: "Microsoft Investor Relations",
    },
    {
      headline: "Copilot adoption expands across enterprise customers",
      source: "The Information",
    },
  ],
  TSLA: [
    {
      headline: "Tesla energy storage deployments continue to accelerate",
      source: "Company update",
    },
    {
      headline: "Investors weigh robotaxi timeline against EV pricing pressure",
      source: "Reuters",
    },
  ],
  AMZN: [
    {
      headline: "AWS demand improves as enterprise AI workloads ramp",
      source: "Amazon Investor Relations",
    },
    {
      headline: "Advertising revenue remains one of Amazon's fastest growers",
      source: "Bloomberg",
    },
  ],
};

const noteByTicker: Record<string, { title: string; body: string; tag: string }> = {
  NVDA: {
    title: "Data center demand remains robust",
    body:
      "Hyperscalers continue to guide strong capex. Blackwell orders exceed expectations.",
    tag: "Bull Case",
  },
  AAPL: {
    title: "Installed base remains the moat",
    body: "Services monetization and ecosystem retention support premium margins.",
    tag: "Bull Case",
  },
  MSFT: {
    title: "Enterprise distribution advantage",
    body:
      "Microsoft can bundle AI capabilities through productivity and cloud relationships.",
    tag: "Bull Case",
  },
  TSLA: {
    title: "Energy segment deserves more attention",
    body: "Storage gross profit can become more material if deployments keep compounding.",
    tag: "Bull Case",
  },
  AMZN: {
    title: "Retail margin runway",
    body: "Regionalization and fulfillment efficiency can keep improving operating income.",
    tag: "Bull Case",
  },
};

const researchByTicker: Record<
  string,
  Array<{
    kind: "strength" | "thesis" | "risk";
    title: string;
    body: string;
    status?: "complete" | "open";
  }>
> = {
  NVDA: [
    {
      kind: "strength",
      title: "Strong data center growth",
      body: "Demand for Hopper and Blackwell chips remains robust.",
    },
    {
      kind: "risk",
      title: "U.S. export restrictions impacting China revenue",
      body: "Policy changes could constrain a meaningful growth channel.",
    },
    {
      kind: "thesis",
      title: "AI infrastructure growth drives multi-year demand",
      body: "Long-term data center demand remains the core thesis.",
      status: "complete",
    },
  ],
  AAPL: [
    {
      kind: "strength",
      title: "Services compounder",
      body: "High-margin recurring revenue cushions hardware cycles.",
    },
    {
      kind: "risk",
      title: "iPhone replacement cycles remain muted",
      body: "Upgrade demand may need stronger AI features to reaccelerate.",
    },
    {
      kind: "thesis",
      title: "Services growth offsets slower hardware cycles",
      body: "Installed base monetization continues to improve business quality.",
      status: "complete",
    },
  ],
  MSFT: [
    {
      kind: "strength",
      title: "AI distribution at scale",
      body: "Copilot can reach users through existing enterprise workflows.",
    },
    {
      kind: "risk",
      title: "AI capex pressure",
      body: "Heavy infrastructure spending could pressure free cash flow.",
    },
    {
      kind: "thesis",
      title: "Azure and Copilot create a durable AI platform",
      body: "Distribution and infrastructure are both strategic advantages.",
      status: "complete",
    },
  ],
  TSLA: [
    {
      kind: "strength",
      title: "Energy storage growth",
      body: "Megapack demand creates a second growth engine beyond vehicles.",
    },
    {
      kind: "risk",
      title: "EV margins remain under pressure",
      body: "Competitive pricing could continue to compress automotive profitability.",
    },
    {
      kind: "thesis",
      title: "Energy and autonomy expand Tesla beyond autos",
      body: "Long-term upside depends on more than vehicle unit growth.",
      status: "open",
    },
  ],
  AMZN: [
    {
      kind: "strength",
      title: "Advertising flywheel",
      body: "Retail intent data supports high-margin ad growth.",
    },
    {
      kind: "risk",
      title: "Cloud competition",
      body: "Azure and Google Cloud are aggressively competing for AI workloads.",
    },
    {
      kind: "thesis",
      title: "Margin expansion continues across retail and ads",
      body: "Operating leverage can drive earnings growth faster than revenue.",
      status: "complete",
    },
  ],
};

export const demoData = mutation({
  args: {},
  handler: async (ctx) => {
    const insertedIds = [];

    for (const stock of stocks) {
      const existing = await ctx.db
        .query("stocks")
        .withIndex("by_ticker", (q) => q.eq("ticker", stock.ticker))
        .unique();

      if (existing) {
        insertedIds.push(existing._id);
        continue;
      }

      const stockId = await ctx.db.insert("stocks", {
        ...stock,
        updatedAt: now,
      });
      insertedIds.push(stockId);

      await Promise.all([
        ...(newsByTicker[stock.ticker] ?? []).map((item, index) =>
          ctx.db.insert("news", {
            ticker: stock.ticker,
            headline: item.headline,
            source: item.source,
            publishedAt: now - index * 86_400_000,
          })
        ),
        ctx.db.insert("notes", {
          ticker: stock.ticker,
          ...noteByTicker[stock.ticker],
          createdAt: now - 172_800_000,
        }),
        ...(researchByTicker[stock.ticker] ?? []).map((item) =>
          ctx.db.insert("researchItems", {
            ticker: stock.ticker,
            ...item,
            createdAt: now,
          })
        ),
      ]);
    }

    return insertedIds;
  },
});
