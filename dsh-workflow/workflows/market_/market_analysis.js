import { QuantAnalyzer } from '../lib/quant_analyzer.js';

/**
 * Market Analysis Workflow - TOP-DOWN M5 TRADING VERSION
 * 
 * Hierarchy:
 * 1. Global Context: Daily TF + Hybrid News + DXY Strength -> Establish Daily Bias.
 * 2. HTF Analysis: H1 Timeframe -> Identify Value Areas & Market Structure.
 * 3. LTF Execution: M5 Timeframe -> Find Precise Entry Triggers.
 * 4. Final Synthesis: Consolidate into a Scalping Strategy.
 */

export default async function (args) {
  const { assets = ['XAUUSDc', 'BTCUSDc'] } = args;

  // ==========================================================================
  // STEP 1: GLOBAL CONTEXT (Daily Bias)
  // ==========================================================================
  const globalContext = await agent(`
    You are the GlobalStrategist. Your goal is to establish the Daily Bias.
    
    Tasks:
    1. Fetch Daily (D1) candles for ${assets.join(', ')} using get_symbol_candles.
    2. Fetch current USD strength using get_external_price for 'DXY'.
    3. Gather latest macro news using get_market_news (Internal) and web_search (External).
    
    Analysis:
    - Compare D1 trend with DXY strength and Macro sentiment.
    - Determine the a a "Daily Bias": BULLISH, BEARISH, or NEUTRAL.
    
    Return a concise summary of the Daily Bias for each asset.
  `, { label: 'Global Context', phase: 'Daily-Bias' });

  // ==========================================================================
  // STEP 2: HTF ANALYSIS (H1 - The Map)
  // ==========================================================================
  const htfAnalysis = await agent(`
    You are the HTFAnalyst. Using the Global Bias:
    ${globalContext}
    
    Tasks:
    1. Fetch H1 candles for ${assets.join(', ')} using get_symbol_candles.
    2. Use QuantAnalyzer logic to:
       - Identify the H1 Market Structure (Higher Highs/Lower Lows).
       - Locate key Support and Resistance zones (Supply/Demand).
       - Check SMA50/200 for mid-term trend confirmation.
    
    Return the "Value Areas" where a trade becomes high-probability.
  `, { label: 'HTF Analysis', phase: 'H1-Map' });

  // ==========================================================================
  // STEP 3: LTF EXECUTION (M5 - The Trigger)
  // ==========================================================================
  const ltfExecution = await agent(`
    You are the LTFExecutioner. Using the HTF Value Areas:
    ${htfAnalysis}
    
    Tasks:
    1. Fetch M5 candles for ${assets.join(', ')} using get_//symbol_candles.
    2. Analyze the current M5 price action:
       - Is the price currently inside a Value Area identified in H1?
       - Check RSI (overbought/oversold) and Bollinger Band positions.
       - Look for reversal or continuation patterns (Price Action).
    
    Return the precise Entry Trigger, Stop Loss, and Take Profit.
  `, { label: 'LTF Execution', phase: 'M5-Trigger' });

  // ==========================================================================
  // STEP 4: FINAL STRATEGY SYNTHESIS
  // ==========================================================================
  const finalStrategy = await agent(`
    You are the MasterStrategist. Synthesize the Top-Down analysis into a professional M5 Trading Plan.
    
    ### 1. GLOBAL BIAS (Daily + News + DXY):
    ${globalContext}
    
    ### 2. HTF STRUCTURE (H1):
    ${htfAnalysis}
    
    ### 3. LTF TRIGGER (M5):
    ${ltfExecution}
    
    Your Task:
    1. **Alignment Check:** Ensure the M5 trigger aligns with the H1 structure and Daily bias.
    2. **Confidence Score:** Provide a score (0-100%) based on the alignment of the 3 layers.
    3. **Execution Plan:** Provide a crystal-clear table with:
       - Asset | Bias | Entry Zone | Stop Loss | Take Profit | Risk/Reward Ratio.
    4. **Alerts:** Define a "No Trade" condition (e.g., if price breaks the H1 support).
    
    Format the output in professional Markdown.
  `, { label: 'Final Synthesis', phase: 'Reporting' });

  return {
    assets,
    globalContext,
    htfAnalysis,
    ltfExecution,
    strategy: finalStrategy
  };
}
