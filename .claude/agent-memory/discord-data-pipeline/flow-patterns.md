---
name: Flow Data Patterns
description: Typical row count ranges and outlier thresholds for each Discord flow channel, used to flag anomalies during daily updates
type: reference
updated: 2026-03-29
---

## Typical Trading Day Ranges (rows per day)

| Channel | Low | Typical | High | Extreme Outlier |
|---------|-----|---------|------|-----------------|
| sweeps | 70 | 85-110 | 142 | |
| sexy-flow | 80 | 100-175 | 200 | 355 (2026-03-23) |
| walter | 40 | 70-130 | 180 | 236 (2026-01-03) |
| golden-sweeps | 7 | 12-25 | 39 | |
| trady-flow | 2 | 5-13 | 26 | |

## Weekend / Holiday Pattern

- Weekends and holidays: all flow channels (golden-sweeps, sweeps, trady-flow, sexy-flow) report 0 rows
- Only `walter` posts on non-trading days (typically 3-72 rows of commentary/updates)

## How to apply

- After updating the tracker, compare new counts against yesterday and also the ranges
- Counts significantly above the "High" column may indicate elevated institutional activity or market events
- Zero rows on an expected trading day = possible export failure, investigate before proceeding with analysis

## Flow and news data formats

1. golden-sweeps (Golden Sweep Alerts)                                                                                                                                                                                                                                                             
    Columns: Date|Time|Symbol|Strike|Expiration|Call/Put|Total_SweepsTotal_Premiums                                                                                                                                                                                                                
    Description: High-premium options sweeps indicating aggressive institutional buying                                                                                                                                                                                                            
    Use for: Identifying smart money directional bets, confirming momentum plays                                                                                                                                                                                                                   
2. sweeps (Regular Options Sweeps)                                                                                                                                                                                                                                                                 
    Columns: Date|Time|Symbol|Strike|Expiration|Call_Put|Premiums|Sweep_Count|Sweep_Time                                                                                                                                                                                                           
    Description: Large block options orders executed via sweep-to-fill                                                                                                                                                                                                                             
    Use for: Detecting unusual activity, tracking aggressive entry/exit points                                                                                                                                                                                                                     
3. trady-flow (Tradytics + Unusual Whales Flow)                                                                                                                                                                                                                                                    
    Columns: Date|Time|Source|Symbol|Strike|Expiration|Call_Put|Orders_Today|Total_Prems|Total_Vol|Price|OTM_Pct|OI|Vol_OI_Ratio|Strike_Diff_Pct|Strike_Diff_Dollar|Description                                                                                                                    
    Description: Combined feed from Tradytics Trady Flow and Unusual Whales alerts                                                                                                                                                                                                                 
    Use for: Real-time flow analysis, identifying repeated hits on specific strikes                                                                                                                                                                                                                
4. sexy-flow-beta (Unusual Whales Hot Contracts)                                                                                                                                                                                                                                                   
    Columns: Date|Time|Symbol|Strike|Call_Put|Expiration|Alert_Type|Side|Vol|OI|Vol_OI_Ratio|Premium|OTM_Pct|Bid_Ask_Pct|Avg_Fill|Multileg_Vol|Description                                                                                                                                         
    Description: High-volume unusual options activity with detailed metrics                                                                                                                                                                                                                        
    Alert Types: Hot Contract, Interval (5 min), Repeated Hits                                                                                                                                                                                                                                     
    Use for: Scalping opportunities, momentum confirmation, detecting smart money accumulation                                                                                                                                                                                                     
5. walter (General Flow Updates)                                                                                                                                                                                                                                                                   
    Columns: Date|Time|Description                                                                                                                                                                                                                                                                 
    Description: Miscellaneous options flow and market updates                                                                                                                                                                                                                                     
    Use for: Supplementary context, narrative analysis                                                                                                                                                                                                                                             
    Data Location & Access  