"""Monthly outlook for the DEV station pages (dev only).

Adds a "Monthly outlook — next 6 months, 30-day mean flow" panel/section
ALONGSIDE the untouched daily 7-day forecast and the weekly outlook:

  data (fetched lazily, same sidecar pattern as weekly/):
    ../monthly/<site>.json  baked monthly forecasts for val+test issue
                            dates (all 10 models), per-station 9-feature
                            standardization stats + monthly tsd (live)
    ../dacpm/<site>.json    monthly DACP half-widths (log space) per
                            station x model x lead-month x level + q_end
    ../onnx_m/<site>/*.onnx monthly neural models (live mode, 3D only)

  3D pages (window.HT3D): floating panel (own drag/collapse/maximize)
    right of the weekly panel, with chart, model selector, DACP band
    toggle + level selector, per-month readout and the pooled monthly
    leaderboard; a Live button assembles the current window via the
    page's htGapAssemble()/htBakedAssemble() + fetchLiveSoilSnow()
    (exposed on window by the weekly patcher) and runs the selected
    monthly NEURAL model in-browser (ONNX, [1,29,9] -> [1,6]).
    Non-neural models and the pooled GCN are baked-dates only; the
    panel says so — no fake live.
  classic pages (window.HT_DATA): static in-flow <section> before the
    Drift section, same chart/readout/leaderboard, no drag, no live.

  The daily forecast, weekly outlook, DACP, stats, drift and UI code
  paths are not modified. On 3D pages the weekly patcher's guarded
  window exposure of the live helpers is reused (this patcher adds no
  edit to existing code there); classic pages only gain the section.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_monthly.py
"""
import json
import re
import sys
from pathlib import Path

MARKER = "ht-monthly v1"

# === WEEKLY META (generated from the weekly build; do not hand-edit) ===
# leader: {model: pooled test RMSE (log)} incl. Climatology/Persistence refs
# st:     {site: {model: this-station test RMSE (log)}}
# sum:    {site: {model: {level: [test coverage, mean width cfs]}}}  (weekly DACP)
MONTHLY_META = {"leader":{"PILSTMv1":0.507,"LSTM":0.5206,"Transformer":0.4988,"TFT":0.5212,"GCN":0.5584,"GP RBF":0.5551,"GP Matérn":0.5638,"PatchTST":0.5309,"ARIMA":0.727,"SARIMA":0.5082,"Climatology":0.5184,"Persistence":0.8255},"st":{"01463500":{"PILSTMv1":0.6334,"LSTM":0.6725,"Transformer":0.6594,"TFT":0.6597,"GCN":0.5443,"GP RBF":0.6542,"GP Matérn":0.6593,"PatchTST":0.6548,"ARIMA":0.6667,"SARIMA":0.65,"Climatology":0.6945,"Persistence":0.9834},"01646500":{"PILSTMv1":0.8679,"LSTM":0.9409,"Transformer":0.8653,"TFT":0.983,"GCN":0.7746,"GP RBF":0.9573,"GP Matérn":0.9612,"PatchTST":0.9624,"ARIMA":0.8804,"SARIMA":0.8506,"Climatology":0.9246,"Persistence":1.2508},"02320500":{"PILSTMv1":0.4532,"LSTM":0.5343,"Transformer":0.4957,"TFT":0.5628,"GCN":0.5017,"GP RBF":0.6528,"GP Matérn":0.6331,"PatchTST":0.5032,"ARIMA":0.4587,"SARIMA":0.4794,"Climatology":0.5524,"Persistence":0.4628},"03294500":{"PILSTMv1":0.4703,"LSTM":0.3804,"Transformer":0.4253,"TFT":0.446,"GCN":0.8003,"GP RBF":0.4883,"GP Matérn":0.4639,"PatchTST":0.4763,"ARIMA":1.1679,"SARIMA":0.7191,"Climatology":0.4202,"Persistence":1.2545},"05331000":{"PILSTMv1":0.5347,"LSTM":0.524,"Transformer":0.5848,"TFT":0.5301,"GCN":0.6469,"GP RBF":0.5316,"GP Matérn":0.5388,"PatchTST":0.5453,"ARIMA":0.7808,"SARIMA":0.5616,"Climatology":0.51,"Persistence":0.8612},"06214500":{"PILSTMv1":0.3896,"LSTM":0.3829,"Transformer":0.3443,"TFT":0.3961,"GCN":0.6376,"GP RBF":0.5629,"GP Matérn":0.5615,"PatchTST":0.3559,"ARIMA":0.6795,"SARIMA":0.2289,"Climatology":0.2877,"Persistence":1.0334},"06934500":{"PILSTMv1":0.3961,"LSTM":0.4142,"Transformer":0.3782,"TFT":0.3895,"GCN":0.4497,"GP RBF":0.4107,"GP Matérn":0.4145,"PatchTST":0.3755,"ARIMA":0.6234,"SARIMA":0.3375,"Climatology":0.3574,"Persistence":0.7258},"07374000":{"PILSTMv1":0.3695,"LSTM":0.3613,"Transformer":0.3343,"TFT":0.3734,"GCN":0.3324,"GP RBF":0.4203,"GP Matérn":0.4361,"PatchTST":0.3508,"ARIMA":1.2294,"SARIMA":0.4549,"Climatology":0.4696,"Persistence":0.8308},"08057000":{"PILSTMv1":0.8252,"LSTM":0.789,"Transformer":0.7578,"TFT":0.7786,"GCN":0.7642,"GP RBF":0.7987,"GP Matérn":0.8101,"PatchTST":0.8818,"ARIMA":0.7893,"SARIMA":0.754,"Climatology":0.6356,"Persistence":1.166},"08158000":{"PILSTMv1":0.6735,"LSTM":0.7813,"Transformer":0.6919,"TFT":0.7344,"GCN":0.718,"GP RBF":0.6813,"GP Matérn":0.8107,"PatchTST":0.7809,"ARIMA":0.9947,"SARIMA":0.7413,"Climatology":0.7334,"Persistence":1.0059},"08313000":{"PILSTMv1":0.6564,"LSTM":0.6793,"Transformer":0.6795,"TFT":0.6761,"GCN":0.6927,"GP RBF":0.6963,"GP Matérn":0.6935,"PatchTST":0.7004,"ARIMA":0.6299,"SARIMA":0.6383,"Climatology":0.8148,"Persistence":0.6334},"09380000":{"PILSTMv1":0.1524,"LSTM":0.1516,"Transformer":0.1271,"TFT":0.1206,"GCN":0.1857,"GP RBF":0.1925,"GP Matérn":0.1955,"PatchTST":0.1555,"ARIMA":0.1807,"SARIMA":0.1494,"Climatology":0.2203,"Persistence":0.1834},"11447650":{"PILSTMv1":0.4834,"LSTM":0.4771,"Transformer":0.4707,"TFT":0.4722,"GCN":0.5678,"GP RBF":0.5226,"GP Matérn":0.5169,"PatchTST":0.4958,"ARIMA":0.7708,"SARIMA":0.4506,"Climatology":0.4205,"Persistence":0.797},"14105700":{"PILSTMv1":0.1924,"LSTM":0.1999,"Transformer":0.1689,"TFT":0.174,"GCN":0.2018,"GP RBF":0.2015,"GP Matérn":0.1979,"PatchTST":0.1936,"ARIMA":0.3255,"SARIMA":0.0995,"Climatology":0.216,"Persistence":0.3682}},"sum":{"01463500":{"LSTM":{"70":[0.7274,19655.09],"80":[0.812,21788.81],"90":[0.887,23480.77],"95":[0.9209,24477.28]},"Transformer":{"70":[0.7281,17660.6],"80":[0.8142,19770.9],"90":[0.8922,21428.63],"95":[0.9246,22382.8]},"TFT":{"70":[0.72,18526.76],"80":[0.8087,21458.38],"90":[0.8893,24380.27],"95":[0.9253,26110.69]},"PatchTST":{"70":[0.7082,18711.51],"80":[0.8094,21858.97],"90":[0.8977,25711.68],"95":[0.936,27899.68]},"PILSTMv1":{"70":[0.7255,16342.95],"80":[0.8098,18325.11],"90":[0.8863,19756.9],"95":[0.9213,20847.77]},"GCN":{"70":[0.7046,13268.72],"80":[0.7943,15157.28],"90":[0.8742,16431.34],"95":[0.9102,17211.85]},"GP Matérn":{"70":[0.7222,18206.42],"80":[0.8102,20468.11],"90":[0.8885,22896.81],"95":[0.9242,24234.95]},"GP RBF":{"70":[0.723,17587.05],"80":[0.8054,19990.65],"90":[0.8848,22127.62],"95":[0.9183,23421.51]},"ARIMA":{"70":[0.7248,18133.99],"80":[0.7976,19854.6],"90":[0.8679,20911.57],"95":[0.9018,21590.63]},"SARIMA":{"70":[0.7141,18607.89],"80":[0.78,20542.48],"90":[0.8517,21905.39],"95":[0.8863,22498.02]}},"01646500":{"LSTM":{"70":[0.7207,25365.89],"80":[0.8145,27956.99],"90":[0.8986,31147.25],"95":[0.9357,33163.95]},"Transformer":{"70":[0.7166,22164.83],"80":[0.8101,24909.42],"90":[0.8911,27944.91],"95":[0.9253,30063.6]},"TFT":{"70":[0.7235,30828.59],"80":[0.8132,34152.28],"90":[0.892,37041.17],"95":[0.9266,39024.37]},"PatchTST":{"70":[0.7272,30980.84],"80":[0.8198,34370.16],"90":[0.8983,37602.09],"95":[0.9328,39587.14]},"PILSTMv1":{"70":[0.7172,17032.76],"80":[0.8079,19450.53],"90":[0.8898,21589.11],"95":[0.9272,23180.36]},"GCN":{"70":[0.7075,16277.44],"80":[0.8007,18627.18],"90":[0.8826,20494.77],"95":[0.9203,21802.78]},"GP Matérn":{"70":[0.7046,31377.04],"80":[0.8004,36303.07],"90":[0.8845,40164.72],"95":[0.9218,42701.04]},"GP RBF":{"70":[0.7012,31264.27],"80":[0.7976,35611.16],"90":[0.8826,38817.15],"95":[0.9184,40452.42]},"ARIMA":{"70":[0.7021,18752.65],"80":[0.7932,21523.26],"90":[0.8745,23741.38],"95":[0.9149,24546.74]},"SARIMA":{"70":[0.6886,21063.41],"80":[0.774,22637.36],"90":[0.8449,23372.52],"95":[0.882,23975.25]}},"02320500":{"LSTM":{"70":[0.6718,6260.01],"80":[0.7719,6853.45],"90":[0.8517,7298.22],"95":[0.8896,7478.9]},"Transformer":{"70":[0.6998,5854.79],"80":[0.7987,6762.92],"90":[0.8852,7409.96],"95":[0.9224,7775.61]},"TFT":{"70":[0.6829,6914.32],"80":[0.7844,7531.72],"90":[0.8606,7953.0],"95":[0.8893,8251.14]},"PatchTST":{"70":[0.6932,6411.26],"80":[0.7958,7478.23],"90":[0.8797,8176.2],"95":[0.9121,8657.96]},"PILSTMv1":{"70":[0.7046,5392.58],"80":[0.8024,5989.38],"90":[0.8907,6474.08],"95":[0.9305,6717.11]},"GCN":{"70":[0.6781,5284.53],"80":[0.7807,5770.22],"90":[0.8639,6105.56],"95":[0.9007,6296.67]},"GP Matérn":{"70":[0.6814,9056.81],"80":[0.7914,10430.27],"90":[0.8808,11785.43],"95":[0.9154,12463.55]},"GP RBF":{"70":[0.6836,9687.29],"80":[0.7925,11425.12],"90":[0.8815,12799.99],"95":[0.9169,13648.7]},"ARIMA":{"70":[0.7038,6261.48],"80":[0.7792,6726.83],"90":[0.8503,6978.58],"95":[0.8859,7101.51]},"SARIMA":{"70":[0.6924,6957.54],"80":[0.7822,7450.17],"90":[0.8624,7733.01],"95":[0.9014,7875.9]}},"03294500":{"LSTM":{"70":[0.7114,144139.57],"80":[0.8035,166409.54],"90":[0.8968,185573.66],"95":[0.9328,200278.94]},"Transformer":{"70":[0.709,158835.56],"80":[0.8085,181202.77],"90":[0.8943,200396.88],"95":[0.9279,206617.15]},"TFT":{"70":[0.7114,162172.2],"80":[0.8072,204662.43],"90":[0.8918,229706.08],"95":[0.9266,238422.91]},"PatchTST":{"70":[0.7239,179215.63],"80":[0.8085,216660.68],"90":[0.9017,260783.55],"95":[0.9353,286144.16]},"PILSTMv1":{"70":[0.7338,170959.91],"80":[0.8234,200106.78],"90":[0.8968,219608.22],"95":[0.9279,232590.79]},"GCN":{"70":[0.6803,427704.49],"80":[0.791,529982.98],"90":[0.8818,582970.74],"95":[0.9216,617243.5]},"GP Matérn":{"70":[0.699,166990.82],"80":[0.8072,202457.77],"90":[0.8968,244289.57],"95":[0.9279,263758.49]},"GP RBF":{"70":[0.7052,174652.23],"80":[0.806,219576.02],"90":[0.898,266090.28],"95":[0.9279,290277.59]},"ARIMA":{"70":[0.7488,468281.09],"80":[0.7823,530084.86],"90":[0.8234,547086.45],"95":[0.8458,555728.35]},"SARIMA":{"70":[0.7139,188999.39],"80":[0.7848,218435.34],"90":[0.8408,230600.81],"95":[0.8669,236216.42]}},"05331000":{"LSTM":{"70":[0.7009,17812.84],"80":[0.7965,19973.26],"90":[0.8752,21881.67],"95":[0.9104,23072.84]},"Transformer":{"70":[0.6969,21437.08],"80":[0.7955,25198.21],"90":[0.8835,28705.95],"95":[0.9203,30539.46]},"TFT":{"70":[0.6902,17839.73],"80":[0.7912,20692.55],"90":[0.8792,23830.31],"95":[0.915,25773.5]},"PatchTST":{"70":[0.6942,20438.11],"80":[0.7948,23987.58],"90":[0.8828,28000.76],"95":[0.917,30313.39]},"PILSTMv1":{"70":[0.6965,15504.5],"80":[0.7938,18033.28],"90":[0.8752,20661.51],"95":[0.9094,21747.51]},"GCN":{"70":[0.6982,22754.97],"80":[0.7865,25429.09],"90":[0.8679,27455.8],"95":[0.9074,28560.81]},"GP Matérn":{"70":[0.6916,19144.73],"80":[0.7898,22755.37],"90":[0.8785,26790.73],"95":[0.916,28817.75]},"GP RBF":{"70":[0.6926,18934.14],"80":[0.7925,22198.57],"90":[0.8805,25750.18],"95":[0.9167,27335.2]},"ARIMA":{"70":[0.7155,29378.56],"80":[0.8051,32234.79],"90":[0.8768,34713.25],"95":[0.9133,36677.04]},"SARIMA":{"70":[0.6803,16315.03],"80":[0.753,17087.46],"90":[0.821,17521.13],"95":[0.8586,17897.25]}},"06214500":{"LSTM":{"70":[0.6841,5338.65],"80":[0.7804,6542.8],"90":[0.8692,7055.5],"95":[0.9098,7241.47]},"Transformer":{"70":[0.7,4659.45],"80":[0.7975,5568.29],"90":[0.8775,6178.71],"95":[0.9134,6430.04]},"TFT":{"70":[0.6848,6030.93],"80":[0.7797,7174.77],"90":[0.867,7717.05],"95":[0.9072,8055.48]},"PatchTST":{"70":[0.6899,4183.74],"80":[0.7841,4887.12],"90":[0.8772,5694.16],"95":[0.9156,6079.43]},"PILSTMv1":{"70":[0.6996,5505.78],"80":[0.7902,6061.38],"90":[0.8703,6497.96],"95":[0.9054,6769.6]},"GCN":{"70":[0.6877,8617.95],"80":[0.7862,9849.11],"90":[0.8728,10715.43],"95":[0.9083,11346.35]},"GP Matérn":{"70":[0.6833,7553.48],"80":[0.7855,9186.69],"90":[0.8728,10578.58],"95":[0.9087,11328.08]},"GP RBF":{"70":[0.6841,7713.79],"80":[0.7862,8962.21],"90":[0.8699,10181.62],"95":[0.9058,10676.05]},"ARIMA":{"70":[0.6855,9468.29],"80":[0.7652,10080.06],"90":[0.8395,10452.08],"95":[0.8736,10846.65]},"SARIMA":{"70":[0.6866,2882.31],"80":[0.758,3094.02],"90":[0.8293,3241.56],"95":[0.867,3367.17]}},"06934500":{"LSTM":{"70":[0.6868,60980.38],"80":[0.7913,70054.36],"90":[0.8792,77820.1],"95":[0.9165,81434.99]},"Transformer":{"70":[0.6802,49357.04],"80":[0.7869,59198.33],"90":[0.876,67238.25],"95":[0.9121,71898.79]},"TFT":{"70":[0.6886,60289.0],"80":[0.791,71044.35],"90":[0.8826,80999.75],"95":[0.9209,87473.18]},"PatchTST":{"70":[0.6911,54098.13],"80":[0.7928,66085.59],"90":[0.8836,75661.39],"95":[0.9209,82896.33]},"PILSTMv1":{"70":[0.6849,58032.69],"80":[0.7919,66490.09],"90":[0.8829,74501.51],"95":[0.9234,79534.98]},"GCN":{"70":[0.6918,68175.33],"80":[0.7903,76916.34],"90":[0.8776,84789.71],"95":[0.9137,88990.68]},"GP Matérn":{"70":[0.6855,61890.52],"80":[0.7906,71545.95],"90":[0.8817,82233.11],"95":[0.919,87172.19]},"GP RBF":{"70":[0.6858,61285.91],"80":[0.7897,70826.09],"90":[0.8795,80969.92],"95":[0.9165,85479.02]},"ARIMA":{"70":[0.683,87445.31],"80":[0.7668,95267.29],"90":[0.8365,99691.02],"95":[0.8707,103093.03]},"SARIMA":{"70":[0.6755,50136.45],"80":[0.7489,54259.59],"90":[0.8211,56392.21],"95":[0.8584,57644.86]}},"07374000":{"LSTM":{"70":[0.7075,405416.12],"80":[0.8065,453404.37],"90":[0.8797,486886.08],"95":[0.9146,499724.11]},"Transformer":{"70":[0.7071,365231.16],"80":[0.8021,405245.42],"90":[0.8804,436605.01],"95":[0.9154,453076.07]},"TFT":{"70":[0.6976,430174.41],"80":[0.791,475051.01],"90":[0.8734,516066.2],"95":[0.9054,534250.08]},"PatchTST":{"70":[0.7152,389304.23],"80":[0.8079,436346.51],"90":[0.8845,470785.3],"95":[0.9146,490688.6]},"PILSTMv1":{"70":[0.7119,413527.27],"80":[0.8039,461712.55],"90":[0.8742,495138.81],"95":[0.9069,514048.69]},"GCN":{"70":[0.7329,384553.07],"80":[0.8219,440036.65],"90":[0.9021,479751.97],"95":[0.936,504328.74]},"GP Matérn":{"70":[0.7141,493519.55],"80":[0.8124,566514.64],"90":[0.8977,628745.7],"95":[0.9327,659878.55]},"GP RBF":{"70":[0.7108,471498.94],"80":[0.8072,532759.14],"90":[0.8933,586720.69],"95":[0.9275,620501.44]},"ARIMA":{"70":[0.7285,921050.28],"80":[0.8061,1055948.24],"90":[0.8668,211823117.48],"95":[0.8999,397382365.33]},"SARIMA":{"70":[0.6884,526673.54],"80":[0.7597,554023.13],"90":[0.8116,564773.3],"95":[0.84,575095.91]}},"08057000":{"LSTM":{"70":[0.6981,3768.24],"80":[0.7933,4356.96],"90":[0.8785,4861.61],"95":[0.9158,5172.59]},"Transformer":{"70":[0.7053,3785.38],"80":[0.7974,4384.16],"90":[0.8841,4777.24],"95":[0.9217,5013.59]},"TFT":{"70":[0.7005,3939.31],"80":[0.7992,4690.4],"90":[0.8834,5184.47],"95":[0.9217,5535.08]},"PatchTST":{"70":[0.6946,5232.42],"80":[0.7961,6561.9],"90":[0.8841,8165.24],"95":[0.9196,9328.38]},"PILSTMv1":{"70":[0.6915,3652.17],"80":[0.7854,4155.51],"90":[0.8703,4623.79],"95":[0.9096,4937.62]},"GCN":{"70":[0.6991,3092.49],"80":[0.7995,3665.74],"90":[0.8823,4057.59],"95":[0.9186,4287.74]},"GP Matérn":{"70":[0.6991,4332.01],"80":[0.7964,5256.07],"90":[0.8827,6221.44],"95":[0.9189,6755.4]},"GP RBF":{"70":[0.6984,4057.61],"80":[0.7954,4813.43],"90":[0.883,5737.52],"95":[0.9213,6298.38]},"ARIMA":{"70":[0.6915,3081.57],"80":[0.7698,3600.64],"90":[0.8499,3800.13],"95":[0.8879,3905.07]},"SARIMA":{"70":[0.697,2965.86],"80":[0.7723,3485.45],"90":[0.8496,3704.41],"95":[0.8879,3845.32]}},"08158000":{"LSTM":{"70":[0.7059,831.65],"80":[0.8057,984.18],"90":[0.8961,1163.97],"95":[0.9316,1331.26]},"Transformer":{"70":[0.7043,649.01],"80":[0.7985,860.16],"90":[0.8848,1051.73],"95":[0.9212,1147.74]},"TFT":{"70":[0.7003,692.79],"80":[0.7991,834.84],"90":[0.887,976.36],"95":[0.9203,1043.88]},"PatchTST":{"70":[0.7053,768.47],"80":[0.8032,931.61],"90":[0.8945,1151.92],"95":[0.9306,1302.87]},"PILSTMv1":{"70":[0.6974,529.21],"80":[0.7966,640.2],"90":[0.8873,745.7],"95":[0.9244,802.07]},"GCN":{"70":[0.7018,736.12],"80":[0.8007,886.94],"90":[0.8908,1032.06],"95":[0.9294,1110.02]},"GP Matérn":{"70":[0.7006,866.21],"80":[0.8032,1098.31],"90":[0.8977,1430.25],"95":[0.9347,1657.94]},"GP RBF":{"70":[0.704,733.18],"80":[0.8032,925.06],"90":[0.897,1141.23],"95":[0.9353,1275.33]},"ARIMA":{"70":[0.6739,898.15],"80":[0.7593,1004.7],"90":[0.8365,1083.62],"95":[0.8726,1117.52]},"SARIMA":{"70":[0.6786,510.49],"80":[0.7505,577.74],"90":[0.8267,614.53],"95":[0.8622,637.92]}},"08313000":{"LSTM":{"70":[0.6915,1493.32],"80":[0.7863,1673.81],"90":[0.8679,1791.51],"95":[0.9046,1848.64]},"Transformer":{"70":[0.689,1473.39],"80":[0.7841,1632.79],"90":[0.8632,1736.12],"95":[0.8989,1789.5]},"TFT":{"70":[0.6899,1597.3],"80":[0.7781,1800.54],"90":[0.861,1912.99],"95":[0.8989,1977.04]},"PatchTST":{"70":[0.6918,1625.79],"80":[0.7884,1858.29],"90":[0.876,2023.47],"95":[0.9134,2116.59]},"PILSTMv1":{"70":[0.6915,1321.71],"80":[0.7866,1500.85],"90":[0.8685,1616.52],"95":[0.904,1673.44]},"GCN":{"70":[0.6817,1697.03],"80":[0.7646,1817.17],"90":[0.8434,1904.21],"95":[0.8785,1954.02]},"GP Matérn":{"70":[0.6933,1529.9],"80":[0.7928,1753.19],"90":[0.8826,1941.54],"95":[0.9171,2027.85]},"GP RBF":{"70":[0.6965,1531.36],"80":[0.7979,1737.27],"90":[0.8858,1972.21],"95":[0.9196,2072.71]},"ARIMA":{"70":[0.6127,1266.64],"80":[0.6616,1348.82],"90":[0.7159,1398.31],"95":[0.7439,1414.48]},"SARIMA":{"70":[0.6626,1559.01],"80":[0.7181,1637.87],"90":[0.7941,1648.17],"95":[0.8305,1668.32]}},"09380000":{"LSTM":{"70":[0.6929,3205.68],"80":[0.7972,3693.1],"90":[0.8893,4097.02],"95":[0.9254,4329.91]},"Transformer":{"70":[0.6868,2672.28],"80":[0.7854,2992.54],"90":[0.8729,3244.58],"95":[0.9091,3436.25]},"TFT":{"70":[0.6891,2456.44],"80":[0.7884,2825.77],"90":[0.8752,3090.54],"95":[0.914,3270.95]},"PatchTST":{"70":[0.6819,3286.66],"80":[0.79,3760.71],"90":[0.8839,4322.44],"95":[0.922,4663.79]},"PILSTMv1":{"70":[0.6849,3250.18],"80":[0.7854,3592.09],"90":[0.8725,3927.13],"95":[0.9091,4155.25]},"GCN":{"70":[0.6804,4543.77],"80":[0.7785,4821.49],"90":[0.8623,5066.29],"95":[0.8984,5190.38]},"GP Matérn":{"70":[0.6853,4107.62],"80":[0.7869,4621.22],"90":[0.8725,4973.29],"95":[0.9064,5152.82]},"GP RBF":{"70":[0.6857,4037.27],"80":[0.7835,4473.86],"90":[0.8672,4799.4],"95":[0.9011,4988.12]},"ARIMA":{"70":[0.7108,3890.92],"80":[0.782,4251.68],"90":[0.844,4427.65],"95":[0.8775,4538.22]},"SARIMA":{"70":[0.6495,3130.73],"80":[0.7245,3235.53],"90":[0.7991,3313.92],"95":[0.8349,3371.78]}},"11447650":{"LSTM":{"70":[0.7122,23385.58],"80":[0.8041,27224.14],"90":[0.8792,29278.01],"95":[0.9124,31082.12]},"Transformer":{"70":[0.7072,23750.41],"80":[0.8041,27849.56],"90":[0.887,30395.41],"95":[0.9253,32088.47]},"TFT":{"70":[0.7009,25028.87],"80":[0.7969,29723.52],"90":[0.8798,32706.25],"95":[0.9187,35038.08]},"PatchTST":{"70":[0.7024,24986.69],"80":[0.801,30661.96],"90":[0.8889,35113.98],"95":[0.9294,38242.78]},"PILSTMv1":{"70":[0.709,24253.71],"80":[0.7988,28474.25],"90":[0.876,31076.68],"95":[0.9121,32915.03]},"GCN":{"70":[0.7166,27803.55],"80":[0.8079,31614.66],"90":[0.8798,34102.97],"95":[0.9143,35828.88]},"GP Matérn":{"70":[0.7122,25539.88],"80":[0.8041,30062.69],"90":[0.8823,33844.06],"95":[0.9196,37058.94]},"GP RBF":{"70":[0.7144,25307.31],"80":[0.8035,29649.05],"90":[0.8801,33325.52],"95":[0.9184,35983.14]},"ARIMA":{"70":[0.6999,52797.93],"80":[0.7806,57760.03],"90":[0.8528,60874.73],"95":[0.8895,62881.91]},"SARIMA":{"70":[0.7006,27892.82],"80":[0.7919,30482.13],"90":[0.8704,31877.73],"95":[0.909,32917.26]}},"14105700":{"LSTM":{"70":[0.694,66586.72],"80":[0.7934,79217.31],"90":[0.8786,90414.82],"95":[0.9138,96485.74]},"Transformer":{"70":[0.6871,59040.44],"80":[0.7833,66694.66],"90":[0.8645,72711.03],"95":[0.8978,75688.51]},"TFT":{"70":[0.6959,61265.16],"80":[0.7931,72076.94],"90":[0.8796,79817.26],"95":[0.916,83852.6]},"PatchTST":{"70":[0.6846,66667.28],"80":[0.7881,78622.08],"90":[0.8836,91231.28],"95":[0.9214,97998.84]},"PILSTMv1":{"70":[0.6947,62782.68],"80":[0.7937,75342.72],"90":[0.8805,85663.03],"95":[0.9164,91145.13]},"GCN":{"70":[0.6943,72603.02],"80":[0.7912,83230.38],"90":[0.8824,93306.02],"95":[0.922,99279.89]},"GP Matérn":{"70":[0.6855,66030.39],"80":[0.7884,80102.28],"90":[0.8714,90751.59],"95":[0.9022,95747.74]},"GP RBF":{"70":[0.6868,67553.2],"80":[0.7896,82536.49],"90":[0.8758,94274.62],"95":[0.9066,99984.87]},"ARIMA":{"70":[0.6965,94595.72],"80":[0.7862,105885.48],"90":[0.8566,112912.03],"95":[0.8912,116235.89]},"SARIMA":{"70":[0.7053,32885.73],"80":[0.7909,37977.79],"90":[0.8585,39643.27],"95":[0.894,40538.63]}}}}

# --------------------------- anchors: 3D pages ----------------------------
D_LIVE_OLD = "async function bigModelLive() {"
D_LIVE_NEW = ("/* ht-monthly v1: expose live helpers for the weekly outlook panel */\n"
              "if (typeof htGapAssemble === 'function') window.htGapAssemble = htGapAssemble;\n"
              "if (typeof htBakedAssemble === 'function') window.htBakedAssemble = htBakedAssemble;\n"
              "if (typeof fetchLiveSoilSnow === 'function') window.fetchLiveSoilSnow = fetchLiveSoilSnow;\n"
              + D_LIVE_OLD)

# ------------------------- anchors: classic pages -------------------------
C_SEC_OLD = '<section class="hts-sec" id="hts-sec-drift">'
C_SEC_NEW = ('<section class="hts-sec" id="hts-sec-monthly">\n'
             '   <h2>Monthly outlook</h2>\n'
             '   <p>Outlook for the next 6 months (30-day mean flow) from the monthly models '
             '(alongside the daily 7-day forecast and the weekly outlook above).</p>\n'
             '   <div id="htmo-root"></div>\n'
             '  </section>\n  ' + C_SEC_OLD)

# ------------------------------ injected UI -------------------------------
JS_BODY = r"""
<script>
/* ht-monthly v1 - Monthly outlook: next 6 months of 30-day mean flow (dev).
 * Baked forecasts + monthly DACP half-widths ship as sidecars in
 * ../monthly/<site>.json and ../dacpm/<site>.json; live mode (3D pages)
 * runs the monthly neural ONNX models in ../onnx_m/<site>/. */
(function () {
  var NEURAL = ['LSTM', 'Transformer', 'TFT', 'PatchTST', 'PILSTMv1'];
  var META = window.__moMeta || { leader: {}, st: {}, sum: {} };
  var W = { model: null, follow: true, on: true, lvl: 90, wk: null, dq: null,
            wkErr: false, dqErr: false, live: null, busy: false, touched: false };
  var is3d = !!window.HT3D;
  function pay() {
    try {
      if (window.HT_DATA) { var D = window.HT_DATA; return { models: D.models, pred: D.pred, flow: D.flow, start: D.start, site: (D.station && D.station.stationId || '').replace('USGS-', '') }; }
      if (window.HT3D) { var E = window.HT3D; return { models: E.models, pred: E.pred, flow: E.flow, start: E.start, site: E.site }; }
    } catch (e) {}
    return null;
  }
  function $(id) { return document.getElementById(id); }
  function fmt(v) { return (v == null || !isFinite(v)) ? '–' : Math.round(v).toLocaleString('en-US'); }
  function isoOf(P, i) { return new Date(Date.parse(P.start + 'T00:00:00Z') + i * 864e5).toISOString().slice(0, 10); }
  function addDays(iso, k) { return new Date(Date.parse(iso + 'T00:00:00Z') + k * 864e5).toISOString().slice(0, 10); }
  function blockMean(flow, endIdx) {
    if (endIdx < 29 || endIdx >= flow.length) return null;
    var s = 0, c = 0;
    for (var j = endIdx - 29; j <= endIdx; j++) { var v = flow[j]; if (v != null && v > 0) { s += v; c++; } }
    return c >= 20 ? s / c : null;
  }
  function load() {
    var P = pay(); if (!P || !P.site) return;
    if (!W.wk && !W.wkErr) {
      fetch('../monthly/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { W.wk = j; W.wk.idx = {}; j.dates.forEach(function (d, i) { W.wk.idx[d] = i; }); render(); })
        .catch(function () { W.wkErr = true; render(); });
    }
    if (!W.dq && !W.dqErr) {
      fetch('../dacpm/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { W.dq = j; W.dq.idx = {}; j.dates.forEach(function (d, i) { W.dq.idx[d] = i; }); render(); })
        .catch(function () { W.dqErr = true; });
    }
  }
  function curModel() {
    var P = pay(), S = window.__htS;
    if (W.follow && P && S && P.models[S.model]) return P.models[S.model];
    return W.model;
  }
  function boardHTML(sel) {
    var L = META.leader || {};
    var names = Object.keys(L).sort(function (a, b) { return L[a] - L[b]; });
    if (!names.length) return '';
    var rows = names.map(function (n) {
      var ref = (n === 'Climatology' || n === 'Persistence');
      return '<tr' + (n === sel ? ' class="htmo-sel"' : '') + '><td>' + n + (ref ? ' (reference)' : '') + '</td><td>' + L[n].toFixed(4) + '</td></tr>';
    }).join('');
    return '<div class="htmo-board"><div class="htmo-bt">Monthly outlook — next 6 months, 30-day mean flow · pooled test RMSE (log space), all 14 stations</div>'
      + '<table>' + rows + '</table></div>';
  }
  function draw(cv, ctx, fc, act, band) {
    var g = cv.getContext('2d'); if (!g) return;
    var cw = cv.width, ch = cv.height;
    g.clearRect(0, 0, cw, ch);
    var vals = [];
    ctx.concat(fc, act).forEach(function (p) { if (p[1] != null) vals.push(p[1]); });
    if (band) band.forEach(function (b) { if (b) { vals.push(b[0]); vals.push(b[1]); } });
    if (!vals.length) { g.fillStyle = '#9fb4c8'; g.font = '22px system-ui'; g.fillText('no monthly data for this date', 18, 40); return; }
    var lo = Math.floor(Math.log10(Math.min.apply(null, vals))), hi = Math.ceil(Math.log10(Math.max.apply(null, vals)));
    if (hi <= lo) hi = lo + 1;
    var X0 = 64, X1 = cw - 14, Y0 = 12, Y1 = ch - 30;
    function X(x) { return X0 + (x + 4.6) / 11.2 * (X1 - X0); }
    function Y(v) { var t = (Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo); return Y1 - t * (Y1 - Y0); }
    g.font = '19px system-ui'; g.textBaseline = 'middle';
    for (var e = lo; e <= hi; e++) {
      var yv = Math.pow(10, e), yy = Y(yv);
      g.strokeStyle = 'rgba(255,255,255,.13)'; g.beginPath(); g.moveTo(X0, yy); g.lineTo(X1, yy); g.stroke();
      g.fillStyle = '#9fb4c8'; g.fillText(fmt(yv), 6, yy);
    }
    g.strokeStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.moveTo(X(0), Y0); g.lineTo(X(0), Y1); g.stroke();
    g.fillStyle = '#9fb4c8';
    [-4, -2, 0, 2, 4, 6].forEach(function (x) { g.fillText(x === 0 ? 'issue' : (x > 0 ? '+' + x + 'mo' : x + 'mo'), X(x) - 10, Y1 + 15); });
    function line(pts, style, width, dash) {
      g.save(); g.strokeStyle = style; g.lineWidth = width; g.setLineDash(dash || []);
      g.beginPath(); var started = false;
      pts.forEach(function (p) { if (p[1] == null) { started = false; return; } var xx = X(p[0]), yy2 = Y(p[1]); if (!started) { g.moveTo(xx, yy2); started = true; } else g.lineTo(xx, yy2); });
      g.stroke(); g.restore();
    }
    if (band) {
      g.save(); g.fillStyle = 'rgba(76,201,240,.16)'; g.beginPath();
      var started = false;
      fc.forEach(function (p, k) { if (p[1] == null || !band[k]) return; var xx = X(p[0]), yy2 = Y(band[k][1]); if (!started) { g.moveTo(xx, yy2); started = true; } else g.lineTo(xx, yy2); });
      for (var b = fc.length - 1; b >= 0; b--) { if (fc[b][1] == null || !band[b]) continue; g.lineTo(X(fc[b][0]), Y(band[b][0])); }
      g.closePath(); g.fill(); g.restore();
    }
    var ctxLine = ctx.slice(); var lastC = ctx.length ? ctx[ctx.length - 1] : null;
    line(ctxLine, '#9fb4c8', 2);
    if (act.length) line(act, 'rgba(255,255,255,.85)', 2, [6, 5]);
    var fcLine = fc.slice(); if (lastC && lastC[1] != null) fcLine = [[0, lastC[1]]].concat(fcLine);
    line(fcLine, '#4CC9F0', 2.5);
    g.fillStyle = '#4CC9F0'; g.fillText('— forecast', X(1.4), Y0 + 10);
    g.fillStyle = '#9fb4c8'; g.fillText('— observed 30-day mean', X(-4.4), Y0 + 10);
    if (act.length) { g.fillStyle = '#fff'; g.fillText('- - actual outcome', X(4.2), Y0 + 10); }
  }
  function stationLine(P, model) {
    var st = (META.st[P.site] || {})[model];
    var sum = ((META.sum[P.site] || {})[model] || {})[String(W.lvl)];
    var out = '';
    if (st != null) out += 'This station · ' + model + ' monthly test RMSE ' + st.toFixed(4);
    if (W.on && sum) out += (out ? ' · ' : '') + 'DACP ' + W.lvl + '% test coverage ' + sum[0].toFixed(2) + ' · mean width ' + fmt(sum[1]) + ' cfs';
    return out;
  }
  function render() {
    var root = $('htmo-root'); if (!root) return;
    var P = pay(), S = window.__htS;
    if (!P) { root.innerHTML = '<div class="htmo-note">monthly outlook unavailable</div>'; return; }
    if (W.wkErr) { var re1 = $('htmo-read'); if (re1) re1.innerHTML = '<div class="htmo-note">monthly forecasts unavailable (sidecar missing)</div>'; else root.innerHTML = '<div class="htmo-note">monthly forecasts unavailable (sidecar missing)</div>'; return; }
    if (!W.wk) { if (!$('htmo-canvas')) root.innerHTML = '<div class="htmo-note">loading monthly outlook…</div>'; load(); return; }
    var model = curModel();
    if (!model || W.wk.models.indexOf(model) < 0) model = W.wk.models[0];
    var sel = $('htmo-model');
    if (sel && sel.value !== model && !W.touched) sel.value = model;
    if (sel && W.touched) model = sel.value;
    W.model = model;
    var issueEl = $('htmo-issue'), readEl = $('htmo-read'), cv = $('htmo-canvas');
    var ctx = [], fc = [], act = [], band = null, issueTxt = '', rows = [];
    if (W.live) {
      var L = W.live;
      ctx = L.ctx; fc = L.preds.map(function (v, k) { return [k + 1, v]; });
      if (W.on && L.q) band = L.preds.map(function (v, k) { return L.q[k] == null ? null : [v * Math.exp(-L.q[k]), v * Math.exp(L.q[k])]; });
      issueTxt = 'LIVE outlook · issued ' + L.issue + ' (window ends ' + L.issue + ') · ' + model + ' run in-browser';
      rows = L.preds.map(function (v, k) { return [k + 1, addDays(L.issue, 30 * k + 1), addDays(L.issue, 30 * k + 30), v, band ? band[k] : null, null]; });
    } else {
      if (!S) { issueEl.textContent = '…'; return; }
      var day = S.day, issue = isoOf(P, day);
      for (var j = 4; j >= 1; j--) ctx.push([-j, blockMean(P.flow, day - 30 * (j - 1))]);
      for (var k2 = 1; k2 <= 6; k2++) { var am = blockMean(P.flow, day + 30 * k2); if (am != null) act.push([k2, am]); }
      var di = W.wk.idx[issue];
      var preds = (di != null) ? W.wk.predw[model][di] : null;
      issueTxt = 'Issue date ' + issue + ' · ' + model + (preds ? '' : ' · no baked monthly forecast for this date (monthly outlook covers ' + W.wk.dates[0] + ' … ' + W.wk.dates[W.wk.dates.length - 1] + ')');
      if (preds) {
        fc = preds.map(function (v, k) { return [k + 1, v]; });
        var qi = (W.on && W.dq) ? W.dq.idx[issue] : null;
        if (qi != null && W.dq.q[model]) {
          var ql = W.dq.q[model][String(W.lvl)];
          if (ql) band = preds.map(function (v, k) { var q = ql[k][qi]; return (q == null || v == null) ? null : [v * Math.exp(-q), v * Math.exp(q)]; });
        }
        rows = preds.map(function (v, k) {
          var a = blockMean(P.flow, day + 30 * (k + 1));
          return [k + 1, addDays(issue, 30 * k + 1), addDays(issue, 30 * k + 30), v, band ? band[k] : null, a];
        });
      }
    }
    if (issueEl) issueEl.textContent = issueTxt;
    if (cv) draw(cv, ctx, fc, act, band);
    if (readEl) {
      var html = '';
      if (rows.length) {
        html += '<table class="htmo-t"><tr><th>Mo</th><th>Month (30 d)</th><th>Forecast</th>' + (band ? '<th>' + W.lvl + '% DACP</th>' : '') + '<th>Observed</th></tr>';
        rows.forEach(function (r) {
          html += '<tr><td>' + r[0] + '</td><td>' + r[1].slice(5) + ' – ' + r[2].slice(5) + '</td><td>' + fmt(r[3]) + '</td>'
            + (band ? '<td>' + (r[4] ? fmt(r[4][0]) + ' – ' + fmt(r[4][1]) : '–') + '</td>' : '')
            + '<td>' + fmt(r[5]) + '</td></tr>';
        });
        html += '</table><div class="htmo-note">cfs, 30-day mean flow</div>';
      }
      var sl = stationLine(P, model);
      if (sl) html += '<div class="htmo-note">' + sl + '</div>';
      html += boardHTML(model);
      readEl.innerHTML = html;
    }
  }
  async function runLive() {
    var P = pay(); if (!P) return;
    var model = W.model || curModel();
    var st = $('htmo-status');
    function say(t) { if (st) st.textContent = t; }
    if (!window.htGapAssemble || !window.fetchLiveSoilSnow) { say('live assembly unavailable on this page'); return; }
    if (NEURAL.indexOf(model) < 0) { say('Live monthly outlook runs the neural models in-browser (LSTM, Transformer, TFT, PatchTST, PILSTMv1). ' + model + ' is baked-dates only.'); return; }
    if (!W.wk) { say('monthly data still loading…'); load(); return; }
    if (W.busy) return;
    W.busy = true; say('live: fetching newest daily data…');
    try {
      var A = null;
      try { A = await window.htGapAssemble(); } catch (e1) { A = null; }
      var H3 = window.HT3D || {};
      var bN = (H3.flow || []).length;
      var bEnd = (H3.start && bN) ? new Date(Date.parse(H3.start + 'T00:00:00Z') + (bN - 1) * 864e5).toISOString().slice(0, 10) : '';
      var flows, wx, win30;
      if (A && A.win30[29] >= bEnd) { flows = A.flows; wx = A.wx; win30 = A.win30; }
      else if (window.htBakedAssemble) { var B = await window.htBakedAssemble(); flows = B.flows; wx = B.wx; win30 = B.win30; }
      else throw new Error('no live window available');
      var stats = W.wk.stats, mu = stats.mu, sd = stats.sd, tsd = stats.tsd;
      var ss = await window.fetchLiveSoilSnow();
      var flat = new Float32Array(29 * 9);
      var prev = flows[win30[0]];
      for (var i = 1; i < 30; i++) {
        var dt = win30[i], t = wx[dt], q = flows[dt];
        if (!t || q == null) throw new Error('live window has gaps');
        var row = [t[0], t[1], (t[0] + t[1]) / 2, t[2], q, q > prev ? 1 : 0, ss.sms, ss.stmpF, ss.swe];
        prev = q;
        for (var j = 0; j < 9; j++) { var x = j === 4 ? Math.log(row[j]) : row[j]; flat[(i - 1) * 9 + j] = (x - mu[j]) / sd[j]; }
      }
      var last = Math.log(flows[win30[29]]);
      if (typeof ort === 'undefined') throw new Error('onnxruntime failed to load (CDN blocked?)');
      var url = '../onnx_m/' + P.site + '/' + model + '.onnx';
      var sess = await ort.InferenceSession.create(url);
      var feeds = {}; feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
      var out = await sess.run(feeds);
      var diffs = Array.from(out[sess.outputNames[0]].data);
      if (diffs.length !== 6 || diffs.some(function (v) { return !isFinite(v); })) throw new Error('bad model output');
      var preds = diffs.map(function (d, k) { return Math.exp(last + d * tsd[k]); });
      var ctxD = [];
      for (var j2 = 4; j2 >= 1; j2--) {
        var s = 0, c = 0;
        for (var d2 = 0; d2 < 30; d2++) { var iso = addDays(win30[29], -30 * (j2 - 1) - d2); var v = flows[iso]; if (v != null && v > 0) { s += v; c++; } }
        ctxD.push([-j2, c >= 20 ? s / c : null]);
      }
      var q = null;
      if (W.dq && W.dq.q_end[model]) q = W.dq.q_end[model][String(W.lvl)];
      W.live = { issue: win30[29], preds: preds, ctx: ctxD, q: q };
      say('live outlook issued ' + win30[29] + ' · ' + model);
      var bx = $('htmo-back'); if (bx) bx.style.display = '';
      render();
    } catch (e) {
      say('live monthly failed: ' + (e && e.message ? e.message : e));
    }
    W.busy = false;
  }
  function controlsHTML() {
    var P = pay();
    var opts = (W.wk ? W.wk.models : (P ? P.models : [])).map(function (m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
    return '<div class="htmo-ctl">'
      + '<label>model <select id="htmo-model">' + opts + '</select></label>'
      + '<label style="cursor:pointer"><input type="checkbox" id="htmo-on" checked> DACP band</label>'
      + '<label>level <select id="htmo-lvl"><option value="70">70%</option><option value="80">80%</option><option value="90" selected>90%</option><option value="95">95%</option></select></label>'
      + (is3d ? '<button type="button" id="htmo-live">▶ Live monthly outlook</button><button type="button" id="htmo-back" style="display:none">↩ selected date</button>' : '')
      + '</div>'
      + '<div id="htmo-issue" class="htmo-issue"></div>'
      + '<canvas id="htmo-canvas" width="760" height="380"></canvas>'
      + '<div id="htmo-read"></div>'
      + (is3d ? '<div id="htmo-status" class="htmo-note"></div>' : '');
  }
  function wire() {
    var m = $('htmo-model');
    if (m) m.addEventListener('change', function () { W.touched = true; W.follow = false; W.model = this.value; render(); });
    var on = $('htmo-on');
    if (on) on.addEventListener('change', function () { W.on = this.checked; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lv = $('htmo-lvl');
    if (lv) lv.addEventListener('change', function () { W.lvl = +this.value; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lb = $('htmo-live');
    if (lb) lb.addEventListener('click', runLive);
    var bb = $('htmo-back');
    if (bb) bb.addEventListener('click', function () { W.live = null; bb.style.display = 'none'; var st = $('htmo-status'); if (st) st.textContent = ''; render(); });
  }
  var css = '.htmo-ctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0}'
    + '.htmo-ctl select,.htmo-ctl button{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:3px 6px;cursor:pointer}'
    + '.htmo-issue{font-weight:600;color:#BFD0E0;margin:2px 0 4px}'
    + '#htmo-canvas{width:100%;height:auto;display:block;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.12);border-radius:8px}'
    + '.htmo-t{border-collapse:collapse;width:100%;font-size:12px;margin-top:6px}'
    + '.htmo-t th,.htmo-t td{border-bottom:1px solid rgba(255,255,255,.12);padding:2px 6px;text-align:right}'
    + '.htmo-t th:first-child,.htmo-t td:first-child,.htmo-t td:nth-child(2){text-align:left}'
    + '.htmo-note{opacity:.85;font-size:12px;margin-top:6px}'
    + '.htmo-board{margin-top:10px}.htmo-bt{font-weight:700;color:#8FC1F2;font-size:12.5px;margin-bottom:4px}'
    + '.htmo-board table{border-collapse:collapse;font-size:12px}'
    + '.htmo-board td{padding:1px 10px 1px 0}'
    + '.htmo-board tr.htmo-sel td{color:#4CC9F0;font-weight:700}'
    + '#htmo-panel{position:fixed;left:466px;bottom:76px;z-index:9997;width:440px;max-width:94vw;background:rgba(12,18,28,.94);color:#e8eef5;border:1px solid rgba(255,255,255,.16);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.45);font:12.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}'
    + '#htmo-panel .htmo-head{display:flex;justify-content:space-between;align-items:center;background:rgba(12,18,28,.9);color:#BFD0E0;font-weight:700;padding:6px 8px 6px 12px;border-radius:12px 12px 0 0;cursor:move;user-select:none;-webkit-user-select:none}'
    + '#htmo-panel .htmo-head button{background:rgba(35,70,110,.9);border:1px solid rgba(255,255,255,.35);color:#E6EDF5;border-radius:6px;min-width:24px;height:24px;padding:0 6px;cursor:pointer;font:600 13px/1 Arial}'
    + '#htmo-panel .htmo-body{padding:8px 12px 12px;max-height:66vh;overflow:auto}'
    + '#htmo-panel.htmo-max{left:10px !important;top:10px !important;bottom:auto !important;width:calc(100vw - 20px) !important;max-width:none !important}'
    + '#htmo-panel.htmo-max .htmo-body{max-height:calc(100vh - 90px)}'
    + '#htmo-panel .htmo-dev{background:#d9930d;color:#111;border-radius:4px;padding:0 5px;font-size:10px;vertical-align:1px;margin-left:6px}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);
  if (is3d) {
    var panel = document.createElement('div'); panel.id = 'htmo-panel';
    panel.innerHTML = '<div class="htmo-head" id="htmo-head"><span>Monthly outlook<span class="htmo-dev">DEV</span></span>'
      + '<span><button type="button" id="htmo-max" aria-label="maximize">⛶</button> <button type="button" id="htmo-min" aria-label="collapse">–</button></span></div>'
      + '<div class="htmo-body" id="htmo-body"><div id="htmo-root"></div></div>';
    document.body.appendChild(panel);
    var root0 = $('htmo-root'); root0.innerHTML = controlsHTML();
    wire(); load(); render();
    var head = $('htmo-head'), dragging = null;
    head.addEventListener('mousedown', function (ev) {
      if (ev.target.closest('button')) return;
      var r = panel.getBoundingClientRect();
      dragging = { dx: ev.clientX - r.left, dy: ev.clientY - r.top };
      panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px'; panel.style.bottom = 'auto';
      ev.preventDefault();
    });
    document.addEventListener('mousemove', function (ev) {
      if (!dragging) return;
      var nx = Math.max(0, Math.min(window.innerWidth - 80, ev.clientX - dragging.dx));
      var ny = Math.max(0, Math.min(window.innerHeight - 40, ev.clientY - dragging.dy));
      panel.style.left = nx + 'px'; panel.style.top = ny + 'px';
    });
    document.addEventListener('mouseup', function () { dragging = null; });
    $('htmo-min').addEventListener('click', function () {
      var b = $('htmo-body'); var hid = b.style.display === 'none';
      b.style.display = hid ? '' : 'none'; this.textContent = hid ? '–' : '+';
    });
    $('htmo-max').addEventListener('click', function () { panel.classList.toggle('htmo-max'); });
  } else {
    var root1 = $('htmo-root');
    if (root1) { root1.innerHTML = controlsHTML(); wire(); load(); render(); }
  }
  var lastKey = '';
  setInterval(function () {
    load();
    var S = window.__htS; if (!S || W.live) return;
    var key = S.day + '|' + S.model + '|' + W.on + '|' + W.lvl + '|' + W.model + '|' + (W.wk ? 1 : 0) + '|' + (W.dq ? 1 : 0);
    if (key !== lastKey) { lastKey = key; render(); }
  }, 700);
})();
</script>
"""


def inject_block():
    return ("<script>\nwindow.__moMeta = " + json.dumps(MONTHLY_META, ensure_ascii=False, separators=(",", ":"))
            + ";\n</script>" + JS_BODY)


def patch_3d(s):
    # No edit to existing code: the weekly patcher (runs earlier in the
    # pipeline) already exposed the live helpers on window.
    return s


def patch_classic(s):
    if s.count(C_SEC_OLD) != 1:
        return None
    return s.replace(C_SEC_OLD, C_SEC_NEW, 1)


def patch_page(s):
    if MARKER in s:
        return s
    # 3D pages DEFINE window.HT3D = {...}; classic pages merely reference
    # window.HT3D once inside other patchers' payload sniffers, so a bare
    # substring test misclassifies them -- anchor on the assignment.
    is3d = re.search(r"window\.HT3D\s*=\s*\{", s) is not None
    out = patch_3d(s) if is3d else patch_classic(s)
    if out is None:
        return None
    if out.count("</body>") != 1:
        return None
    out = out.replace("</body>", inject_block() + "\n</body>", 1)
    if MARKER not in out or "__moMeta" not in out:
        return None
    return out


def main():
    pages = sorted(Path("stations").glob("*.html"))
    if not pages:
        print("no station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_new = n_skip = n_warn = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            n_skip += 1
            print(f"already patched: {p.name}")
            continue
        out = patch_page(s)
        if out is None:
            n_warn += 1
            print(f"WARNING: anchors not as expected, skipped: {p.name}")
            continue
        p.write_text(out, encoding="utf-8")
        n_new += 1
        print(f"patched: {p.name}")
    print(f"patch_monthly: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
