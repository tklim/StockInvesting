export type Stock = {
  ticker: string;
  companyName: string;
  exchange: string;
  sector: string;
  logoUrl?: string;
  price: number;
  change: number;
  changePercent: number;
  updatedAt?: number;
  marketCap: string;
  peRatio: string;
  revenueTtm: string;
  epsTtm: string;
  dividendYield: string;
  summary: string;
  chartPoints?: number[];
};

export type NewsItem = {
  headline: string;
  source: string;
  url?: string;
  publishedAt: number;
};

export type NoteItem = {
  _id?: string;
  title: string;
  body: string;
  tag: string;
  createdAt: number;
};

export type ResearchItem = {
  kind: "brief" | "strength" | "thesis" | "risk";
  title: string;
  body: string;
  status?: "complete" | "open";
};

export type ResearchBundle = {
  stock: Stock;
  news: NewsItem[];
  notes: NoteItem[];
  researchItems: ResearchItem[];
  financialReport?: {
    source: string;
    numericVersion?: number;
    sourceUrl?: string;
    filedAt?: string;
    accessionNumber?: string;
    validationStatus?: "verified" | "partial" | "fallback";
    warnings?: string[];
    qualityScore?: number;
    currency: string;
    fiscalYearEnd: string;
    latestQuarter: string;
    profitMargin: string;
    operatingMarginTtm: string;
    returnOnEquityTtm: string;
    priceToBookRatio: string;
    evToRevenue: string;
    evToEbitda: string;
    beta: string;
    analystTargetPrice: string;
    quarterly: Array<{
      fiscalDateEnding: string;
      derived?: boolean;
      derivation?: string;
      currency?: string;
      normalized?: Partial<Record<
        | "totalRevenue"
        | "grossProfit"
        | "operatingIncome"
        | "netIncome"
        | "dilutedEps"
        | "operatingCashflow"
        | "capitalExpenditures"
        | "freeCashFlow"
        | "totalAssets"
        | "totalLiabilities"
        | "totalShareholderEquity",
        number
      >>;
      filedAt?: string;
      accessionNumber?: string;
      sourceUrl?: string;
      totalRevenue: string;
      grossProfit: string;
      operatingIncome: string;
      netIncome: string;
      dilutedEps: string;
      operatingCashflow: string;
      capitalExpenditures: string;
      freeCashFlow: string;
      totalAssets: string;
      totalLiabilities: string;
      totalShareholderEquity: string;
    }>;
    annual: Array<{
      fiscalDateEnding: string;
      derived?: boolean;
      derivation?: string;
      currency?: string;
      normalized?: Partial<Record<
        | "totalRevenue"
        | "grossProfit"
        | "operatingIncome"
        | "netIncome"
        | "dilutedEps"
        | "operatingCashflow"
        | "capitalExpenditures"
        | "freeCashFlow"
        | "totalAssets"
        | "totalLiabilities"
        | "totalShareholderEquity",
        number
      >>;
      filedAt?: string;
      accessionNumber?: string;
      sourceUrl?: string;
      totalRevenue: string;
      grossProfit: string;
      operatingIncome: string;
      netIncome: string;
      dilutedEps: string;
      operatingCashflow: string;
      capitalExpenditures: string;
      freeCashFlow: string;
      totalAssets: string;
      totalLiabilities: string;
      totalShareholderEquity: string;
    }>;
    updatedAt: number;
  };
  aiReport?: {
    summary: string;
    bullPoints: string[];
    bearPoints: string[];
    thesisPoints: string[];
    watchItems: string[];
    provider: string;
    model: string;
    generatedAt: number;
  };
  investmentThesis?: {
    summary: string;
    thesisPoints: string[];
    watchItems: string[];
    source: string;
    updatedAt: number;
  };
  snapshots?: Array<{
    ticker: string;
    companyName: string;
    exchange: string;
    sector: string;
    price: number;
    change: number;
    changePercent: number;
    marketCap: string;
    peRatio: string;
    revenueTtm: string;
    epsTtm: string;
    dividendYield: string;
    summary: string;
    aiBriefSummary?: string;
    aiBullPoints?: string[];
    aiBearPoints?: string[];
    thesisSummary?: string;
    thesisPoints?: string[];
    thesisWatchItems?: string[];
    syncedAt: number;
  }>;
  isSaved: boolean;
};

export type StockSummary = Pick<
  Stock,
  "ticker" | "companyName" | "exchange" | "sector" | "price" | "changePercent"
>;

const now = new Date("2025-05-20T20:00:00Z").getTime();

export const chartSeriesByTicker: Record<string, number[]> = {
  NVDA: [
    980, 940, 952, 966, 990, 918, 952, 934, 892, 914, 887, 881, 934, 930, 942,
    925, 930, 935, 905, 884, 862, 903, 916, 887, 836, 820, 862, 845, 818, 856,
    884, 878, 904, 920, 948, 980, 954, 962, 989, 965, 974, 952,
  ],
  AAPL: [
    176, 174, 175, 173, 177, 179, 178, 181, 183, 180, 182, 185, 184, 186, 188,
    187, 189, 191, 190, 192, 194, 193, 195, 197, 196, 198, 201, 199, 202, 204,
    203, 205, 207, 206, 208, 210, 209, 211, 213, 212, 214, 216,
  ],
  MSFT: [
    402, 406, 408, 405, 410, 414, 412, 417, 420, 418, 422, 425, 424, 428, 431,
    429, 433, 436, 432, 438, 441, 439, 443, 447, 445, 449, 452, 450, 454, 457,
    455, 459, 462, 460, 464, 467, 465, 469, 472, 470, 474, 476,
  ],
  TSLA: [
    248, 242, 236, 241, 229, 224, 230, 218, 212, 220, 215, 208, 214, 219, 211,
    205, 198, 204, 197, 190, 196, 203, 199, 207, 214, 221, 216, 224, 232, 228,
    236, 241, 235, 244, 251, 247, 255, 262, 258, 266, 271, 268,
  ],
  AMZN: [
    174, 176, 175, 178, 181, 179, 182, 184, 183, 186, 189, 187, 190, 192, 191,
    194, 197, 195, 198, 201, 199, 202, 205, 203, 206, 209, 207, 210, 212, 211,
    214, 217, 215, 218, 221, 219, 222, 225, 223, 226, 229, 228,
  ],
};

export const researchBundles: Record<string, ResearchBundle> = {
  NVDA: {
    stock: {
      ticker: "NVDA",
      companyName: "NVIDIA Corp.",
      exchange: "NasdaqGS",
      sector: "Semiconductors",
      price: 952.89,
      change: 18.1,
      changePercent: 1.94,
      updatedAt: now,
      marketCap: "2.34T",
      peRatio: "54.21",
      revenueTtm: "60.92B",
      epsTtm: "17.59",
      dividendYield: "0.03%",
      summary:
        "NVIDIA remains the dominant force in AI infrastructure chips, with strong demand across data centers, gaming, and automotive. Blackwell ramp is on track, driving FY26 growth. Key risks include China export restrictions and rising competition from AMD and custom silicon.",
    },
    news: [
      {
        headline:
          "NVIDIA announces new Blackwell platform for next-gen AI data centers",
        source: "NVIDIA Investor Relations",
        publishedAt: now,
      },
      {
        headline:
          "Morgan Stanley raises NVIDIA price target to $1,100 on strong AI demand",
        source: "Morgan Stanley Research",
        publishedAt: now - 86_400_000,
      },
      {
        headline: "NVIDIA GTC key takeaways: Blackwell ramp and ecosystem updates",
        source: "Seeking Alpha",
        publishedAt: now - 172_800_000,
      },
    ],
    notes: [
      {
        title: "Data center demand remains robust",
        body:
          "Hyperscalers continue to guide strong capex. Blackwell orders exceed expectations and reinforce near-term visibility.",
        tag: "Bull Case",
        createdAt: now - 172_800_000,
      },
      {
        title: "Valuation review",
        body:
          "P/E forward around 35x FY26E EPS. Premium vs. market but justified by growth and moat.",
        tag: "Valuation",
        createdAt: now - 259_200_000,
      },
    ],
    researchItems: [
      {
        kind: "strength",
        title: "Strong data center growth",
        body: "Demand for Hopper and Blackwell chips remains robust.",
      },
      {
        kind: "strength",
        title: "Leadership in AI ecosystem",
        body: "CUDA moat and software advantages remain unmatched.",
      },
      {
        kind: "risk",
        title: "U.S. export restrictions impacting China revenue",
        body: "Policy changes could constrain a meaningful growth channel.",
      },
      {
        kind: "risk",
        title: "High valuation leaves little room for execution error",
        body: "Multiple compression could hurt returns even if fundamentals stay solid.",
      },
      {
        kind: "thesis",
        title: "AI infrastructure growth drives multi-year demand",
        body: "Long-term data center demand remains the core thesis.",
        status: "complete",
      },
      {
        kind: "thesis",
        title: "NVIDIA maintains leadership through CUDA ecosystem",
        body: "Software switching costs reinforce the hardware moat.",
        status: "complete",
      },
    ],
    isSaved: false,
  },
  AAPL: {
    stock: {
      ticker: "AAPL",
      companyName: "Apple Inc.",
      exchange: "NasdaqGS",
      sector: "Consumer Electronics",
      price: 216.24,
      change: 2.11,
      changePercent: 0.99,
      updatedAt: now,
      marketCap: "3.22T",
      peRatio: "32.18",
      revenueTtm: "385.71B",
      epsTtm: "6.43",
      dividendYield: "0.44%",
      summary:
        "Apple remains a high-quality consumer platform business with resilient services revenue, a massive installed base, and strong capital returns. The key debate is whether AI-enabled device upgrades can reaccelerate iPhone growth.",
    },
    news: [
      {
        headline: "Apple services revenue reaches new high as device demand stabilizes",
        source: "Company filings",
        publishedAt: now - 42_000_000,
      },
      {
        headline: "Analysts watch AI features as next iPhone cycle approaches",
        source: "MarketWatch",
        publishedAt: now - 128_000_000,
      },
    ],
    notes: [
      {
        title: "Installed base remains the moat",
        body:
          "Services monetization and ecosystem retention continue to support premium margins.",
        tag: "Bull Case",
        createdAt: now - 160_000_000,
      },
      {
        title: "China demand check",
        body:
          "Track regional iPhone share and competitive pressure from domestic premium devices.",
        tag: "Risk",
        createdAt: now - 260_000_000,
      },
    ],
    researchItems: [
      {
        kind: "strength",
        title: "Services compounder",
        body: "High-margin recurring revenue cushions hardware cycles.",
      },
      {
        kind: "strength",
        title: "Capital returns",
        body: "Buybacks remain a major driver of per-share value creation.",
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
      {
        kind: "thesis",
        title: "AI features can drive a stronger upgrade cycle",
        body: "Evidence is still early and should be monitored.",
        status: "open",
      },
    ],
    isSaved: false,
  },
  MSFT: {
    stock: {
      ticker: "MSFT",
      companyName: "Microsoft Corp.",
      exchange: "NasdaqGS",
      sector: "Software Infrastructure",
      price: 476.91,
      change: 3.84,
      changePercent: 0.81,
      updatedAt: now,
      marketCap: "3.54T",
      peRatio: "38.72",
      revenueTtm: "245.12B",
      epsTtm: "11.81",
      dividendYield: "0.62%",
      summary:
        "Microsoft combines durable enterprise software, Azure growth, and broad AI distribution through Copilot and cloud infrastructure. Investors are watching AI monetization, cloud margins, and capex intensity.",
    },
    news: [
      {
        headline: "Azure growth remains resilient as AI workloads scale",
        source: "Microsoft Investor Relations",
        publishedAt: now - 64_000_000,
      },
      {
        headline: "Copilot adoption expands across enterprise customers",
        source: "The Information",
        publishedAt: now - 154_000_000,
      },
    ],
    notes: [
      {
        title: "Enterprise distribution advantage",
        body:
          "Microsoft can bundle AI capabilities through existing productivity and cloud relationships.",
        tag: "Bull Case",
        createdAt: now - 144_000_000,
      },
      {
        title: "Capex watch",
        body: "AI infrastructure spending needs to translate into durable revenue growth.",
        tag: "Valuation",
        createdAt: now - 310_000_000,
      },
    ],
    researchItems: [
      {
        kind: "strength",
        title: "Cloud and productivity flywheel",
        body: "Azure, Office, and security products reinforce each other.",
      },
      {
        kind: "strength",
        title: "AI distribution at scale",
        body: "Copilot can reach users through existing enterprise workflows.",
      },
      {
        kind: "risk",
        title: "AI capex pressure",
        body: "Heavy infrastructure spending could pressure free cash flow if monetization lags.",
      },
      {
        kind: "thesis",
        title: "Azure and Copilot create a durable AI platform",
        body: "Distribution and infrastructure are both strategic advantages.",
        status: "complete",
      },
      {
        kind: "thesis",
        title: "Margins remain resilient through AI investment cycle",
        body: "Needs continued operating leverage outside AI capex.",
        status: "open",
      },
    ],
    isSaved: false,
  },
  TSLA: {
    stock: {
      ticker: "TSLA",
      companyName: "Tesla, Inc.",
      exchange: "NasdaqGS",
      sector: "Auto Manufacturers",
      price: 268.73,
      change: 7.42,
      changePercent: 2.84,
      updatedAt: now,
      marketCap: "856.42B",
      peRatio: "72.39",
      revenueTtm: "96.77B",
      epsTtm: "3.12",
      dividendYield: "0.00%",
      summary:
        "Tesla is a volatile growth story balancing near-term EV margin pressure against optionality in energy storage, autonomous driving, and robotics. Execution risk is high, but upside narratives remain powerful.",
    },
    news: [
      {
        headline: "Tesla energy storage deployments continue to accelerate",
        source: "Company update",
        publishedAt: now - 52_000_000,
      },
      {
        headline: "Investors weigh robotaxi timeline against EV pricing pressure",
        source: "Reuters",
        publishedAt: now - 118_000_000,
      },
    ],
    notes: [
      {
        title: "Energy segment deserves more attention",
        body: "Storage gross profit can become more material if deployments keep compounding.",
        tag: "Bull Case",
        createdAt: now - 120_000_000,
      },
      {
        title: "Auto margin sensitivity",
        body: "Price cuts and mix shifts can move earnings power quickly.",
        tag: "Risk",
        createdAt: now - 244_000_000,
      },
    ],
    researchItems: [
      {
        kind: "strength",
        title: "Energy storage growth",
        body: "Megapack demand creates a second growth engine beyond vehicles.",
      },
      {
        kind: "strength",
        title: "Autonomy optionality",
        body: "FSD and robotaxi economics remain a major upside scenario.",
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
      {
        kind: "thesis",
        title: "Core EV demand stabilizes without heavy price cuts",
        body: "Needs clearer evidence in delivery and margin trends.",
        status: "open",
      },
    ],
    isSaved: false,
  },
  AMZN: {
    stock: {
      ticker: "AMZN",
      companyName: "Amazon.com Inc.",
      exchange: "NasdaqGS",
      sector: "Internet Retail",
      price: 228.41,
      change: 2.96,
      changePercent: 1.31,
      updatedAt: now,
      marketCap: "2.39T",
      peRatio: "41.06",
      revenueTtm: "620.13B",
      epsTtm: "5.28",
      dividendYield: "0.00%",
      summary:
        "Amazon pairs a massive retail logistics network with AWS, advertising, and marketplace monetization. The current thesis centers on margin expansion, AWS AI demand, and continued advertising growth.",
    },
    news: [
      {
        headline: "AWS demand improves as enterprise AI workloads ramp",
        source: "Amazon Investor Relations",
        publishedAt: now - 33_000_000,
      },
      {
        headline: "Advertising revenue remains one of Amazon's fastest growers",
        source: "Bloomberg",
        publishedAt: now - 166_000_000,
      },
    ],
    notes: [
      {
        title: "Retail margin runway",
        body:
          "Regionalization and fulfillment efficiency can keep improving operating income.",
        tag: "Bull Case",
        createdAt: now - 116_000_000,
      },
      {
        title: "AWS competition",
        body: "Track cloud share against Microsoft and Google as AI workloads grow.",
        tag: "Risk",
        createdAt: now - 288_000_000,
      },
    ],
    researchItems: [
      {
        kind: "strength",
        title: "AWS AI demand",
        body: "Cloud infrastructure remains a major profit pool.",
      },
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
      {
        kind: "thesis",
        title: "AWS reaccelerates through AI workload demand",
        body: "Needs sustained cloud growth evidence.",
        status: "open",
      },
    ],
    isSaved: false,
  },
};

export const demoBundle = researchBundles.NVDA;

export const searchableStocks: StockSummary[] = Object.values(researchBundles).map(
  ({ stock }) => ({
    ticker: stock.ticker,
    companyName: stock.companyName,
    exchange: stock.exchange,
    sector: stock.sector,
    price: stock.price,
    changePercent: stock.changePercent,
  })
);
