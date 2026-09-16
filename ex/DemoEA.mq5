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

input ENUM_TIMEFRAMES InpExecutionTimeframe = PERIOD_M5;
input ENUM_TIMEFRAMES InpHtfTimeframe = PERIOD_H4;
input ENUM_MA_METHOD InpMAMethod = MODE_EMA;
input ENUM_APPLIED_PRICE InpMAApplied = PRICE_CLOSE;
input int InpFastMAPeriod = 12;
input int InpSlowMAPeriod = 21;
input double InpFastMAOpenWeight = 0.65;
input double InpFastMACloseWeight = 0.35;
input double InpOpenThreshold = 6.1;
input double InpCloseThreshold = 2.9;
input bool InpRequestMorningContext = true;
input bool InpRequestHtfContext = true;

int g_fastHandle = INVALID_HANDLE;
int g_slowHandle = INVALID_HANDLE;
datetime g_lastExecBarTime = 0;
datetime g_lastHtfBarTime = 0;
uint g_requestCounter = 0;
string g_morningStateKey;

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

string TimeframeToString(const ENUM_TIMEFRAMES tf)
{
   switch(tf)
   {
      case PERIOD_M1:  return "M1";
      case PERIOD_M5:  return "M5";
      case PERIOD_M15: return "M15";
      case PERIOD_M30: return "M30";
      case PERIOD_H1:  return "H1";
      case PERIOD_H4:  return "H4";
      case PERIOD_D1:  return "D1";
      case PERIOD_W1:  return "W1";
      case PERIOD_MN1: return "MN1";
      default:         return "M5";
   }
}

// jobType decides which timeframe input is reported; signalsJson is a pre-built
// JSON object string (or "" when the job carries no signals, e.g. morning/htf).
bool PostAnalysis(const string jobType, const string signalsJson, const string trigger)
{
   if(StringLen(InpDshSessionId) == 0)
   {
      Print("DSH session ID is empty; analysis was not requested.");
      return false;
   }

   ENUM_TIMEFRAMES tf = (jobType == "htf_context") ? InpHtfTimeframe : InpExecutionTimeframe;
   string requestId = NewRequestId(jobType);
   string signalsField = StringLen(signalsJson) > 0 ? StringFormat(",\"signals\":%s", signalsJson) : "";
   string body = StringFormat(
      "{\"sessionId\":\"%s\",\"requestId\":\"%s\",\"jobType\":\"%s\",\"symbol\":\"%s\",\"timeframes\":[\"%s\"]%s,\"trigger\":\"%s\"}",
      JsonEscape(InpDshSessionId), JsonEscape(requestId), JsonEscape(jobType),
      JsonEscape(_Symbol), TimeframeToString(tf), signalsField, JsonEscape(trigger));

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

// ── Tầng 1: đầu ngày, tổng quan ─────────────────────────────────────
void RequestMorningContext()
{
   if(!InpRequestMorningContext || MorningAlreadyRequested())
      return;

   if(PostAnalysis("morning_context", "", "daily_schedule"))
   {
      GlobalVariableSet(g_morningStateKey, (double)TimeCurrent());
      PrintFormat("Morning analysis accepted for %s.", _Symbol);
   }
}

// ── Tầng 2: định kỳ theo HTF, cập nhật bối cảnh trung hạn ───────────
bool IsNewHtfBar()
{
   datetime currentBar = iTime(_Symbol, InpHtfTimeframe, 0);
   if(currentBar <= 0 || currentBar == g_lastHtfBarTime)
      return false;
   g_lastHtfBarTime = currentBar;
   return true;
}

void RequestHtfContext()
{
   if(!InpRequestHtfContext || !IsNewHtfBar())
      return;

   PostAnalysis("htf_context", "", "new_htf_bar");
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

// ── Tầng 3: mỗi nến execution, lọc sơ bộ rồi để model quyết định ────
bool IsNewExecBar()
{
   datetime currentBar = iTime(_Symbol, InpExecutionTimeframe, 0);
   if(currentBar <= 0 || currentBar == g_lastExecBarTime)
      return false;
   g_lastExecBarTime = currentBar;
   return true;
}

void CheckLtfTriggers()
{
   if(!IsNewExecBar())
      return;

   double fastAngle = CalculateAngle(g_fastHandle);
   double slowAngle = CalculateAngle(g_slowHandle);
   double openWeight = fastAngle * InpFastMAOpenWeight + slowAngle * (1.0 - InpFastMAOpenWeight);
   double closeWeight = fastAngle * InpFastMACloseWeight + slowAngle * (1.0 - InpFastMACloseWeight);

   bool canOpenBuy  = openWeight  >= InpOpenThreshold;
   bool canOpenSell = openWeight  <= -InpOpenThreshold;
   // TODO: hiện đang tạm dùng thuần MA-angle cho TP; sẽ thay bằng pos-manager
   // check lời/lỗ thật khi class đó sẵn sàng.
   bool canTpBuy    = closeWeight <= -InpCloseThreshold;
   bool canTpSell   = closeWeight >= InpCloseThreshold;

   PrintFormat("LTF filter: open=%.1f close=%.1f buy=%s sell=%s tpBuy=%s tpSell=%s",
               openWeight, closeWeight,
               canOpenBuy ? "T" : "F", canOpenSell ? "T" : "F",
               canTpBuy ? "T" : "F", canTpSell ? "T" : "F");

   if(!canOpenBuy && !canOpenSell && !canTpBuy && !canTpSell)
      return; // Không có gì đáng báo — khỏi làm phiền model.

   string signalsJson = StringFormat(
      "{\"can_open_buy\":%s,\"can_open_sell\":%s,\"can_tp_buy\":%s,\"can_tp_sell\":%s}",
      canOpenBuy ? "true" : "false", canOpenSell ? "true" : "false",
      canTpBuy ? "true" : "false", canTpSell ? "true" : "false");

   PostAnalysis("ltf_trigger", signalsJson, "ma_threshold");
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

   g_fastHandle = iMA(_Symbol, InpExecutionTimeframe, InpFastMAPeriod, 0, InpMAMethod, InpMAApplied);
   g_slowHandle = iMA(_Symbol, InpExecutionTimeframe, InpSlowMAPeriod, 0, InpMAMethod, InpMAApplied);
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
   RequestHtfContext();
   CheckLtfTriggers();
}
//+------------------------------------------------------------------+