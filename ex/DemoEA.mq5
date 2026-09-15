//+------------------------------------------------------------------+
//| DemoEA.mq5                                                       |
//| MA filter/scheduler -> DSH API; no direct order execution.       |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026"
#property strict

#include <Trade\Trade.mqh>

input ulong InpMagic = 1234;
input string InpDshApiBaseUrl = "http://127.0.0.1:3080/dsh-api";
input string InpDshSessionId = "session-03229f20-e44d-4594-abe5-9e705e2d4fa3";
input int InpWebRequestTimeoutMs = 10000;
input double InpTrailingThresholdPoints = 1000;
input double InpBufferThresholdPoints = 500;

input ENUM_TIMEFRAMES InpAnalysisTimeframe = PERIOD_CURRENT;
input ENUM_MA_METHOD InpMAMethod = MODE_EMA;
input ENUM_APPLIED_PRICE InpMAApplied = PRICE_CLOSE;
input int InpFastMAPeriod = 12;
input int InpSlowMAPeriod = 21;
input double InpFastMAOpenWeight = 0.65;
input double InpFastMACloseWeight = 0.35;
input double InpOpenThreshold = 6.1;
input double InpCloseThreshold = 2.9;
input bool InpRequestMorningContext = true;

int g_fastHandle = INVALID_HANDLE;
int g_slowHandle = INVALID_HANDLE;
datetime g_lastBarTime = 0;
uint g_requestCounter = 0;
string g_morningStateKey;
string g_lastSignal = "NONE";

string CurrentDateKey()
{
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   return StringFormat("%04d%02d%02d", now.year, now.mon, now.day);
}

string JsonEscape(const string value)
{
   string escaped = value;
   StringReplace(escaped, "\\", "\\\\");
   StringReplace(escaped, "\"", "\\\"");
   StringReplace(escaped, "\r", "\\r");
   StringReplace(escaped, "\n", "\\n");
   return escaped;
}

string NewRequestId(const string kind)
{
   g_requestCounter++;
   return StringFormat("%s-%s-%d-%u", kind, _Symbol, (int)TimeLocal(), g_requestCounter);
}

bool PostAnalysis(const string jobType, const string intent, const string side, const string trigger)
{
   if(StringLen(InpDshSessionId) == 0)
   {
      Print("DSH session ID is empty; analysis was not requested.");
      return false;
   }

   string requestId = NewRequestId(jobType);
   string body = StringFormat(
      "{\"sessionId\":\"%s\",\"requestId\":\"%s\",\"jobType\":\"%s\",\"intent\":\"%s\",\"symbol\":\"%s\",\"side\":\"%s\",\"timeframes\":[\"M15\",\"M5\"],\"trigger\":\"%s\"}",
      JsonEscape(InpDshSessionId), JsonEscape(requestId), JsonEscape(jobType),
      JsonEscape(intent), JsonEscape(_Symbol), JsonEscape(side), JsonEscape(trigger));

   char payload[];
   char response[];
   string responseHeaders;
   string headers = "Content-Type: application/json\r\n";
   StringToCharArray(body, payload, 0, StringLen(body), CP_UTF8);

   ResetLastError();
   int status = WebRequest("POST", InpDshApiBaseUrl + "/session/analyze", headers,
                           InpWebRequestTimeoutMs, payload, ArraySize(payload), response, responseHeaders);
   string responseText = CharArrayToString(response, 0, -1, CP_UTF8);
   if(status == -1)
   {
      PrintFormat("DSH WebRequest failed: error=%d request=%s", GetLastError(), requestId);
      return false;
   }

   PrintFormat("DSH analysis request: status=%d request=%s response=%s", status, requestId, responseText);
   return (status == 200 || status == 202);
}

bool MorningAlreadyRequested()
{
   return GlobalVariableCheck(g_morningStateKey) && GlobalVariableGet(g_morningStateKey) > 0;
}

void RequestMorningContext()
{
   if(!InpRequestMorningContext || MorningAlreadyRequested())
      return;

   if(PostAnalysis("morning_context", "", "", "daily_schedule"))
   {
      GlobalVariableSet(g_morningStateKey, (double)TimeCurrent());
      PrintFormat("Morning analysis accepted for %s.", _Symbol);
   }
}

bool IsNewBar()
{
   datetime currentBar = iTime(_Symbol, InpAnalysisTimeframe, 0);
   if(currentBar <= 0 || currentBar == g_lastBarTime)
      return false;
   g_lastBarTime = currentBar;
   return true;
}

bool ReadMAValues(const int handle, double &currentValue, double &previousValue)
{
   double values[2];
   ArraySetAsSeries(values, true);
   if(CopyBuffer(handle, 0, 1, 2, values) != 2)
      return false;
   currentValue = values[0];
   previousValue = values[1];
   return true;
}

double CalculateAngle(const int handle)
{
   double currentValue;
   double previousValue;
   if(!ReadMAValues(handle, currentValue, previousValue) || previousValue == 0.0)
      return 0.0;

   double slope = ((currentValue - previousValue) / previousValue) * 500.0;
   return MathArctan(slope) * 180.0 / M_PI;
}

void RequestLtfAnalysis(const string intent, const string side, const string trigger)
{
   PostAnalysis("ltf_trigger", intent, side, trigger);
}

void CheckMATriggers()
{
   if(!IsNewBar())
      return;

   double fastAngle = CalculateAngle(g_fastHandle);
   double slowAngle = CalculateAngle(g_slowHandle);
   double openWeight = fastAngle * InpFastMAOpenWeight + slowAngle * (1.0 - InpFastMAOpenWeight);
   double closeWeight = fastAngle * InpFastMACloseWeight + slowAngle * (1.0 - InpFastMACloseWeight);

   PrintFormat("Fast Angle: %.1f, Slow Angle: %.1f, Open Weight: %.1f, Close Weight: %.1f",
               fastAngle, slowAngle, openWeight, closeWeight);
   g_lastSignal = "NONE";

   if(closeWeight <= -InpCloseThreshold)
   {
      g_lastSignal = "REQUEST TP BUY";
      RequestLtfAnalysis("tp", "buy", "ma_close_threshold");
   }
   else if(closeWeight >= InpCloseThreshold)
   {
      g_lastSignal = "REQUEST TP SELL";
      RequestLtfAnalysis("tp", "sell", "ma_close_threshold");
   }

   if(openWeight >= InpOpenThreshold)
   {
      g_lastSignal = "REQUEST BUY ANALYSIS";
      RequestLtfAnalysis("open", "buy", "ma_open_threshold");
   }
   else if(openWeight <= -InpOpenThreshold)
   {
      g_lastSignal = "REQUEST SELL ANALYSIS";
      RequestLtfAnalysis("open", "sell", "ma_open_threshold");
   }
}

void TrailPositions()
{
   CTrade trade;
   trade.SetExpertMagicNumber(InpMagic);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double threshold = InpTrailingThresholdPoints * point;
   double buffer = InpBufferThresholdPoints * point;

   for(int direction = 0; direction < 2; direction++)
   {
      ENUM_POSITION_TYPE type = direction == 0 ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
      double volume = 0.0;
      double weightedPrice = 0.0;
      ulong tickets[];
      ArrayResize(tickets, 0);

      for(int index = PositionsTotal() - 1; index >= 0; index--)
      {
         ulong ticket = PositionGetTicket(index);
         if(ticket == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol)
            continue;
         if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic ||
            (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) != type)
            continue;

         double positionVolume = PositionGetDouble(POSITION_VOLUME);
         volume += positionVolume;
         weightedPrice += positionVolume * PositionGetDouble(POSITION_PRICE_OPEN);
         int size = ArraySize(tickets);
         ArrayResize(tickets, size + 1);
         tickets[size] = ticket;
      }

      if(volume <= 0.0)
         continue;

      double equilibrium = weightedPrice / volume;
      bool valid = type == POSITION_TYPE_BUY ? (bid - equilibrium > threshold) : (equilibrium - ask > threshold);
      if(!valid)
         continue;

      double newSL = type == POSITION_TYPE_BUY ? equilibrium + buffer : equilibrium - buffer;
      int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      newSL = NormalizeDouble(newSL, digits);

      for(int ticketIndex = 0; ticketIndex < ArraySize(tickets); ticketIndex++)
      {
         if(!PositionSelectByTicket(tickets[ticketIndex]))
            continue;
         double currentSL = PositionGetDouble(POSITION_SL);
         bool shouldMove = currentSL == 0.0 ||
            (type == POSITION_TYPE_BUY && newSL > currentSL + point) ||
            (type == POSITION_TYPE_SELL && newSL < currentSL - point);
         if(shouldMove && !trade.PositionModify(tickets[ticketIndex], newSL, PositionGetDouble(POSITION_TP)))
            PrintFormat("Trailing modify failed ticket=%I64u retcode=%u", tickets[ticketIndex], trade.ResultRetcode());
      }
   }
}

int OnInit()
{
   if(InpCloseThreshold <= 0.0 || InpOpenThreshold <= 0.0)
      return INIT_PARAMETERS_INCORRECT;

   ENUM_TIMEFRAMES timeframe = InpAnalysisTimeframe == PERIOD_CURRENT ? (ENUM_TIMEFRAMES)_Period : InpAnalysisTimeframe;
   g_fastHandle = iMA(_Symbol, timeframe, InpFastMAPeriod, 0, InpMAMethod, InpMAApplied);
   g_slowHandle = iMA(_Symbol, timeframe, InpSlowMAPeriod, 0, InpMAMethod, InpMAApplied);
   if(g_fastHandle == INVALID_HANDLE || g_slowHandle == INVALID_HANDLE)
      return INIT_FAILED;

   g_morningStateKey = StringFormat("MT5MCP.Morning.%I64u.%s.%s", InpMagic, _Symbol, CurrentDateKey());
   EventSetTimer(10);
   Print("EA initialized: filter/scheduler mode, no direct order execution.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_fastHandle != INVALID_HANDLE) IndicatorRelease(g_fastHandle);
   if(g_slowHandle != INVALID_HANDLE) IndicatorRelease(g_slowHandle);
}

void OnTimer()
{
   RequestMorningContext();
}

void OnTick()
{
   TrailPositions();
   CheckMATriggers();
}
//+------------------------------------------------------------------+
