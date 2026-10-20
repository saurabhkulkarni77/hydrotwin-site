"""Yearly outlook for the DEV station pages (dev only).

Adds a "Yearly outlook — next 12 months, 30-day mean flow" panel/
section ALONGSIDE the untouched daily 7-day forecast, the weekly
outlook and the monthly outlook, with the same Flow & forecast panel
treatment as the daily panel (Saurabh's request, from his screenshot
of the daily panel on the St. Paul 3D page):

  data (fetched lazily, same sidecar pattern as monthly/):
    ../yearly/<site>.json  baked yearly forecasts for val+test issue
                           dates (all 10 models), per-station
                           9-feature standardization stats + yearly
                           tsd (live)
    ../dacpy/<site>.json   yearly DACP half-widths (log space) per
                           station x model x lead-month x level
                           + q_end
    ../onnx_y/<site>/*.onnx yearly neural models (live mode, 3D only)

  Panel contents (classic in-flow section before the Drift section;
  3D floating panel with own drag/collapse/maximize, third slot
  right of the monthly panel):
    * chart: observed context (4 monthly blocks) + selected model's
      forecast across the 12 leads + observed outcomes (dashed),
      log scale, DACP band with the panel's band toggle + level;
    * model selector with FULL model names (ht-fullforms);
    * lead stepper [◀ Lead] [▶ Play] [Lead ▶] with a per-lead
      readout line (period, forecast, DACP range, observed, error %)
      and a marker on the chart at the selected lead — Play steps
      through the 12 leads automatically;
    * the 12-row leads table and the pooled yearly leaderboard;
    * Δ Compare models is added by the sibling patcher
      build25/patch_compare_y.py (deploy step after this one).

  Live mode (3D only, mirroring the monthly panel): the "▶ Live
  yearly outlook" button assembles the current window via the page's
  htGapAssemble()/htBakedAssemble() + fetchLiveSoilSnow() (exposed on
  window by the earlier patchers, bounded by ht-livefix timeouts)
  and runs the selected yearly NEURAL model in-browser (ONNX,
  [1,29,9] -> [1,12]). Non-neural models and the pooled GCN are
  baked-dates only; the panel says so — no fake live.

  Stage/ft: no stage readout. The daily panel's stage inset converts
  daily flows through the station rating curve; a rating-curve stage
  of a 30-day MEAN flow is not an expected water level and is not
  shown (see the build audit).

  The daily forecast, weekly and monthly outlooks, DACP, stats,
  drift and UI code paths are not modified.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_yearly.py
"""
import json
import re
import sys
from pathlib import Path

MARKER = "ht-yearly v1"

# === YEARLY META (generated from the yearly build; do not hand-edit) ===
# leader: {model: pooled test RMSE (log)} incl. Climatology/Persistence refs
# st:     {site: {model: this-station test RMSE (log)}}
# sum:    {site: {model: {level: [test coverage, mean width cfs]}}}  (yearly DACP)
YEARLY_META = {"leader":{"PILSTMv1":0.5473,"LSTM":0.5674,"Transformer":0.5496,"TFT":0.5482,"GCN":0.5655,"GP RBF":0.5948,"GP Matérn":0.5978,"PatchTST":0.5669,"ARIMA":0.7112,"SARIMA":0.5341,"Climatology":0.5181,"Persistence":0.8134},"st":{"01463500":{"PILSTMv1":0.6555,"LSTM":0.6957,"Transformer":0.6574,"TFT":0.6511,"GCN":0.5889,"GP RBF":0.7385,"GP Matérn":0.7444,"PatchTST":0.6922,"ARIMA":0.7345,"SARIMA":0.7048,"Climatology":0.703,"Persistence":0.9723},"01646500":{"PILSTMv1":0.9419,"LSTM":0.9836,"Transformer":0.9813,"TFT":0.9564,"GCN":0.7745,"GP RBF":1.048,"GP Matérn":1.0596,"PatchTST":1.0338,"ARIMA":0.9613,"SARIMA":0.9339,"Climatology":0.9481,"Persistence":1.2655},"02320500":{"PILSTMv1":0.5395,"LSTM":0.5603,"Transformer":0.5534,"TFT":0.5916,"GCN":0.5897,"GP RBF":0.6181,"GP Matérn":0.6775,"PatchTST":0.7445,"ARIMA":0.7364,"SARIMA":0.7573,"Climatology":0.5002,"Persistence":0.7329},"05331000":{"PILSTMv1":0.6294,"LSTM":0.7242,"Transformer":0.5938,"TFT":0.5814,"GCN":0.6724,"GP RBF":0.6078,"GP Matérn":0.6184,"PatchTST":0.5408,"ARIMA":0.8495,"SARIMA":0.5929,"Climatology":0.5381,"Persistence":0.9618},"06214500":{"PILSTMv1":0.3857,"LSTM":0.4001,"Transformer":0.3804,"TFT":0.3969,"GCN":0.6134,"GP RBF":0.5019,"GP Matérn":0.4954,"PatchTST":0.3546,"ARIMA":0.6779,"SARIMA":0.2388,"Climatology":0.2978,"Persistence":1.051},"06934500":{"PILSTMv1":0.4075,"LSTM":0.4496,"Transformer":0.392,"TFT":0.3602,"GCN":0.4231,"GP RBF":0.4054,"GP Matérn":0.4093,"PatchTST":0.3684,"ARIMA":0.5358,"SARIMA":0.2812,"Climatology":0.3605,"Persistence":0.6141},"07374000":{"PILSTMv1":0.5004,"LSTM":0.5147,"Transformer":0.4896,"TFT":0.5119,"GCN":0.6241,"GP RBF":0.5329,"GP Matérn":0.5503,"PatchTST":0.5435,"ARIMA":1.1236,"SARIMA":0.5119,"Climatology":0.4505,"Persistence":0.9482},"08057000":{"PILSTMv1":0.8683,"LSTM":0.797,"Transformer":0.8131,"TFT":0.7866,"GCN":0.7315,"GP RBF":0.7983,"GP Matérn":0.8142,"PatchTST":0.8976,"ARIMA":0.7972,"SARIMA":0.7639,"Climatology":0.6294,"Persistence":1.1884},"08158000":{"PILSTMv1":0.7483,"LSTM":0.7839,"Transformer":0.7682,"TFT":0.7804,"GCN":0.7191,"GP RBF":0.9243,"GP Matérn":0.8641,"PatchTST":0.7063,"ARIMA":0.9879,"SARIMA":0.8533,"Climatology":0.6961,"Persistence":0.9938},"08313000":{"PILSTMv1":0.6196,"LSTM":0.6729,"Transformer":0.706,"TFT":0.7104,"GCN":0.6615,"GP RBF":0.6808,"GP Matérn":0.6657,"PatchTST":0.7059,"ARIMA":0.6511,"SARIMA":0.6179,"Climatology":0.7843,"Persistence":0.5578},"09380000":{"PILSTMv1":0.1826,"LSTM":0.1801,"Transformer":0.1741,"TFT":0.1829,"GCN":0.2009,"GP RBF":0.2018,"GP Matérn":0.2019,"PatchTST":0.1767,"ARIMA":0.1985,"SARIMA":0.1585,"Climatology":0.213,"Persistence":0.2072},"11447650":{"PILSTMv1":0.4679,"LSTM":0.4364,"Transformer":0.4618,"TFT":0.4513,"GCN":0.5652,"GP RBF":0.4802,"GP Matérn":0.4742,"PatchTST":0.43,"ARIMA":0.6828,"SARIMA":0.4324,"Climatology":0.3992,"Persistence":0.7172},"14105700":{"PILSTMv1":0.168,"LSTM":0.1781,"Transformer":0.174,"TFT":0.165,"GCN":0.1872,"GP RBF":0.1939,"GP Matérn":0.196,"PatchTST":0.1754,"ARIMA":0.3086,"SARIMA":0.0965,"Climatology":0.215,"Persistence":0.3639}},"sum":{"01463500":{"LSTM":{"70":[0.6947,18946.21],"80":[0.7924,20957.4],"90":[0.869,22589.12],"95":[0.8999,23295.03]},"Transformer":{"70":[0.7045,16313.99],"80":[0.7949,18321.16],"90":[0.8767,19754.67],"95":[0.9096,20489.16]},"TFT":{"70":[0.7009,16264.22],"80":[0.7937,18491.24],"90":[0.8761,20073.94],"95":[0.9109,20847.51]},"PatchTST":{"70":[0.6963,18129.93],"80":[0.7988,21170.38],"90":[0.8846,24087.85],"95":[0.9167,25924.49]},"PILSTMv1":{"70":[0.7121,16017.64],"80":[0.8037,17747.37],"90":[0.8846,18996.61],"95":[0.9158,19641.11]},"GCN":{"70":[0.7106,13827.13],"80":[0.7995,15641.8],"90":[0.873,17009.21],"95":[0.9026,17694.85]},"GP Matérn":{"70":[0.7128,21755.4],"80":[0.8086,24347.89],"90":[0.8874,26906.4],"95":[0.9164,28153.35]},"GP RBF":{"70":[0.7146,20983.99],"80":[0.8031,23377.06],"90":[0.8785,25473.22],"95":[0.9078,26613.33]},"ARIMA":{"70":[0.7115,20539.96],"80":[0.7811,22078.0],"90":[0.8419,23260.52],"95":[0.8706,23926.66]},"SARIMA":{"70":[0.6767,19938.29],"80":[0.7408,21712.38],"90":[0.8059,22765.44],"95":[0.837,23182.75]}},"01646500":{"LSTM":{"70":[0.6971,29692.06],"80":[0.7949,33113.25],"90":[0.8841,35930.71],"95":[0.9198,37578.86]},"Transformer":{"70":[0.6904,29473.19],"80":[0.7927,33300.14],"90":[0.8789,36589.47],"95":[0.9136,38532.67]},"TFT":{"70":[0.6916,29620.9],"80":[0.7968,33424.2],"90":[0.8832,36231.44],"95":[0.916,37568.71]},"PatchTST":{"70":[0.6757,32152.79],"80":[0.7858,36347.56],"90":[0.8782,40787.56],"95":[0.9129,43244.1]},"PILSTMv1":{"70":[0.7293,23550.12],"80":[0.8205,25781.22],"90":[0.8929,27548.14],"95":[0.9231,29000.7]},"GCN":{"70":[0.6985,16225.79],"80":[0.7968,18444.33],"90":[0.8794,19916.34],"95":[0.9124,20535.94]},"GP Matérn":{"70":[0.712,38871.25],"80":[0.8056,44854.84],"90":[0.8837,49050.93],"95":[0.9162,52662.13]},"GP RBF":{"70":[0.7096,37670.16],"80":[0.8013,42775.49],"90":[0.8803,46120.35],"95":[0.9131,48606.62]},"ARIMA":{"70":[0.7127,21784.13],"80":[0.8025,24297.72],"90":[0.8749,25779.53],"95":[0.9091,26685.21]},"SARIMA":{"70":[0.6441,26329.39],"80":[0.722,27389.2],"90":[0.7828,27945.31],"95":[0.8115,28387.63]}},"02320500":{"LSTM":{"70":[0.67,6463.97],"80":[0.772,7117.18],"90":[0.8495,7596.01],"95":[0.8825,7803.97]},"Transformer":{"70":[0.6746,6179.93],"80":[0.7827,6909.41],"90":[0.8678,7600.12],"95":[0.9023,7977.5]},"TFT":{"70":[0.6706,7392.9],"80":[0.7665,7965.0],"90":[0.8446,8414.1],"95":[0.8761,8587.67]},"PatchTST":{"70":[0.7021,13495.86],"80":[0.8013,14984.41],"90":[0.8761,16399.19],"95":[0.906,17023.58]},"PILSTMv1":{"70":[0.6871,5906.72],"80":[0.7891,6598.42],"90":[0.8645,7135.44],"95":[0.8984,7320.13]},"GCN":{"70":[0.6587,7271.29],"80":[0.7576,7793.52],"90":[0.841,8165.1],"95":[0.8755,8317.62]},"GP Matérn":{"70":[0.7012,10233.97],"80":[0.8059,11713.39],"90":[0.891,13096.56],"95":[0.9267,13749.08]},"GP RBF":{"70":[0.6795,8198.8],"80":[0.7875,9143.86],"90":[0.8779,10104.95],"95":[0.9124,10717.74]},"ARIMA":{"70":[0.6957,13061.77],"80":[0.7637,13701.55],"90":[0.8168,13980.13],"95":[0.8425,14089.0]},"SARIMA":{"70":[0.7241,13908.54],"80":[0.797,14698.32],"90":[0.8544,15017.62],"95":[0.8813,15178.74]}},"05331000":{"LSTM":{"70":[0.707,33336.85],"80":[0.8007,38179.35],"90":[0.8781,41508.59],"95":[0.9117,43234.55]},"Transformer":{"70":[0.7006,19982.69],"80":[0.7958,22867.34],"90":[0.8737,25248.31],"95":[0.9042,26458.34]},"TFT":{"70":[0.706,19785.96],"80":[0.802,22250.96],"90":[0.8794,24269.68],"95":[0.9076,25592.21]},"PatchTST":{"70":[0.7029,20210.51],"80":[0.7987,23182.39],"90":[0.8802,25388.83],"95":[0.9149,26652.94]},"PILSTMv1":{"70":[0.6954,21083.45],"80":[0.7899,23489.6],"90":[0.8678,25632.49],"95":[0.9006,26960.66]},"GCN":{"70":[0.7078,25126.14],"80":[0.7974,28058.35],"90":[0.8696,29907.82],"95":[0.9022,30645.19]},"GP Matérn":{"70":[0.7052,21645.54],"80":[0.8028,25217.18],"90":[0.883,28684.58],"95":[0.9172,30879.81]},"GP RBF":{"70":[0.7114,21418.49],"80":[0.808,24472.82],"90":[0.8872,27453.58],"95":[0.9185,29404.56]},"ARIMA":{"70":[0.69,35319.37],"80":[0.7821,39044.59],"90":[0.854,41770.39],"95":[0.8872,43500.81]},"SARIMA":{"70":[0.6887,17940.19],"80":[0.7648,18626.44],"90":[0.831,19150.2],"95":[0.8634,19670.98]}},"06214500":{"LSTM":{"70":[0.7063,6496.85],"80":[0.7991,7607.03],"90":[0.8858,8369.96],"95":[0.9219,8789.78]},"Transformer":{"70":[0.7011,5928.69],"80":[0.7958,6751.56],"90":[0.8763,7276.75],"95":[0.9119,7609.31]},"TFT":{"70":[0.7106,6593.42],"80":[0.8044,7827.81],"90":[0.8846,8825.18],"95":[0.9221,9314.17]},"PatchTST":{"70":[0.708,5918.3],"80":[0.8044,6723.72],"90":[0.8887,7509.85],"95":[0.9238,7990.7]},"PILSTMv1":{"70":[0.7037,4422.19],"80":[0.797,5045.57],"90":[0.8794,5495.05],"95":[0.9171,5768.23]},"GCN":{"70":[0.7265,8084.35],"80":[0.811,9199.03],"90":[0.8825,10030.94],"95":[0.916,10600.13]},"GP Matérn":{"70":[0.7175,7751.51],"80":[0.8096,9224.14],"90":[0.8913,10500.1],"95":[0.9266,11536.66]},"GP RBF":{"70":[0.7206,7563.69],"80":[0.8113,8931.53],"90":[0.8903,10187.46],"95":[0.9243,11055.96]},"ARIMA":{"70":[0.6902,9020.7],"80":[0.7749,9579.55],"90":[0.8466,9949.25],"95":[0.8784,10297.13]},"SARIMA":{"70":[0.6804,3105.19],"80":[0.7519,3304.18],"90":[0.8174,3437.74],"95":[0.8507,3538.36]}},"06934500":{"LSTM":{"70":[0.6973,77162.18],"80":[0.8025,92263.7],"90":[0.8868,104086.93],"95":[0.9188,111236.53]},"Transformer":{"70":[0.7056,63960.27],"80":[0.8056,73347.07],"90":[0.8901,81778.21],"95":[0.9193,85541.3]},"TFT":{"70":[0.6909,54479.19],"80":[0.7932,63705.82],"90":[0.882,70818.46],"95":[0.9193,75336.73]},"PatchTST":{"70":[0.7018,54682.57],"80":[0.8053,65266.37],"90":[0.8903,74000.28],"95":[0.9209,80919.31]},"PILSTMv1":{"70":[0.7018,64064.01],"80":[0.8058,75865.77],"90":[0.8908,84539.81],"95":[0.9257,89947.29]},"GCN":{"70":[0.712,65544.0],"80":[0.8065,75535.5],"90":[0.8851,85404.84],"95":[0.9176,90067.56]},"GP Matérn":{"70":[0.7004,65811.71],"80":[0.8001,75465.43],"90":[0.8844,86720.06],"95":[0.9174,91597.23]},"GP RBF":{"70":[0.7006,65115.97],"80":[0.8013,74670.04],"90":[0.8868,84327.36],"95":[0.9205,89655.3]},"ARIMA":{"70":[0.7004,85934.85],"80":[0.7844,93639.36],"90":[0.8613,98811.58],"95":[0.8936,102446.63]},"SARIMA":{"70":[0.6878,42126.77],"80":[0.7642,45665.9],"90":[0.8343,47678.69],"95":[0.8692,48770.79]}},"07374000":{"LSTM":{"70":[0.6963,615803.3],"80":[0.7909,668208.11],"90":[0.8666,700846.24],"95":[0.8956,716022.74]},"Transformer":{"70":[0.707,582355.74],"80":[0.8062,642115.29],"90":[0.8791,676942.17],"95":[0.9042,694278.55]},"TFT":{"70":[0.6908,638966.23],"80":[0.7879,681791.71],"90":[0.8538,716539.7],"95":[0.8791,732334.78]},"PatchTST":{"70":[0.7018,708575.6],"80":[0.8068,773830.26],"90":[0.8834,826975.15],"95":[0.9096,857556.87]},"PILSTMv1":{"70":[0.6984,597063.7],"80":[0.7961,645959.39],"90":[0.8739,682594.06],"95":[0.9023,697515.85]},"GCN":{"70":[0.7173,878934.33],"80":[0.8046,950162.35],"90":[0.8703,996104.58],"95":[0.8959,1019970.82]},"GP Matérn":{"70":[0.7036,682879.72],"80":[0.8065,762542.07],"90":[0.8907,855074.5],"95":[0.9228,897005.58]},"GP RBF":{"70":[0.703,650583.67],"80":[0.8056,725331.24],"90":[0.8935,791217.1],"95":[0.9252,832198.21]},"ARIMA":{"70":[0.6999,1345195.4],"80":[0.7781,1490673.4],"90":[0.8382,5212769.38],"95":[0.8666,11667390.45]},"SARIMA":{"70":[0.6358,621414.46],"80":[0.7167,663189.71],"90":[0.7729,680685.1],"95":[0.8049,687946.82]}},"08057000":{"LSTM":{"70":[0.7001,3197.0],"80":[0.7951,3705.05],"90":[0.8796,4075.75],"95":[0.9167,4291.97]},"Transformer":{"70":[0.7177,4456.43],"80":[0.8094,5344.31],"90":[0.8858,5892.76],"95":[0.9183,6203.86]},"TFT":{"70":[0.7061,3323.87],"80":[0.8027,3883.27],"90":[0.8822,4423.28],"95":[0.9169,4732.3]},"PatchTST":{"70":[0.7049,5286.84],"80":[0.8003,6637.11],"90":[0.8889,8132.44],"95":[0.9209,9585.55]},"PILSTMv1":{"70":[0.6966,3240.16],"80":[0.7906,3672.68],"90":[0.8716,3955.17],"95":[0.9076,4153.18]},"GCN":{"70":[0.6987,2719.14],"80":[0.7932,3170.61],"90":[0.8825,3521.69],"95":[0.9209,3695.37]},"GP Matérn":{"70":[0.7063,4184.59],"80":[0.8044,5151.76],"90":[0.8882,6156.25],"95":[0.9226,6829.19]},"GP RBF":{"70":[0.707,3972.92],"80":[0.8048,4864.75],"90":[0.8903,5696.87],"95":[0.9245,6381.05]},"ARIMA":{"70":[0.6923,3190.33],"80":[0.7728,3698.51],"90":[0.8509,3922.42],"95":[0.8887,4038.63]},"SARIMA":{"70":[0.6959,3009.85],"80":[0.7754,3553.25],"90":[0.8511,3781.75],"95":[0.8896,3918.21]}},"08158000":{"LSTM":{"70":[0.699,650.8],"80":[0.802,782.8],"90":[0.8981,930.74],"95":[0.938,1071.97]},"Transformer":{"70":[0.6759,553.4],"80":[0.7866,663.81],"90":[0.8792,765.62],"95":[0.9179,837.68]},"TFT":{"70":[0.6854,691.62],"80":[0.7908,859.72],"90":[0.8827,1017.95],"95":[0.9214,1096.46]},"PatchTST":{"70":[0.7058,582.6],"80":[0.8046,720.03],"90":[0.8972,876.65],"95":[0.9383,1034.48]},"PILSTMv1":{"70":[0.6959,539.29],"80":[0.7958,635.64],"90":[0.8901,734.61],"95":[0.9283,804.32]},"GCN":{"70":[0.7039,836.37],"80":[0.8034,949.55],"90":[0.8822,1037.92],"95":[0.9171,1082.86]},"GP Matérn":{"70":[0.694,970.43],"80":[0.7953,1234.92],"90":[0.8958,1616.62],"95":[0.9359,1923.6]},"GP RBF":{"70":[0.6906,1134.68],"80":[0.7949,1423.76],"90":[0.8941,1972.49],"95":[0.9349,2306.83]},"ARIMA":{"70":[0.6918,787.93],"80":[0.7642,865.86],"90":[0.8355,933.57],"95":[0.868,974.44]},"SARIMA":{"70":[0.7004,529.06],"80":[0.7604,567.26],"90":[0.8229,597.57],"95":[0.8514,621.57]}},"08313000":{"LSTM":{"70":[0.6997,1630.21],"80":[0.7904,1841.06],"90":[0.8706,1960.59],"95":[0.905,2020.52]},"Transformer":{"70":[0.6954,1722.88],"80":[0.787,1917.43],"90":[0.8663,2032.16],"95":[0.9015,2096.91]},"TFT":{"70":[0.6944,1730.06],"80":[0.7856,1975.08],"90":[0.8673,2108.26],"95":[0.9019,2176.5]},"PatchTST":{"70":[0.6942,1718.98],"80":[0.792,1958.48],"90":[0.8763,2146.53],"95":[0.9122,2234.45]},"PILSTMv1":{"70":[0.7009,1247.63],"80":[0.7887,1413.31],"90":[0.8682,1521.14],"95":[0.9029,1571.86]},"GCN":{"70":[0.6816,1449.37],"80":[0.7768,1572.24],"90":[0.8533,1659.14],"95":[0.8863,1696.23]},"GP Matérn":{"70":[0.6935,1384.46],"80":[0.7932,1622.39],"90":[0.8782,1841.24],"95":[0.9133,1940.63]},"GP RBF":{"70":[0.6904,1442.05],"80":[0.7939,1679.15],"90":[0.8806,1911.53],"95":[0.9164,2016.07]},"ARIMA":{"70":[0.6365,1373.65],"80":[0.6873,1453.23],"90":[0.7384,1504.72],"95":[0.764,1530.26]},"SARIMA":{"70":[0.6885,1442.61],"80":[0.7464,1518.81],"90":[0.816,1539.63],"95":[0.8483,1560.33]}},"09380000":{"LSTM":{"70":[0.6773,4030.11],"80":[0.7787,4343.36],"90":[0.8595,4608.48],"95":[0.8924,4760.47]},"Transformer":{"70":[0.6647,3619.86],"80":[0.7629,3905.42],"90":[0.8398,4142.71],"95":[0.8676,4264.47]},"TFT":{"70":[0.6715,3873.32],"80":[0.7749,4250.68],"90":[0.8669,4569.51],"95":[0.9031,4791.64]},"PatchTST":{"70":[0.6764,3654.42],"80":[0.7897,4164.4],"90":[0.8805,4720.27],"95":[0.9134,4998.24]},"PILSTMv1":{"70":[0.6919,4097.0],"80":[0.7907,4493.11],"90":[0.8692,4840.46],"95":[0.9005,5021.61]},"GCN":{"70":[0.6696,4694.6],"80":[0.7607,4991.49],"90":[0.8311,5184.16],"95":[0.8614,5283.43]},"GP Matérn":{"70":[0.6767,4351.75],"80":[0.7778,4811.69],"90":[0.864,5128.02],"95":[0.896,5314.52]},"GP RBF":{"70":[0.676,4290.14],"80":[0.7781,4684.14],"90":[0.8582,4985.62],"95":[0.8889,5150.37]},"ARIMA":{"70":[0.6796,4297.15],"80":[0.7687,4718.24],"90":[0.8437,4926.54],"95":[0.8802,5045.09]},"SARIMA":{"70":[0.6095,3328.01],"80":[0.6838,3435.14],"90":[0.7558,3503.89],"95":[0.7901,3563.35]}},"11447650":{"LSTM":{"70":[0.7063,21054.08],"80":[0.7963,24990.95],"90":[0.8735,27212.28],"95":[0.9112,28694.14]},"Transformer":{"70":[0.7016,24180.18],"80":[0.7984,28438.1],"90":[0.8827,30826.44],"95":[0.9212,32362.62]},"TFT":{"70":[0.7039,25166.02],"80":[0.802,29017.06],"90":[0.8858,32268.27],"95":[0.9217,33963.33]},"PatchTST":{"70":[0.7044,22495.69],"80":[0.8041,26433.83],"90":[0.8901,29656.76],"95":[0.9288,31460.04]},"PILSTMv1":{"70":[0.7092,21710.99],"80":[0.7999,25241.16],"90":[0.8732,27162.45],"95":[0.9067,28324.28]},"GCN":{"70":[0.721,24311.56],"80":[0.802,27012.19],"90":[0.8649,28814.03],"95":[0.8951,30267.5]},"GP Matérn":{"70":[0.7077,23419.93],"80":[0.8039,26955.98],"90":[0.8853,29895.32],"95":[0.9224,31803.65]},"GP RBF":{"70":[0.7106,23219.35],"80":[0.8044,26538.04],"90":[0.8853,29403.11],"95":[0.9221,31232.87]},"ARIMA":{"70":[0.7206,51265.09],"80":[0.7813,54737.35],"90":[0.8409,56947.36],"95":[0.8725,58543.5]},"SARIMA":{"70":[0.6918,28245.82],"80":[0.7721,30516.42],"90":[0.8381,31787.52],"95":[0.8704,32518.72]}},"14105700":{"LSTM":{"70":[0.7074,62817.81],"80":[0.8031,72536.06],"90":[0.8798,79208.56],"95":[0.9117,83082.16]},"Transformer":{"70":[0.7071,62489.08],"80":[0.7957,68857.73],"90":[0.8724,73128.87],"95":[0.9029,75903.58]},"TFT":{"70":[0.7048,57687.28],"80":[0.7995,65392.67],"90":[0.8807,72337.98],"95":[0.9133,75509.32]},"PatchTST":{"70":[0.7048,60439.95],"80":[0.8043,71808.2],"90":[0.8914,83194.75],"95":[0.9257,90899.57]},"PILSTMv1":{"70":[0.7005,57694.99],"80":[0.7964,65133.8],"90":[0.876,70300.12],"95":[0.9098,73284.99]},"GCN":{"70":[0.7069,62777.13],"80":[0.8005,71195.19],"90":[0.8871,77868.58],"95":[0.9236,80548.61]},"GP Matérn":{"70":[0.7169,67105.54],"80":[0.809,78288.36],"90":[0.8919,90199.4],"95":[0.9257,96465.28]},"GP RBF":{"70":[0.7121,65426.27],"80":[0.8067,77092.48],"90":[0.8914,88644.3],"95":[0.9257,94260.79]},"ARIMA":{"70":[0.6952,89202.42],"80":[0.7871,100010.6],"90":[0.8581,106900.5],"95":[0.8905,110400.35]},"SARIMA":{"70":[0.7069,30410.09],"80":[0.7843,35245.93],"90":[0.8455,36851.76],"95":[0.8764,37638.34]}}}}

# ------------------------- anchors: classic pages -------------------------
C_SEC_OLD = '<section class="hts-sec" id="hts-sec-drift">'
C_SEC_NEW = ('<section class="hts-sec" id="hts-sec-yearly">\n'
             '   <h2>Yearly outlook</h2>\n'
             '   <p>Outlook for the next 12 months (30-day mean flow) from the yearly models '
             '(alongside the daily 7-day forecast, the weekly outlook and the monthly outlook above).</p>\n'
             '   <div id="htyr-root"></div>\n'
             '  </section>\n  ' + C_SEC_OLD)

# ------------------------------ injected UI -------------------------------
JS_BODY = r"""
<script>
/* ht-yearly v1 - Yearly outlook: next 12 months of 30-day mean flow (dev).
 * Flow & forecast treatment like the daily panel: chart with DACP band,
 * model selector (full names), lead stepper + per-lead readout + Play,
 * leads table and pooled leaderboard. Baked forecasts + yearly DACP
 * half-widths ship as sidecars in ../yearly/<site>.json and
 * ../dacpy/<site>.json; live mode (3D pages) runs the yearly neural
 * ONNX models in ../onnx_y/<site>/. */
(function () {
  var NEURAL = ['LSTM', 'Transformer', 'TFT', 'PatchTST', 'PILSTMv1'];
  var FULL = {'ARIMA': 'Autoregressive Integrated Moving Average', 'SARIMA': 'Seasonal Autoregressive Integrated Moving Average', 'GP Matérn': 'Gaussian Process (Matérn kernel)', 'GP RBF': 'Gaussian Process (Radial Basis Function kernel)', 'LSTM': 'Long Short-Term Memory network', 'Transformer': 'Transformer (self-attention neural network)', 'TFT': 'Temporal Fusion Transformer', 'PatchTST': 'Patch Time-Series Transformer', 'GCN': 'Graph Convolutional Network', 'PILSTMv1': 'Physics-Informed LSTM, version 1'};
  var NL = 12;
  var META = window.__yrMeta || { leader: {}, st: {}, sum: {} };
  var W = { model: null, follow: true, on: true, lvl: 90, wk: null, dq: null,
            wkErr: false, dqErr: false, live: null, busy: false, touched: false,
            lead: 1, playing: false, timer: null };
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
    if (!W.wk && !W.wkErr && !W.wkBusy) {
      W.wkBusy = true;
      fetch('../yearly/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { W.wkBusy = false; W.wk = j; W.wk.idx = {}; j.dates.forEach(function (d, i) { W.wk.idx[d] = i; }); render(); })
        .catch(function () { W.wkBusy = false; W.wkErr = true; render(); setTimeout(function () { W.wkErr = false; }, 4000); });
    }
    if (!W.dq && !W.dqErr && !W.dqBusy) {
      W.dqBusy = true;
      fetch('../dacpy/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { W.dqBusy = false; W.dq = j; W.dq.idx = {}; j.dates.forEach(function (d, i) { W.dq.idx[d] = i; }); render(); })
        .catch(function () { W.dqBusy = false; W.dqErr = true; setTimeout(function () { W.dqErr = false; }, 4000); });
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
      return '<tr' + (n === sel ? ' class="htyr-sel"' : '') + '><td>' + n + (ref ? ' (reference)' : '') + '</td><td>' + L[n].toFixed(4) + '</td></tr>';
    }).join('');
    return '<div class="htyr-board"><div class="htyr-bt">Yearly outlook — next 12 months, 30-day mean flow · pooled test RMSE (log space), all 14 stations</div>'
      + '<table>' + rows + '</table></div>';
  }
  function draw(cv, ctx, fc, act, band, clim) {
    var g = cv.getContext('2d'); if (!g) return;
    var cw = cv.width, ch = cv.height;
    g.clearRect(0, 0, cw, ch);
    var vals = [];
    ctx.concat(fc, act, clim || []).forEach(function (p) { if (p[1] != null) vals.push(p[1]); });
    if (band) band.forEach(function (b) { if (b) { vals.push(b[0]); vals.push(b[1]); } });
    if (!vals.length) { g.fillStyle = '#9fb4c8'; g.font = '22px system-ui'; g.fillText('no yearly data for this date', 18, 40); return; }
    var lo = Math.floor(Math.log10(Math.min.apply(null, vals))), hi = Math.ceil(Math.log10(Math.max.apply(null, vals)));
    if (hi <= lo) hi = lo + 1;
    var X0 = 64, X1 = cw - 14, Y0 = 12, Y1 = ch - 30;
    function X(x) { return X0 + (x + 4.6) / 17.2 * (X1 - X0); }
    function Y(v) { var t = (Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo); return Y1 - t * (Y1 - Y0); }
    g.font = '19px system-ui'; g.textBaseline = 'middle';
    for (var e = lo; e <= hi; e++) {
      var yv = Math.pow(10, e), yy = Y(yv);
      g.strokeStyle = 'rgba(255,255,255,.13)'; g.beginPath(); g.moveTo(X0, yy); g.lineTo(X1, yy); g.stroke();
      g.fillStyle = '#9fb4c8'; g.fillText(fmt(yv), 6, yy);
    }
    g.strokeStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.moveTo(X(0), Y0); g.lineTo(X(0), Y1); g.stroke();
    g.fillStyle = '#9fb4c8';
    [-4, -2, 0, 3, 6, 9, 12].forEach(function (x) { g.fillText(x === 0 ? 'issue' : (x > 0 ? '+' + x + 'mo' : x + 'mo'), X(x) - 10, Y1 + 15); });
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
    if (clim && clim.length) line(clim, '#FFAA3C', 2, [3, 4]);
    var fcLine = fc.slice(); if (lastC && lastC[1] != null) fcLine = [[0, lastC[1]]].concat(fcLine);
    line(fcLine, '#4CC9F0', 2.5);
    g.fillStyle = '#4CC9F0'; g.fillText('— forecast', X(1.4), Y0 + 10);
    g.fillStyle = '#9fb4c8'; g.fillText('— observed 30-day mean', X(-4.4), Y0 + 10);
    if (act.length) { g.fillStyle = '#fff'; g.fillText('- - actual outcome', X(7.2), Y0 + 10); }
    if (clim && clim.length) { g.fillStyle = '#FFAA3C'; g.fillText('- - climatology (reference)', X(6.4), Y0 + 30); }
    var lp = null;
    fc.forEach(function (p) { if (p[0] === W.lead) lp = p; });
    if (lp && lp[1] != null) {
      g.save();
      g.strokeStyle = '#FFD24D'; g.lineWidth = 2; g.setLineDash([6, 5]);
      g.beginPath(); g.moveTo(X(lp[0]), Y0); g.lineTo(X(lp[0]), Y1); g.stroke();
      g.setLineDash([]);
      g.fillStyle = '#FFD24D'; g.beginPath(); g.arc(X(lp[0]), Y(lp[1]), 6, 0, 7); g.fill();
      g.font = '700 19px system-ui'; g.fillText('Mo ' + lp[0], X(lp[0]) + 10, Math.max(Y0 + 10, Y(lp[1]) - 16));
      g.restore();
    }
  }
  function stationLine(P, model) {
    var st = ((META.st || {})[P.site] || {})[model];
    var sum = (((META.sum || {})[P.site] || {})[model] || {})[String(W.lvl)];
    var out = '';
    if (st != null) out += 'This station · ' + model + ' yearly test RMSE ' + st.toFixed(4);
    if (W.on && sum) out += (out ? ' · ' : '') + 'DACP ' + W.lvl + '% test coverage ' + sum[0].toFixed(2) + ' · mean width ' + fmt(sum[1]) + ' cfs';
    return out;
  }
  function leadReadout(rows) {
    var el = $('htyr-leadread'); if (!el) return;
    var lab = $('htyr-leadlab'); if (lab) lab.textContent = 'Lead: Mo ' + W.lead + ' of ' + NL;
    var r = rows[W.lead - 1];
    if (!r) { el.textContent = rows.length ? '' : 'no forecast to inspect for this date'; return; }
    var txt = 'Mo ' + r[0] + ' · ' + r[1] + ' – ' + r[2] + ' · forecast ' + fmt(r[3]) + ' cfs';
    if (r[6] != null) txt += ' · climatology ' + fmt(r[6]) + ' cfs';
    if (r[4]) txt += ' · ' + W.lvl + '% DACP ' + fmt(r[4][0]) + ' – ' + fmt(r[4][1]) + ' cfs';
    if (r[5] != null && r[3] != null) {
      var err = (r[3] - r[5]) / r[5] * 100;
      txt += ' · observed ' + fmt(r[5]) + ' cfs · error ' + (err >= 0 ? '+' : '') + err.toFixed(1) + '%';
    } else if (r[5] != null) {
      txt += ' · observed ' + fmt(r[5]) + ' cfs';
    } else {
      txt += ' · observed — (30-day outcome not fully in the record for this date)';
    }
    el.textContent = txt;
    var trs = document.querySelectorAll('#htyr-read table.htyr-t tr');
    for (var i = 0; i < trs.length; i++) trs[i].classList.toggle('htyr-hl', i === W.lead);
  }
  /* Climatology reference, computed from the page payload with the exact
   * evaluated-baseline definition (baselines_yearly.py): ln(30-day block
   * mean) by block-start day-of-year over blocks starting <= 2023-09-30,
   * circular-smoothed +/-7 d weighted by counts. Same reference whose
   * pooled RMSE sits in the leaderboard below — drawn so users can see
   * each model cross it (monthly skill crosses climatology at Mo 4). */
  function climTable(P) {
    if (W.climTab) return W.climTab;
    var flow = P.flow, n = flow.length;
    var startMs = Date.parse(P.start + 'T00:00:00Z');
    var trainEnd = Date.parse('2023-09-30T00:00:00Z');
    function doyOf(idx) { var ms = startMs + idx * 864e5; var d = new Date(ms); return Math.round((ms - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5) + 1; }
    var sums = [], cnts = [], d2;
    for (d2 = 1; d2 <= 366; d2++) { sums[d2] = 0; cnts[d2] = 0; }
    for (var s = 0; s + 29 < n; s++) {
      if (startMs + s * 864e5 > trainEnd) break;
      var m = 0, ok = true;
      for (var j = 0; j < 30; j++) { var v = flow[s + j]; if (v == null || !isFinite(v) || v <= 0) { ok = false; break; } m += v; }
      if (!ok) continue;
      var dy = doyOf(s);
      sums[dy] += Math.log(m / 30); cnts[dy] += 1;
    }
    var raw = [], gsum = 0, gcnt = 0;
    for (d2 = 1; d2 <= 366; d2++) { raw[d2] = cnts[d2] > 0 ? sums[d2] / cnts[d2] : NaN; if (cnts[d2] > 0) { gsum += raw[d2]; gcnt++; } }
    var gmean = gcnt ? gsum / gcnt : NaN;
    var sm = [];
    for (var i = 0; i < 366; i++) {
      var num = 0, den = 0;
      for (var o = -7; o <= 7; o++) { var ix = ((i + o) % 366 + 366) % 366 + 1; if (isFinite(raw[ix]) && cnts[ix] > 0) { num += raw[ix] * cnts[ix]; den += cnts[ix]; } }
      sm[i + 1] = den > 0 ? num / den : gmean;
    }
    W.climTab = { sm: sm, doyOf: doyOf };
    return W.climTab;
  }
  function climSeries(P, day) {
    var T = climTable(P); if (!T) return null;
    var out = [];
    for (var k = 0; k < NL; k++) { var v = T.sm[T.doyOf(day + 1 + 30 * k)]; out.push(v == null || !isFinite(v) ? null : Math.exp(v)); }
    return out;
  }
  function render() {
    var root = $('htyr-root'); if (!root) return;
    var P = pay(), S = window.__htS;
    if (!P) { root.innerHTML = '<div class="htyr-note">yearly outlook unavailable</div>'; return; }
    if (W.wkErr) { var re1 = $('htyr-read'); if (re1) re1.innerHTML = '<div class="htyr-note">yearly forecasts unavailable (sidecar missing)</div>'; else root.innerHTML = '<div class="htyr-note">yearly forecasts unavailable (sidecar missing)</div>'; return; }
    if (!W.wk) { if (!$('htyr-canvas')) root.innerHTML = '<div class="htyr-note">loading yearly outlook…</div>'; load(); return; }
    var model = curModel();
    if (!model || W.wk.models.indexOf(model) < 0) model = W.wk.models[0];
    var sel = $('htyr-model');
    if (sel && sel.value !== model && !W.touched) sel.value = model;
    if (sel && W.touched) model = sel.value;
    W.model = model;
    var issueEl = $('htyr-issue'), readEl = $('htyr-read'), cv = $('htyr-canvas');
    var ctx = [], fc = [], act = [], band = null, issueTxt = '', rows = [], clim = [];
    if (W.live) {
      var L = W.live;
      ctx = L.ctx; fc = L.preds.map(function (v, k) { return [k + 1, v]; });
      if (W.on && L.q) band = L.preds.map(function (v, k) { return L.q[k] == null ? null : [v * Math.exp(-L.q[k]), v * Math.exp(L.q[k])]; });
      issueTxt = 'LIVE outlook · issued ' + L.issue + ' (window ends ' + L.issue + ') · ' + model + ' run in-browser';
      var lday = Math.round((Date.parse(L.issue + 'T00:00:00Z') - Date.parse(P.start + 'T00:00:00Z')) / 864e5);
      var lclim = isFinite(lday) ? climSeries(P, lday) : null;
      if (lclim) clim = lclim.map(function (v, k) { return [k + 1, v]; });
      rows = L.preds.map(function (v, k) { return [k + 1, addDays(L.issue, 30 * k + 1), addDays(L.issue, 30 * k + 30), v, band ? band[k] : null, null, lclim ? lclim[k] : null]; });
    } else {
      if (!S) { issueEl.textContent = '…'; return; }
      var day = S.day, issue = isoOf(P, day);
      for (var j = 4; j >= 1; j--) ctx.push([-j, blockMean(P.flow, day - 30 * (j - 1))]);
      for (var k2 = 1; k2 <= NL; k2++) { var am = blockMean(P.flow, day + 30 * k2); if (am != null) act.push([k2, am]); }
      var di = W.wk.idx[issue];
      var preds = (di != null) ? W.wk.predw[model][di] : null;
      issueTxt = 'Issue date ' + issue + ' · ' + model + (preds ? '' : ' · no baked yearly forecast for this date — yearly outlook covers ' + W.wk.dates[0] + ' … ' + W.wk.dates[W.wk.dates.length - 1] + '. Pick a date in that range.');
      if (preds) {
        fc = preds.map(function (v, k) { return [k + 1, v]; });
        var climP = climSeries(P, day);
        if (climP) clim = climP.map(function (v, k) { return [k + 1, v]; });
        var qi = (W.on && W.dq) ? W.dq.idx[issue] : null;
        if (qi != null && W.dq.q[model]) {
          var ql = W.dq.q[model][String(W.lvl)];
          if (ql) band = preds.map(function (v, k) { var q = ql[k][qi]; return (q == null || v == null) ? null : [v * Math.exp(-q), v * Math.exp(q)]; });
        }
        rows = preds.map(function (v, k) {
          var a = blockMean(P.flow, day + 30 * (k + 1));
          return [k + 1, addDays(issue, 30 * k + 1), addDays(issue, 30 * k + 30), v, band ? band[k] : null, a, climP ? climP[k] : null];
        });
      }
    }
    if (issueEl) issueEl.textContent = issueTxt;
    if (cv) draw(cv, ctx, fc, act, band, clim);
    leadReadout(rows);
    if (readEl) {
      var html = '';
      var showClim = rows.some(function (r) { return r[6] != null; });
      if (rows.length) {
        html += '<table class="htyr-t"><tr><th>Mo</th><th>Month (30 d)</th><th>Forecast</th>' + (showClim ? '<th>Climatology</th>' : '') + (band ? '<th>' + W.lvl + '% DACP</th>' : '') + '<th>Observed</th></tr>';
        rows.forEach(function (r) {
          html += '<tr><td>' + r[0] + '</td><td>' + r[1].slice(5) + ' – ' + r[2].slice(5) + '</td><td>' + fmt(r[3]) + '</td>'
            + (showClim ? '<td>' + fmt(r[6]) + '</td>' : '')
            + (band ? '<td>' + (r[4] ? fmt(r[4][0]) + ' – ' + fmt(r[4][1]) : '–') + '</td>' : '')
            + '<td>' + fmt(r[5]) + '</td></tr>';
        });
        html += '</table><div class="htyr-note">cfs, 30-day mean flow' + (showClim ? ' · Climatology = train-era (to Sep 2023) mean for the same calendar block, ±7 d smoothed — the reference each model should beat' : '') + '</div>';
      }
      if (!W.live && !preds) {
        html += '<div class="htyr-note">No baked yearly forecast for ' + issue + ' — yearly outlook covers ' + W.wk.dates[0] + ' … ' + W.wk.dates[W.wk.dates.length - 1] + '. Pick a date in that range. (The ▶ Live button can still run the neural models for the newest data.)</div>';
      }
      var sl = stationLine(P, model);
      if (sl) html += '<div class="htyr-note">' + sl + '</div>';
      html += boardHTML(model);
      readEl.innerHTML = html;
      leadReadout(rows);
    }
  }
  async function runLive() {
    var P = pay(); if (!P) return;
    var model = W.model || curModel();
    var st = $('htyr-status');
    function say(t) { if (st) st.textContent = t; }
    if (!window.htGapAssemble || !window.fetchLiveSoilSnow) { say('live assembly unavailable on this page'); return; }
    if (NEURAL.indexOf(model) < 0) { say('Live yearly outlook runs the neural models in-browser (LSTM, Transformer, TFT, PatchTST, PILSTMv1). ' + model + ' is baked-dates only.'); return; }
    if (!W.wk) { say('yearly data still loading…'); load(); return; }
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
      var url = '../onnx_y/' + P.site + '/' + model + '.onnx';
      var sess = await ort.InferenceSession.create(url);
      var feeds = {}; feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
      var out = await sess.run(feeds);
      var diffs = Array.from(out[sess.outputNames[0]].data);
      if (diffs.length !== NL || diffs.some(function (v) { return !isFinite(v); })) throw new Error('bad model output');
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
      var bx = $('htyr-back'); if (bx) bx.style.display = '';
      render();
    } catch (e) {
      say('live yearly failed: ' + (e && e.message ? e.message : e));
    }
    W.busy = false;
  }
  function stopPlay() {
    W.playing = false;
    if (W.timer) { clearInterval(W.timer); W.timer = null; }
    var b = $('htyr-play'); if (b) b.textContent = '▶ Play';
  }
  function controlsHTML() {
    var P = pay();
    var opts = (W.wk ? W.wk.models : (P ? P.models : [])).map(function (m) { return '<option value="' + m + '">' + (FULL[m] ? m + ' — ' + FULL[m] : m) + '</option>'; }).join('');
    return '<div class="htyr-ctl">'
      + '<label>model <select id="htyr-model">' + opts + '</select></label>'
      + '<label style="cursor:pointer"><input type="checkbox" id="htyr-on" checked> DACP band</label>'
      + '<label>level <select id="htyr-lvl"><option value="70">70%</option><option value="80">80%</option><option value="90" selected>90%</option><option value="95">95%</option></select></label>'
      + (is3d ? '<button type="button" id="htyr-live">▶ Live yearly outlook</button><button type="button" id="htyr-back" style="display:none">↩ selected date</button>' : '')
      + '</div>'
      + '<div id="htyr-issue" class="htyr-issue"></div>'
      + '<canvas id="htyr-canvas" width="760" height="380"></canvas>'
      + '<div class="htyr-ff">'
      + '<div class="htyr-ffctl"><button type="button" id="htyr-prev">◀ Lead</button>'
      + '<button type="button" id="htyr-play">▶ Play</button>'
      + '<button type="button" id="htyr-next">Lead ▶</button>'
      + '<span class="htyr-leadlab" id="htyr-leadlab"></span></div>'
      + '<div class="htyr-leadread" id="htyr-leadread"></div></div>'
      + '<div id="htyr-read"></div>'
      + (is3d ? '<div id="htyr-status" class="htyr-note"></div>' : '');
  }
  function wire() {
    var m = $('htyr-model');
    if (m) m.addEventListener('change', function () { W.touched = true; W.follow = false; W.model = this.value; render(); });
    var on = $('htyr-on');
    if (on) on.addEventListener('change', function () { W.on = this.checked; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lv = $('htyr-lvl');
    if (lv) lv.addEventListener('change', function () { W.lvl = +this.value; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lb = $('htyr-live');
    if (lb) lb.addEventListener('click', runLive);
    var bb = $('htyr-back');
    if (bb) bb.addEventListener('click', function () { W.live = null; bb.style.display = 'none'; var st = $('htyr-status'); if (st) st.textContent = ''; render(); });
    var pv = $('htyr-prev');
    if (pv) pv.addEventListener('click', function () { stopPlay(); W.lead = Math.max(1, W.lead - 1); render(); });
    var nx = $('htyr-next');
    if (nx) nx.addEventListener('click', function () { stopPlay(); W.lead = Math.min(NL, W.lead + 1); render(); });
    var pl = $('htyr-play');
    if (pl) pl.addEventListener('click', function () {
      if (W.playing) { stopPlay(); render(); return; }
      if (W.lead >= NL) W.lead = 1;
      W.playing = true; this.textContent = '❚❚ Pause'; render();
      W.timer = setInterval(function () {
        if (W.lead >= NL) { stopPlay(); render(); return; }
        W.lead += 1; render();
        if (W.lead >= NL) stopPlay();
      }, 1100);
    });
  }
  var css = '.htyr-ctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0}'
    + '.htyr-ctl select,.htyr-ctl button{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:3px 6px;cursor:pointer}'
    + '.htyr-issue{font-weight:600;color:#BFD0E0;margin:2px 0 4px}'
    + '#htyr-canvas{width:100%;height:auto;display:block;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.12);border-radius:8px}'
    + '.htyr-t{border-collapse:collapse;width:100%;font-size:12px;margin-top:6px}'
    + '.htyr-t th,.htyr-t td{border-bottom:1px solid rgba(255,255,255,.12);padding:2px 6px;text-align:right}'
    + '.htyr-t th:first-child,.htyr-t td:first-child,.htyr-t td:nth-child(2){text-align:left}'
    + '.htyr-t tr.htyr-hl td{background:rgba(255,210,77,.14);color:#FFD24D;font-weight:700}'
    + '.htyr-note{opacity:.85;font-size:12px;margin-top:6px}'
    + '.htyr-board{margin-top:10px}.htyr-bt{font-weight:700;color:#8FC1F2;font-size:12.5px;margin-bottom:4px}'
    + '.htyr-board table{border-collapse:collapse;font-size:12px}'
    + '.htyr-board td{padding:1px 10px 1px 0}'
    + '.htyr-board tr.htyr-sel td{color:#4CC9F0;font-weight:700}'
    + '.htyr-ff{margin:8px 0 2px;border:1px solid rgba(255,255,255,.16);border-radius:8px;padding:8px 10px;background:rgba(255,255,255,.03)}'
    + '.htyr-ffctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap}'
    + '.htyr-ffctl button{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:3px 8px;cursor:pointer}'
    + '.htyr-leadlab{font-weight:600;color:#BFD0E0;font-size:12px}'
    + '.htyr-leadread{font-size:12.5px;color:#e8eef5;margin-top:6px}'
    + '#htyr-panel{position:fixed;left:918px;bottom:76px;z-index:9996;width:440px;max-width:94vw;background:rgba(12,18,28,.94);color:#e8eef5;border:1px solid rgba(255,255,255,.16);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.45);font:12.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}'
    + '#htyr-panel .htyr-head{display:flex;justify-content:space-between;align-items:center;background:rgba(12,18,28,.9);color:#BFD0E0;font-weight:700;padding:6px 8px 6px 12px;border-radius:12px 12px 0 0;cursor:move;user-select:none;-webkit-user-select:none}'
    + '#htyr-panel .htyr-head button{background:rgba(35,70,110,.9);border:1px solid rgba(255,255,255,.35);color:#E6EDF5;border-radius:6px;min-width:24px;height:24px;padding:0 6px;cursor:pointer;font:600 13px/1 Arial}'
    + '#htyr-panel .htyr-body{padding:8px 12px 12px;max-height:66vh;overflow:auto}'
    + '#htyr-panel.htyr-max{left:10px !important;top:10px !important;bottom:auto !important;width:calc(100vw - 20px) !important;max-width:none !important}'
    + '#htyr-panel.htyr-max .htyr-body{max-height:calc(100vh - 90px)}'
    + '#htyr-panel .htyr-dev{background:#d9930d;color:#111;border-radius:4px;padding:0 5px;font-size:10px;vertical-align:1px;margin-left:6px}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);
  if (is3d) {
    var panel = document.createElement('div'); panel.id = 'htyr-panel';
    panel.innerHTML = '<div class="htyr-head" id="htyr-head"><span>Yearly outlook<span class="htyr-dev">DEV</span></span>'
      + '<span><button type="button" id="htyr-max" aria-label="maximize">⛶</button> <button type="button" id="htyr-min" aria-label="collapse">–</button></span></div>'
      + '<div class="htyr-body" id="htyr-body"><div id="htyr-root"></div></div>';
    document.body.appendChild(panel);
    var root0 = $('htyr-root'); root0.innerHTML = controlsHTML();
    wire(); load(); render();
    var head = $('htyr-head'), dragging = null;
    head.addEventListener('mousedown', function (ev) {
      if (ev.target.closest('button')) return;
      var r = panel.getBoundingClientRect();
      dragging = { dx: ev.clientX - r.left, dy: ev.clientY - r.top };
      panel.style.left = r.left + 'px'; panel.style.top = r.top + 'px'; panel.style.bottom = 'auto';
      ev.preventDefault();
    });
    document.addEventListener('mousemove', function (ev) {
      if (!dragging) return;
      var nx2 = Math.max(0, Math.min(window.innerWidth - 80, ev.clientX - dragging.dx));
      var ny2 = Math.max(0, Math.min(window.innerHeight - 40, ev.clientY - dragging.dy));
      panel.style.left = nx2 + 'px'; panel.style.top = ny2 + 'px';
    });
    document.addEventListener('mouseup', function () { dragging = null; });
    $('htyr-min').addEventListener('click', function () {
      var b = $('htyr-body'); var hid = b.style.display === 'none';
      b.style.display = hid ? '' : 'none'; this.textContent = hid ? '–' : '+';
    });
    $('htyr-max').addEventListener('click', function () { panel.classList.toggle('htyr-max'); });
  } else {
    var root1 = $('htyr-root');
    if (root1) { root1.innerHTML = controlsHTML(); wire(); load(); render(); }
  }
  var lastKey = '';
  setInterval(function () {
    load();
    var S = window.__htS; if (!S || W.live) return;
    var key = S.day + '|' + S.model + '|' + W.on + '|' + W.lvl + '|' + W.model + '|' + W.lead + '|' + (W.wk ? 1 : 0) + '|' + (W.dq ? 1 : 0);
    if (key !== lastKey) { lastKey = key; render(); }
  }, 700);
})();
</script>
"""


def inject_block():
    return ("<script>\nwindow.__yrMeta = " + json.dumps(YEARLY_META, ensure_ascii=False, separators=(",", ":"))
            + ";\n</script>" + JS_BODY)


def patch_3d(s):
    # No edit to existing code: the earlier patchers already exposed the
    # live helpers on window and ht-livefix bounds them.
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
    if MARKER not in out or "__yrMeta" not in out:
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
    print(f"patch_yearly: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
