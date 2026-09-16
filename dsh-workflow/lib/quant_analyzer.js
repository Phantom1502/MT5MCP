/**
 * QuantAnalyzer - Technical Analysis Library for MT5 Data
 * This library provides pure mathematical functions to analyze OHLCV data.
 */

export const QuantAnalyzer = {
  /**
   * Parses raw MT5 candle data into an array of closing prices.
   * MT5 data is assumed to be in ascending time order (newest last).
   */
  parseClosePrices(candles) {
    if (!Array.isArray(candles)) return [];
    return candles.map(c => c.close);
  },

  /**
   * Simple Moving Average (SMA)
   */
  calcSMA(prices, window) {
    if (prices.length < window) return null;
    const slice = prices.slice(-window);
    const sum = slice.reduce((a, b) => a + b, 0);
    return sum / window;
  },

  /**
   * Exponential Moving Average (EMA)
   */
  calcEMA(prices, window) {
    if (prices.length < window) return null;
    const k = 2 / (window + 1);
    let ema = prices.slice(0, window).reduce((a, b) => a + b, 0) / window;
    
    for (let i = window; i < prices.length; i++) {
      ema = (prices[i] * k) + (ema * (1 - k));
    }
    return ema;
  },

  /**
   * Relative Strength Index (RSI)
   */
  calcRSI(prices, window = 14) {
    if (prices.length <= window) return null;
    
    let gains = 0;
    let losses = 0;

    for (let i = prices.length - window; i < prices.length; i++) {
      const diff = prices[i] - prices[i - 1];
      if (diff >= 0) gains += diff;
      else losses -= diff;
    }

    if (losses === 0) return 100;
    const rs = (gains / window) / (losses / window);
    return 100 - (100 / (1 + rs));
  },

  /**
   * MACD (Moving Average Convergence Divergence)
   */
  calcMACD(prices) {
    const fastEMA = this.calcEMA(prices, 12);
    const slowEMA = this.calcEMA(prices, 26);
    if (fastEMA === null || slowEMA === null) return null;
    
    return {
      macdLine: fastEMA - slowEMA,
      signalLine: this.calcEMA(prices, 9) // Simplified signal line
    };
  },

  /**
   * Bollinger Bands
   */
  calcBollingerBands(prices, window = 20, stdDevMultiplier = 2) {
    const sma = this.calcSMA(prices, window);
    if (sma === null) return null;

    const slice = prices.slice(-window);
    const variance = slice.reduce((sum, p) => sum + Math.pow(p - sma, 2), 0) / window;
    const stdDev = Math.sqrt(variance);

    return {
      middle: sma,
      upper: sma + (stdDevMultiplier * stdDev),
      lower: sma - (stdDevMultiplier * stdDev)
    };
  },

  /**
   * Comprehensive Trend Analysis
   * Combines multiple indicators to give a verdict.
   */
  analyzeTrend(prices) {
    const rsi = this.calcRSI(prices, 14);
    const sma50 = this.calcSMA(prices, 50);
    const sma200 = this.calcSMA(prices, 200);
    const currentPrice = prices[prices.length - 1];

    let score = 0; // Positive = Bullish, Negative = Bearish

    if (rsi < 30) score += 1; // Oversold -> Bullish potential
    if (rsi > 70) score -= 1; // Overbought -> Bearish potential
    if (sma50 && currentPrice > sma50) score += 1;
    if (sma200 && currentPrice > sma200) score += 2; // Strong trend
    if (sma50 && currentPrice < sma50) score -= 1;
    if (sma200 && currentPrice < sma200) score -= 2;

    if (score >= 2) return { verdict: 'BULLISH', score, rsi };
    if (score <= -2) return { verdict: 'BEARISH', score, rsi };
    return { verdict: 'NEUTRAL', score, rsi };
  }
};
