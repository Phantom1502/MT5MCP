import { QuantAnalyzer } from '../lib/quant_analyzer.js';

/**
 * Market Analysis Workflow - DISTRIBUTED MICRO-AGENT VERSION
 * 
 * Design Philosophy:
 * - Distributed Tasks: Each sub-task is assigned to the most appropriate model to optimize RPM and Quality.
 * - Resource Allocation:
 *   - Lite Models: Data fetching, basic filtering, raw calculations.
 *   - Flash Models: Trend analysis, pattern recognition, sentiment scoring.
 *   - Pro/Gemma-4 Models: Final strategic synthesis, cross-verification, risk management.
 */

export default async function (args) {
  const { assets = ['XAUUSDc', 'BTCUSDc'] } = args;

  // --- Model Configuration ---
  const MODELS = {
    LITE: 'google/gemini-3.5-flash-lite',
    FLASH: 'google/gemini-3.5-flash',
    STRATEGIST: 'google/gemma-4-31b-it'
  };

  // ==========================================================================
  // PHASE 1: GLOBAL CONTEXT (Daily Bias) - Distributed
  // ==========================================================================
  const globalContext = await (async () => {
    const rawData = await parallel([
      async () => await agent(`Fetch D1 candles for ${assets.join(', ')} using get_symbol_candles. Return only raw data.`, { provider: 'google', model: MODELS.LITE, label: 'D1 Fetch' }),
      async () => await agent(`Fetch DXY price using get_external_price. Return raw price and change%.`, { provider: 'google', model: MODELS.LITE, label: 'DXY Fetch' }),
      async () => await agent(`Fetch USD macro news using get_market_news and web_search. Filter for High/Medium impact.`, { provider: 'google', model: MODELS.LITE, label: 'News Fetch' })
    ]);

    return await agent(`
      Analyze the following raw data to establish a "Daily Bias" (BULLISH, BEARISH, or NEUTRAL) for each asset: ${assets.join(', ')}.
      Data: ${JSON.stringify(rawData)}
      Focus on the alignment between D1 trend, DXY strength, and Macro sentiment.
    `, { provider: 'google', model: MODELS.FLASH, label: 'Bias Determination' });
  })();

  // ==========================================================================
  // PHASE 2: HTF ANALYSIS (H1 Map) - Distributed
  // ==========================================================================
  const htfAnalysis = await (async () => {
    const h1Data = await agent(`Fetch H1 candles for ${assets.join(', ')} using get_symbol_candles (window=100). Return raw data.`, { provider: 'google', model: MODELS.LITE, label: 'H1 Fetch' });

    return await agent(`
      As an HTF Analyst, use the following H1 data and Global Bias: ${globalContext}.
      Data: ${h1Data}
      Tasks:
      1. Identify Market Structure (Higher Highs/Lower Lows).
      2. Locate key Supply/Demand zones (Value Areas).
      3. Confirm trend via SMA50/200.
      Return the latest levels (Value Areas) where price is likely to reject.
    `, { provider: 'google', model: MODELS.FLASH, label: 'H1 Analysis' });
  })();

  // ==========================================================================
  // PHASE 3: LTF EXECUTION (M5 Trigger) - Distributed
  // ==========================================================================
  const ltfExecution = await (async () => {
    const m5Data = await agent(`Fetch M5 candles for ${assets.join(', ')} using get_symbol_candles (window=50). Return raw data.`, { provider: 'google', model: MODELS.LITE, label: 'M5 Fetch' });

    return await agent(`
      As an LTF Executioner, use the H1 Value Areas: ${htfAnalysis} and M5 data: ${m5Data}.
      Tasks:
      1. Check if price is inside an H1 Value Area.
      2. Evaluate M5 triggers: RSI (>70 or <30), Bollinger Bands, and Price Action.
      3. Active TP Management: Check if current prices suggest harvesting profits for existing BUY or SELL groups via ask_for_tp.
      4. New Entry: If setup aligns with Daily Bias, invoke ask_for_open.
      
      Return a detailed execution log: actions taken, tool results, and M5 notes.
    `, { provider: 'google', model: MODELS.FLASH, label: 'M5 Execution' });
  })();

  // ==========================================================================
  // PHASE 4: FINAL STRATEGIC SYNTHESIS (The Master Strategist)
  // ==========================================================================
  const finalStrategy = await agent(`
    You are the MasterStrategist (Gemma-4). Synthesize the distributed analysis into a professional M5 Trading Plan.
    
    INPUTS:
    - Global Bias: ${globalContext}
    - HTF Map (H1): ${htfAnalysis}
    - LTF Execution (M5): ${ltfExecution}
    
    Your Task:
    1. **Cross-Verification:** Ensure M5 triggers align with H1 structure and Daily bias.
    2. **Conflict Detection:** Highlight any divergence.
    3. **Confidence Score:** Provide a score (0-100%) based on the alignment of all 3 sources.
    4. **Execution Plan:** Professional table with Asset | Bias | Entry Zone | SL | TP | R:R.
    5. **Log Summary:** Confirm which tool calls (open/tp) were performed.
    
    Format in professional Markdown.
  `, { provider: 'google', model: MODELS.STRATEGIST, label: 'Final Synthesis' });

  return {
    assets,
    globalContext,
    htfAnalysis,
    ltfExecution,
    strategy: finalStrategy
  };
}
