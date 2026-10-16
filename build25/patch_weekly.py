#!/usr/bin/env python3
"""Weekly outlook for the DEV station pages (dev only).

Adds a "Weekly outlook — 12 weeks, weekly mean flow" panel/section
ALONGSIDE the untouched daily 7-day forecast:

  data (fetched lazily, same sidecar pattern as dacp//params/):
    ../weekly/<site>.json  baked weekly forecasts for val+test issue
                           dates (all 10 models), per-station 9-feature
                           standardization stats + weekly tsd (for live)
    ../dacpw/<site>.json   weekly DACP half-widths (log space) per
                           station x model x lead-week x level + q_end
    ../onnx_w/<site>/*.onnx weekly neural models (live mode, 3D only)

  3D pages (window.HT3D): floating panel (own drag/collapse/maximize,
    ht-uiux does not manage it) with chart, model selector, DACP band
    toggle + level selector, per-week readout and the pooled weekly
    leaderboard; a Live button assembles the current window via the
    page's htGapAssemble()/htBakedAssemble() + fetchLiveSoilSnow()
    (exposed on window by a guarded hook below) and runs the selected
    weekly NEURAL model in-browser (ONNX). Non-neural models and the
    pooled GCN are baked-dates only; the panel says so — no fake live.
  classic pages (window.HT_DATA): static in-flow <section> before the
    Drift section, same chart/readout/leaderboard, no drag, no live.

  The daily forecast, DACP, stats, drift and UI code paths are not
  modified; the only edit to existing code is the guarded window
  exposure of the three live helpers on 3D pages.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_weekly.py
"""
import json
import re
import sys
from pathlib import Path

MARKER = "ht-weekly v1"

# === WEEKLY META (generated from the weekly build; do not hand-edit) ===
# leader: {model: pooled test RMSE (log)} incl. Climatology/Persistence refs
# st:     {site: {model: this-station test RMSE (log)}}
# sum:    {site: {model: {level: [test coverage, mean width cfs]}}}  (weekly DACP)
WEEKLY_META = {"leader":{"PILSTMv1":0.4987,"LSTM":0.5124,"Transformer":0.4857,"TFT":0.5027,"GCN":0.5239,"GP RBF":0.5363,"GP Matérn":0.5439,"PatchTST":0.5169,"ARIMA":0.626,"SARIMA":0.544,"Climatology":0.578,"Persistence":0.6728},"st":{"01463500":{"PILSTMv1":0.5743,"LSTM":0.6568,"Transformer":0.6061,"TFT":0.7269,"GCN":0.5498,"GP RBF":0.5923,"GP Matérn":0.5924,"PatchTST":0.6411,"ARIMA":0.7677,"SARIMA":0.7409,"Climatology":0.7106,"Persistence":0.7913},"01646500":{"PILSTMv1":0.8237,"LSTM":0.907,"Transformer":0.8582,"TFT":0.8477,"GCN":0.7557,"GP RBF":0.8496,"GP Matérn":0.8527,"PatchTST":0.9661,"ARIMA":0.85,"SARIMA":0.828,"Climatology":0.9631,"Persistence":1.0163},"02320500":{"PILSTMv1":0.3544,"LSTM":0.4237,"Transformer":0.4445,"TFT":0.4531,"GCN":0.3606,"GP RBF":0.4521,"GP Matérn":0.5461,"PatchTST":0.4637,"ARIMA":0.3641,"SARIMA":0.3458,"Climatology":0.6334,"Persistence":0.3641},"03294500":{"PILSTMv1":0.5657,"LSTM":0.5663,"Transformer":0.5391,"TFT":0.5347,"GCN":0.7067,"GP RBF":0.583,"GP Matérn":0.5927,"PatchTST":0.5544,"ARIMA":0.7289,"SARIMA":0.6337,"Climatology":0.5851,"Persistence":0.9726},"05331000":{"PILSTMv1":0.4644,"LSTM":0.4744,"Transformer":0.4629,"TFT":0.4741,"GCN":0.5398,"GP RBF":0.5052,"GP Matérn":0.5167,"PatchTST":0.4862,"ARIMA":0.5715,"SARIMA":0.4627,"Climatology":0.5307,"Persistence":0.5747},"06214500":{"PILSTMv1":0.3041,"LSTM":0.2822,"Transformer":0.2991,"TFT":0.293,"GCN":0.6371,"GP RBF":0.5439,"GP Matérn":0.527,"PatchTST":0.3186,"ARIMA":0.6816,"SARIMA":0.2782,"Climatology":0.3269,"Persistence":0.8408},"06934500":{"PILSTMv1":0.4952,"LSTM":0.467,"Transformer":0.3607,"TFT":0.4637,"GCN":0.4768,"GP RBF":0.4538,"GP Matérn":0.4575,"PatchTST":0.3836,"ARIMA":0.4813,"SARIMA":0.4405,"Climatology":0.3998,"Persistence":0.5651},"07374000":{"PILSTMv1":0.3427,"LSTM":0.3592,"Transformer":0.3029,"TFT":0.2956,"GCN":0.2996,"GP RBF":0.3195,"GP Matérn":0.3289,"PatchTST":0.3141,"ARIMA":0.4213,"SARIMA":0.3674,"Climatology":0.4804,"Persistence":0.5001},"08057000":{"PILSTMv1":0.9363,"LSTM":0.9298,"Transformer":0.9338,"TFT":0.9162,"GCN":0.8976,"GP RBF":0.9477,"GP Matérn":0.9558,"PatchTST":1.0207,"ARIMA":1.2376,"SARIMA":0.9322,"Climatology":0.8253,"Persistence":1.2643},"08158000":{"PILSTMv1":0.7959,"LSTM":0.782,"Transformer":0.679,"TFT":0.792,"GCN":0.6929,"GP RBF":0.8172,"GP Matérn":0.7962,"PatchTST":0.7944,"ARIMA":0.8405,"SARIMA":0.822,"Climatology":0.8189,"Persistence":0.8405},"08313000":{"PILSTMv1":0.4964,"LSTM":0.5109,"Transformer":0.4999,"TFT":0.4857,"GCN":0.5125,"GP RBF":0.5713,"GP Matérn":0.5657,"PatchTST":0.4774,"ARIMA":0.6475,"SARIMA":0.6516,"Climatology":0.8695,"Persistence":0.5257},"09380000":{"PILSTMv1":0.1363,"LSTM":0.1474,"Transformer":0.1299,"TFT":0.1195,"GCN":0.1821,"GP RBF":0.1861,"GP Matérn":0.1907,"PatchTST":0.1164,"ARIMA":0.1676,"SARIMA":0.1699,"Climatology":0.2301,"Persistence":0.16},"11447650":{"PILSTMv1":0.527,"LSTM":0.511,"Transformer":0.5205,"TFT":0.4785,"GCN":0.5662,"GP RBF":0.526,"GP Matérn":0.5255,"PatchTST":0.5351,"ARIMA":0.7291,"SARIMA":0.6676,"Climatology":0.4919,"Persistence":0.7283},"14105700":{"PILSTMv1":0.1651,"LSTM":0.1562,"Transformer":0.163,"TFT":0.1569,"GCN":0.1573,"GP RBF":0.1612,"GP Matérn":0.167,"PatchTST":0.1655,"ARIMA":0.2746,"SARIMA":0.2759,"Climatology":0.2269,"Persistence":0.2752}},"sum":{"01463500":{"LSTM":{"70":[0.7124,19204.58],"80":[0.8068,21945.2],"90":[0.895,24753.69],"95":[0.9314,26238.47]},"Transformer":{"70":[0.7095,15739.97],"80":[0.8045,18301.69],"90":[0.8896,20870.03],"95":[0.9252,22132.3]},"TFT":{"70":[0.7095,22930.64],"80":[0.8056,27051.21],"90":[0.8939,31270.76],"95":[0.9326,33431.06]},"PatchTST":{"70":[0.707,16819.66],"80":[0.8057,20286.19],"90":[0.8947,24377.48],"95":[0.934,26898.32]},"PILSTMv1":{"70":[0.7049,13196.27],"80":[0.8021,15759.91],"90":[0.8956,18295.52],"95":[0.9325,19482.32]},"GCN":{"70":[0.6964,12668.35],"80":[0.7993,15218.75],"90":[0.8893,17729.6],"95":[0.9236,18704.67]},"GP Matérn":{"70":[0.7052,14791.69],"80":[0.8028,17637.45],"90":[0.8927,20517.64],"95":[0.9277,22077.11]},"GP RBF":{"70":[0.7061,14780.34],"80":[0.8021,17719.25],"90":[0.8901,20318.79],"95":[0.9255,21869.76]},"ARIMA":{"70":[0.7307,20787.09],"80":[0.8171,22522.14],"90":[0.9026,24999.98],"95":[0.94,26450.73]},"SARIMA":{"70":[0.7385,21079.27],"80":[0.8206,23251.98],"90":[0.898,24815.11],"95":[0.9317,25895.33]}},"01646500":{"LSTM":{"70":[0.7174,22070.24],"80":[0.8114,25292.72],"90":[0.897,29374.28],"95":[0.9326,32120.46]},"Transformer":{"70":[0.7161,20516.83],"80":[0.8106,23468.99],"90":[0.8898,25935.31],"95":[0.9241,27049.79]},"TFT":{"70":[0.7131,19074.95],"80":[0.8075,22159.34],"90":[0.8911,25816.02],"95":[0.9266,27811.99]},"PatchTST":{"70":[0.7149,25696.67],"80":[0.8113,31213.92],"90":[0.8981,37500.01],"95":[0.9365,41039.61]},"PILSTMv1":{"70":[0.7144,15888.7],"80":[0.8086,18865.56],"90":[0.8959,22269.67],"95":[0.9338,24428.25]},"GCN":{"70":[0.7069,13133.68],"80":[0.8045,15897.43],"90":[0.8901,18187.26],"95":[0.9261,19472.87]},"GP Matérn":{"70":[0.7107,19779.72],"80":[0.8065,23536.79],"90":[0.8937,27346.42],"95":[0.9309,29513.23]},"GP RBF":{"70":[0.7149,19957.04],"80":[0.8087,23382.85],"90":[0.8923,26726.46],"95":[0.9276,28523.13]},"ARIMA":{"70":[0.7003,13708.11],"80":[0.7998,16502.81],"90":[0.8929,19489.18],"95":[0.9322,20894.49]},"SARIMA":{"70":[0.701,13490.44],"80":[0.8021,15869.81],"90":[0.8947,18184.78],"95":[0.9334,19697.15]}},"02320500":{"LSTM":{"70":[0.7004,4272.46],"80":[0.7983,4952.75],"90":[0.8872,5548.98],"95":[0.9256,5958.73]},"Transformer":{"70":[0.7037,4481.57],"80":[0.8012,5055.77],"90":[0.8862,5570.82],"95":[0.9238,5850.42]},"TFT":{"70":[0.7036,5163.67],"80":[0.8018,5904.95],"90":[0.8846,6521.37],"95":[0.9214,6841.6]},"PatchTST":{"70":[0.7087,5058.41],"80":[0.8043,5658.31],"90":[0.889,6262.02],"95":[0.9273,6525.19]},"PILSTMv1":{"70":[0.7002,3254.32],"80":[0.7981,3869.23],"90":[0.886,4429.86],"95":[0.9244,4753.79]},"GCN":{"70":[0.692,3288.94],"80":[0.7931,3731.92],"90":[0.8827,4150.23],"95":[0.9209,4356.3]},"GP Matérn":{"70":[0.7165,6994.16],"80":[0.8127,8238.15],"90":[0.8985,9842.97],"95":[0.9372,10668.1]},"GP RBF":{"70":[0.7036,5013.79],"80":[0.803,5861.2],"90":[0.8933,6773.53],"95":[0.9325,7303.45]},"ARIMA":{"70":[0.7072,4128.94],"80":[0.7939,4853.91],"90":[0.8857,5369.81],"95":[0.9296,5616.25]},"SARIMA":{"70":[0.7086,3855.72],"80":[0.8039,4518.38],"90":[0.8959,5138.27],"95":[0.9411,5370.75]}},"03294500":{"LSTM":{"70":[0.7203,208467.57],"80":[0.8152,255978.35],"90":[0.8978,305410.69],"95":[0.9319,328601.29]},"Transformer":{"70":[0.7178,212037.02],"80":[0.8134,262459.51],"90":[0.8982,303349.9],"95":[0.9333,318127.5]},"TFT":{"70":[0.7062,175357.4],"80":[0.8051,216603.4],"90":[0.8917,251461.7],"95":[0.9225,262668.62]},"PatchTST":{"70":[0.7159,204365.97],"80":[0.8101,255444.06],"90":[0.9011,309666.96],"95":[0.9391,336732.48]},"PILSTMv1":{"70":[0.7109,183214.52],"80":[0.8058,226966.95],"90":[0.8946,271089.71],"95":[0.9312,288951.89]},"GCN":{"70":[0.7174,320726.44],"80":[0.8163,403272.53],"90":[0.9029,497683.97],"95":[0.9399,530642.84]},"GP Matérn":{"70":[0.7058,212983.71],"80":[0.8065,264463.79],"90":[0.8986,332143.97],"95":[0.9344,350954.89]},"GP RBF":{"70":[0.7112,208065.8],"80":[0.8069,259445.9],"90":[0.8986,321082.75],"95":[0.9322,342022.43]},"ARIMA":{"70":[0.7178,203735.15],"80":[0.8076,275981.07],"90":[0.8786,320134.07],"95":[0.9105,330117.6]},"SARIMA":{"70":[0.7149,176838.45],"80":[0.8076,240434.98],"90":[0.8822,277953.53],"95":[0.9152,285610.67]}},"05331000":{"LSTM":{"70":[0.7019,14920.68],"80":[0.794,17267.6],"90":[0.8751,19070.62],"95":[0.9115,20232.88]},"Transformer":{"70":[0.7007,15501.84],"80":[0.7939,18087.67],"90":[0.8746,20213.83],"95":[0.9133,21453.62]},"TFT":{"70":[0.6962,14163.94],"80":[0.7882,16419.81],"90":[0.8704,18044.53],"95":[0.9072,19006.05]},"PatchTST":{"70":[0.6959,15570.65],"80":[0.7946,19304.29],"90":[0.882,22635.18],"95":[0.9179,24913.33]},"PILSTMv1":{"70":[0.7014,13861.88],"80":[0.7924,15912.48],"90":[0.8736,17487.58],"95":[0.9096,18478.33]},"GCN":{"70":[0.7121,17732.99],"80":[0.8035,20104.68],"90":[0.8795,21725.5],"95":[0.9161,22527.87]},"GP Matérn":{"70":[0.703,17340.47],"80":[0.7996,20730.95],"90":[0.8873,24349.73],"95":[0.9231,26457.51]},"GP RBF":{"70":[0.7035,16740.24],"80":[0.7991,19823.05],"90":[0.8855,22837.07],"95":[0.9218,24417.05]},"ARIMA":{"70":[0.7033,21723.49],"80":[0.7981,24535.03],"90":[0.8779,26583.96],"95":[0.9164,27648.31]},"SARIMA":{"70":[0.6983,14167.22],"80":[0.7833,15924.95],"90":[0.8606,17306.37],"95":[0.8974,18046.36]}},"06214500":{"LSTM":{"70":[0.6968,4059.84],"80":[0.8006,5282.98],"90":[0.8927,6537.9],"95":[0.9281,7045.78]},"Transformer":{"70":[0.6944,3867.36],"80":[0.8009,5119.25],"90":[0.8949,6169.38],"95":[0.9308,6662.66]},"TFT":{"70":[0.6967,4574.58],"80":[0.7984,5536.95],"90":[0.8874,6454.47],"95":[0.9229,6949.21]},"PatchTST":{"70":[0.6929,4257.78],"80":[0.7969,5629.39],"90":[0.8891,7005.93],"95":[0.9255,7593.56]},"PILSTMv1":{"70":[0.7025,3779.67],"80":[0.8015,4693.64],"90":[0.895,5608.83],"95":[0.9319,6186.05]},"GCN":{"70":[0.7038,9236.78],"80":[0.7991,10753.85],"90":[0.8732,11643.36],"95":[0.906,12222.23]},"GP Matérn":{"70":[0.7035,7215.3],"80":[0.8045,9285.07],"90":[0.8882,11590.08],"95":[0.924,12783.5]},"GP RBF":{"70":[0.7035,7584.96],"80":[0.8024,9763.43],"90":[0.8873,12124.81],"95":[0.9223,13706.27]},"ARIMA":{"70":[0.6776,9201.0],"80":[0.766,10109.28],"90":[0.8397,10736.69],"95":[0.8757,11289.87]},"SARIMA":{"70":[0.6917,3347.24],"80":[0.7972,4126.1],"90":[0.8862,4841.55],"95":[0.925,5141.63]}},"06934500":{"LSTM":{"70":[0.7008,69545.15],"80":[0.7988,80609.18],"90":[0.8832,90709.2],"95":[0.9172,96673.91]},"Transformer":{"70":[0.698,58131.6],"80":[0.7993,69231.14],"90":[0.8915,80918.49],"95":[0.9293,86612.12]},"TFT":{"70":[0.6996,80716.92],"80":[0.7976,95057.15],"90":[0.8844,109393.15],"95":[0.9225,116484.15]},"PatchTST":{"70":[0.6979,61082.62],"80":[0.8004,72397.0],"90":[0.8886,85387.47],"95":[0.9256,92783.54]},"PILSTMv1":{"70":[0.6996,76889.43],"80":[0.7984,87863.3],"90":[0.8809,98249.1],"95":[0.9164,103965.38]},"GCN":{"70":[0.7007,77954.46],"80":[0.7982,93903.15],"90":[0.882,105707.88],"95":[0.9173,113088.09]},"GP Matérn":{"70":[0.6987,73477.39],"80":[0.8005,86612.18],"90":[0.8864,101060.64],"95":[0.9215,109240.87]},"GP RBF":{"70":[0.6976,72074.54],"80":[0.7974,84949.57],"90":[0.8854,99254.5],"95":[0.9228,107811.15]},"ARIMA":{"70":[0.6964,77163.38],"80":[0.7964,87451.21],"90":[0.8817,95842.37],"95":[0.9179,99683.59]},"SARIMA":{"70":[0.6955,70254.41],"80":[0.7948,78034.34],"90":[0.8773,84706.13],"95":[0.9132,87963.89]}},"07374000":{"LSTM":{"70":[0.6991,410221.77],"80":[0.7942,459736.67],"90":[0.8804,503548.04],"95":[0.9192,528872.99]},"Transformer":{"70":[0.6947,330053.07],"80":[0.796,383184.42],"90":[0.883,432208.19],"95":[0.9235,454676.72]},"TFT":{"70":[0.7078,312210.6],"80":[0.8028,358308.46],"90":[0.8828,398341.7],"95":[0.9205,417499.62]},"PatchTST":{"70":[0.7023,331979.35],"80":[0.7975,388246.01],"90":[0.8836,428941.0],"95":[0.9235,453754.1]},"PILSTMv1":{"70":[0.697,374181.73],"80":[0.7946,428470.11],"90":[0.8818,471136.1],"95":[0.9208,491930.39]},"GCN":{"70":[0.6957,326102.95],"80":[0.7936,391327.18],"90":[0.8828,441600.58],"95":[0.9224,458751.53]},"GP Matérn":{"70":[0.713,354859.26],"80":[0.8103,412542.05],"90":[0.8928,472347.98],"95":[0.9296,504977.44]},"GP RBF":{"70":[0.7134,343107.18],"80":[0.8087,399863.15],"90":[0.8916,453439.38],"95":[0.9281,484953.07]},"ARIMA":{"70":[0.7201,444227.7],"80":[0.7993,492130.86],"90":[0.8761,524745.55],"95":[0.9112,539540.63]},"SARIMA":{"70":[0.7157,382817.39],"80":[0.8002,430666.2],"90":[0.8807,465477.01],"95":[0.9188,480429.74]}},"08057000":{"LSTM":{"70":[0.6986,3703.21],"80":[0.796,4582.83],"90":[0.8825,5690.96],"95":[0.9209,6259.71]},"Transformer":{"70":[0.6955,4166.37],"80":[0.7994,5149.82],"90":[0.8909,6332.09],"95":[0.9297,7313.65]},"TFT":{"70":[0.6995,3975.81],"80":[0.8007,4863.28],"90":[0.8888,5854.81],"95":[0.9272,6403.06]},"PatchTST":{"70":[0.693,5759.21],"80":[0.7961,7765.08],"90":[0.8872,10256.04],"95":[0.9233,12047.72]},"PILSTMv1":{"70":[0.702,3613.08],"80":[0.8023,4533.61],"90":[0.8877,5527.79],"95":[0.9253,6125.02]},"GCN":{"70":[0.7012,3585.21],"80":[0.8017,4392.8],"90":[0.8903,5416.8],"95":[0.9272,5969.71]},"GP Matérn":{"70":[0.6974,4814.04],"80":[0.7986,6144.18],"90":[0.8906,7853.43],"95":[0.9265,9000.79]},"GP RBF":{"70":[0.6976,4719.92],"80":[0.7991,5946.95],"90":[0.8907,7617.65],"95":[0.9281,8733.33]},"ARIMA":{"70":[0.686,10817.23],"80":[0.7888,14268.38],"90":[0.8761,16857.3],"95":[0.9118,18038.67]},"SARIMA":{"70":[0.6859,3911.38],"80":[0.7916,4723.62],"90":[0.8795,5421.42],"95":[0.9178,5751.76]}},"08158000":{"LSTM":{"70":[0.697,680.06],"80":[0.7981,927.23],"90":[0.8878,1207.59],"95":[0.9265,1381.68]},"Transformer":{"70":[0.7028,536.17],"80":[0.7982,656.36],"90":[0.89,877.57],"95":[0.9258,1002.71]},"TFT":{"70":[0.6983,605.99],"80":[0.7977,837.64],"90":[0.8838,1073.35],"95":[0.922,1172.43]},"PatchTST":{"70":[0.6995,689.36],"80":[0.798,892.67],"90":[0.8934,1278.04],"95":[0.9296,1511.08]},"PILSTMv1":{"70":[0.6986,697.38],"80":[0.7982,986.86],"90":[0.8865,1282.35],"95":[0.9241,1447.1]},"GCN":{"70":[0.7022,599.97],"80":[0.7996,722.64],"90":[0.8919,945.5],"95":[0.9306,1053.03]},"GP Matérn":{"70":[0.7006,744.58],"80":[0.7996,961.61],"90":[0.8926,1301.22],"95":[0.931,1488.15]},"GP RBF":{"70":[0.6995,780.18],"80":[0.799,1017.76],"90":[0.8935,1383.05],"95":[0.9306,1611.26]},"ARIMA":{"70":[0.7065,858.51],"80":[0.7982,1051.23],"90":[0.8849,1301.26],"95":[0.9211,1381.18]},"SARIMA":{"70":[0.7061,813.04],"80":[0.7989,985.81],"90":[0.885,1233.65],"95":[0.9217,1319.96]}},"08313000":{"LSTM":{"70":[0.6789,769.89],"80":[0.7831,902.44],"90":[0.8757,1013.49],"95":[0.9167,1072.98]},"Transformer":{"70":[0.71,735.86],"80":[0.804,857.6],"90":[0.8888,955.39],"95":[0.9274,1019.46]},"TFT":{"70":[0.6871,685.57],"80":[0.7873,804.31],"90":[0.8785,913.07],"95":[0.9193,975.53]},"PatchTST":{"70":[0.7103,673.5],"80":[0.8093,812.54],"90":[0.8965,911.59],"95":[0.9353,988.47]},"PILSTMv1":{"70":[0.6801,714.7],"80":[0.7839,843.49],"90":[0.8765,953.47],"95":[0.9176,1010.39]},"GCN":{"70":[0.697,860.58],"80":[0.797,970.41],"90":[0.884,1075.95],"95":[0.9237,1130.62]},"GP Matérn":{"70":[0.6991,1017.41],"80":[0.799,1228.26],"90":[0.8901,1425.34],"95":[0.9296,1531.01]},"GP RBF":{"70":[0.6966,1042.59],"80":[0.7982,1246.89],"90":[0.8904,1441.17],"95":[0.9304,1562.02]},"ARIMA":{"70":[0.6628,1328.18],"80":[0.7562,1414.65],"90":[0.8329,1481.57],"95":[0.8686,1520.9]},"SARIMA":{"70":[0.6983,1367.76],"80":[0.7687,1520.03],"90":[0.8449,1604.89],"95":[0.8789,1655.91]}},"09380000":{"LSTM":{"70":[0.7018,3187.46],"80":[0.7967,3640.21],"90":[0.882,4014.31],"95":[0.9213,4265.98]},"Transformer":{"70":[0.6909,2719.73],"80":[0.7934,3103.87],"90":[0.8845,3431.1],"95":[0.9209,3587.06]},"TFT":{"70":[0.6996,2468.04],"80":[0.7968,2914.43],"90":[0.8865,3250.33],"95":[0.9248,3439.36]},"PatchTST":{"70":[0.7029,2499.46],"80":[0.8017,2915.28],"90":[0.8919,3344.92],"95":[0.9307,3537.89]},"PILSTMv1":{"70":[0.6919,2944.56],"80":[0.7859,3353.78],"90":[0.8736,3685.7],"95":[0.9125,3884.09]},"GCN":{"70":[0.688,4099.41],"80":[0.785,4433.28],"90":[0.8669,4739.82],"95":[0.9011,4871.55]},"GP Matérn":{"70":[0.688,4014.61],"80":[0.7887,4541.4],"90":[0.8798,4973.4],"95":[0.9173,5182.75]},"GP RBF":{"70":[0.6866,3853.07],"80":[0.7873,4329.91],"90":[0.8784,4796.55],"95":[0.9162,5004.82]},"ARIMA":{"70":[0.6891,3376.0],"80":[0.7787,3677.52],"90":[0.8686,3939.23],"95":[0.9089,4098.37]},"SARIMA":{"70":[0.6879,3406.95],"80":[0.7779,3698.61],"90":[0.8653,3945.22],"95":[0.9068,4094.02]}},"11447650":{"LSTM":{"70":[0.7088,24661.73],"80":[0.804,28790.73],"90":[0.8898,32346.76],"95":[0.9309,35150.61]},"Transformer":{"70":[0.7064,28217.67],"80":[0.8052,33886.57],"90":[0.8931,39303.5],"95":[0.9306,42717.2]},"TFT":{"70":[0.7093,25399.3],"80":[0.8075,30745.68],"90":[0.8941,35250.03],"95":[0.9318,37991.01]},"PatchTST":{"70":[0.7092,28455.62],"80":[0.8049,34392.6],"90":[0.8894,39764.02],"95":[0.9261,42042.8]},"PILSTMv1":{"70":[0.7067,27008.43],"80":[0.8044,32816.58],"90":[0.8918,38306.81],"95":[0.9297,40835.94]},"GCN":{"70":[0.7117,27404.54],"80":[0.8077,32301.93],"90":[0.8913,36476.58],"95":[0.9304,39328.75]},"GP Matérn":{"70":[0.7116,27605.44],"80":[0.8064,32757.07],"90":[0.8907,37260.33],"95":[0.9297,40192.87]},"GP RBF":{"70":[0.7104,27610.54],"80":[0.8056,32204.11],"90":[0.8925,36458.29],"95":[0.9317,39833.93]},"ARIMA":{"70":[0.723,50682.33],"80":[0.8117,60278.81],"90":[0.8897,65985.75],"95":[0.9244,70839.93]},"SARIMA":{"70":[0.721,47306.74],"80":[0.8097,56114.12],"90":[0.8882,61200.53],"95":[0.9252,64976.96]}},"14105700":{"LSTM":{"70":[0.707,55097.01],"80":[0.8023,64937.76],"90":[0.885,71820.59],"95":[0.9199,75421.88]},"Transformer":{"70":[0.7098,56236.45],"80":[0.8034,66008.77],"90":[0.8853,74499.16],"95":[0.9191,79287.55]},"TFT":{"70":[0.7161,54545.92],"80":[0.8063,63617.41],"90":[0.8864,70883.28],"95":[0.9196,74133.13]},"PatchTST":{"70":[0.705,52838.45],"80":[0.8046,63743.55],"90":[0.8923,75305.54],"95":[0.9281,81718.78]},"PILSTMv1":{"70":[0.7079,55762.15],"80":[0.8028,65936.91],"90":[0.8879,75693.84],"95":[0.924,80331.78]},"GCN":{"70":[0.7003,53323.81],"80":[0.7962,62667.69],"90":[0.8826,72165.62],"95":[0.9192,77546.42]},"GP Matérn":{"70":[0.7026,56979.5],"80":[0.8007,69411.67],"90":[0.8847,81303.46],"95":[0.9207,88210.38]},"GP RBF":{"70":[0.7023,53642.43],"80":[0.7994,65815.76],"90":[0.8854,76844.61],"95":[0.9213,83392.12]},"ARIMA":{"70":[0.6885,84517.86],"80":[0.7929,96715.95],"90":[0.8831,107067.13],"95":[0.9236,110995.89]},"SARIMA":{"70":[0.6908,85651.39],"80":[0.7951,100349.94],"90":[0.8851,111368.68],"95":[0.9245,116297.14]}}}}

# --------------------------- anchors: 3D pages ----------------------------
D_LIVE_OLD = "async function bigModelLive() {"
D_LIVE_NEW = ("/* ht-weekly v1: expose live helpers for the weekly outlook panel */\n"
              "if (typeof htGapAssemble === 'function') window.htGapAssemble = htGapAssemble;\n"
              "if (typeof htBakedAssemble === 'function') window.htBakedAssemble = htBakedAssemble;\n"
              "if (typeof fetchLiveSoilSnow === 'function') window.fetchLiveSoilSnow = fetchLiveSoilSnow;\n"
              + D_LIVE_OLD)

# ------------------------- anchors: classic pages -------------------------
C_SEC_OLD = '<section class="hts-sec" id="hts-sec-drift">'
C_SEC_NEW = ('<section class="hts-sec" id="hts-sec-weekly">\n'
             '   <h2>Weekly outlook</h2>\n'
             '   <p>12-week outlook of weekly mean flow from the weekly models '
             '(alongside the daily 7-day forecast above).</p>\n'
             '   <div id="htwk-root"></div>\n'
             '  </section>\n  ' + C_SEC_OLD)

# ------------------------------ injected UI -------------------------------
JS_BODY = r"""
<script>
/* ht-weekly v1 - Weekly outlook: 12 weeks of weekly mean flow (dev).
 * Baked forecasts + weekly DACP half-widths ship as sidecars in
 * ../weekly/<site>.json and ../dacpw/<site>.json; live mode (3D pages)
 * runs the weekly neural ONNX models in ../onnx_w/<site>/. */
(function () {
  var NEURAL = ['LSTM', 'Transformer', 'TFT', 'PatchTST', 'PILSTMv1'];
  var META = window.__wkMeta || { leader: {}, st: {}, sum: {} };
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
    if (endIdx < 6 || endIdx >= flow.length) return null;
    var s = 0, c = 0;
    for (var j = endIdx - 6; j <= endIdx; j++) { var v = flow[j]; if (v != null && v > 0) { s += v; c++; } }
    return c >= 4 ? s / c : null;
  }
  function load() {
    var P = pay(); if (!P || !P.site) return;
    if (!W.wk && !W.wkErr) {
      fetch('../weekly/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
        .then(function (j) { W.wk = j; W.wk.idx = {}; j.dates.forEach(function (d, i) { W.wk.idx[d] = i; }); render(); })
        .catch(function () { W.wkErr = true; render(); });
    }
    if (!W.dq && !W.dqErr) {
      fetch('../dacpw/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
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
      return '<tr' + (n === sel ? ' class="htwk-sel"' : '') + '><td>' + n + (ref ? ' (reference)' : '') + '</td><td>' + L[n].toFixed(4) + '</td></tr>';
    }).join('');
    return '<div class="htwk-board"><div class="htwk-bt">Weekly outlook — 12 weeks, weekly mean flow · pooled test RMSE (log space), all 14 stations</div>'
      + '<table>' + rows + '</table></div>';
  }
  function draw(cv, ctx, fc, act, band) {
    var g = cv.getContext('2d'); if (!g) return;
    var cw = cv.width, ch = cv.height;
    g.clearRect(0, 0, cw, ch);
    var vals = [];
    ctx.concat(fc, act).forEach(function (p) { if (p[1] != null) vals.push(p[1]); });
    if (band) band.forEach(function (b) { if (b) { vals.push(b[0]); vals.push(b[1]); } });
    if (!vals.length) { g.fillStyle = '#9fb4c8'; g.font = '22px system-ui'; g.fillText('no weekly data for this date', 18, 40); return; }
    var lo = Math.floor(Math.log10(Math.min.apply(null, vals))), hi = Math.ceil(Math.log10(Math.max.apply(null, vals)));
    if (hi <= lo) hi = lo + 1;
    var X0 = 64, X1 = cw - 14, Y0 = 12, Y1 = ch - 30;
    function X(x) { return X0 + (x + 8.6) / 21.2 * (X1 - X0); }
    function Y(v) { var t = (Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo); return Y1 - t * (Y1 - Y0); }
    g.font = '19px system-ui'; g.textBaseline = 'middle';
    for (var e = lo; e <= hi; e++) {
      var yv = Math.pow(10, e), yy = Y(yv);
      g.strokeStyle = 'rgba(255,255,255,.13)'; g.beginPath(); g.moveTo(X0, yy); g.lineTo(X1, yy); g.stroke();
      g.fillStyle = '#9fb4c8'; g.fillText(fmt(yv), 6, yy);
    }
    g.strokeStyle = 'rgba(255,255,255,.3)'; g.beginPath(); g.moveTo(X(0), Y0); g.lineTo(X(0), Y1); g.stroke();
    g.fillStyle = '#9fb4c8';
    [-8, -4, 0, 4, 8, 12].forEach(function (x) { g.fillText(x === 0 ? 'issue' : (x > 0 ? '+' + x + 'w' : x + 'w'), X(x) - 10, Y1 + 15); });
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
    g.fillStyle = '#4CC9F0'; g.fillText('— forecast', X(6.4), Y0 + 10);
    g.fillStyle = '#9fb4c8'; g.fillText('— observed weekly mean', X(-8.4), Y0 + 10);
    if (act.length) { g.fillStyle = '#fff'; g.fillText('- - actual outcome', X(9.6), Y0 + 10); }
  }
  function stationLine(P, model) {
    var st = (META.st[P.site] || {})[model];
    var sum = ((META.sum[P.site] || {})[model] || {})[String(W.lvl)];
    var out = '';
    if (st != null) out += 'This station · ' + model + ' weekly test RMSE ' + st.toFixed(4);
    if (W.on && sum) out += (out ? ' · ' : '') + 'DACP ' + W.lvl + '% test coverage ' + sum[0].toFixed(2) + ' · mean width ' + fmt(sum[1]) + ' cfs';
    return out;
  }
  function render() {
    var root = $('htwk-root'); if (!root) return;
    var P = pay(), S = window.__htS;
    if (!P) { root.innerHTML = '<div class="htwk-note">weekly outlook unavailable</div>'; return; }
    if (W.wkErr) { var re1 = $('htwk-read'); if (re1) re1.innerHTML = '<div class="htwk-note">weekly forecasts unavailable (sidecar missing)</div>'; else root.innerHTML = '<div class="htwk-note">weekly forecasts unavailable (sidecar missing)</div>'; return; }
    if (!W.wk) { if (!$('htwk-canvas')) root.innerHTML = '<div class="htwk-note">loading weekly outlook…</div>'; load(); return; }
    var model = curModel();
    if (!model || W.wk.models.indexOf(model) < 0) model = W.wk.models[0];
    var sel = $('htwk-model');
    if (sel && sel.value !== model && !W.touched) sel.value = model;
    if (sel && W.touched) model = sel.value;
    W.model = model;
    var issueEl = $('htwk-issue'), readEl = $('htwk-read'), cv = $('htwk-canvas');
    var ctx = [], fc = [], act = [], band = null, issueTxt = '', rows = [];
    if (W.live) {
      var L = W.live;
      ctx = L.ctx; fc = L.preds.map(function (v, k) { return [k + 1, v]; });
      if (W.on && L.q) band = L.preds.map(function (v, k) { return L.q[k] == null ? null : [v * Math.exp(-L.q[k]), v * Math.exp(L.q[k])]; });
      issueTxt = 'LIVE outlook · issued ' + L.issue + ' (window ends ' + L.issue + ') · ' + model + ' run in-browser';
      rows = L.preds.map(function (v, k) { return [k + 1, addDays(L.issue, 7 * k + 1), addDays(L.issue, 7 * k + 7), v, band ? band[k] : null, null]; });
    } else {
      if (!S) { issueEl.textContent = '…'; return; }
      var day = S.day, issue = isoOf(P, day);
      for (var j = 8; j >= 1; j--) ctx.push([-j, blockMean(P.flow, day - 7 * (j - 1))]);
      for (var k2 = 1; k2 <= 12; k2++) { var am = blockMean(P.flow, day + 7 * k2); if (am != null) act.push([k2, am]); }
      var di = W.wk.idx[issue];
      var preds = (di != null) ? W.wk.predw[model][di] : null;
      issueTxt = 'Issue date ' + issue + ' · ' + model + (preds ? '' : ' · no baked weekly forecast for this date (weekly outlook covers ' + W.wk.dates[0] + ' … ' + W.wk.dates[W.wk.dates.length - 1] + ')');
      if (preds) {
        fc = preds.map(function (v, k) { return [k + 1, v]; });
        var qi = (W.on && W.dq) ? W.dq.idx[issue] : null;
        if (qi != null && W.dq.q[model]) {
          var ql = W.dq.q[model][String(W.lvl)];
          if (ql) band = preds.map(function (v, k) { var q = ql[k][qi]; return (q == null || v == null) ? null : [v * Math.exp(-q), v * Math.exp(q)]; });
        }
        rows = preds.map(function (v, k) {
          var a = blockMean(P.flow, day + 7 * (k + 1));
          return [k + 1, addDays(issue, 7 * k + 1), addDays(issue, 7 * k + 7), v, band ? band[k] : null, a];
        });
      }
    }
    if (issueEl) issueEl.textContent = issueTxt;
    if (cv) draw(cv, ctx, fc, act, band);
    if (readEl) {
      var html = '';
      if (rows.length) {
        html += '<table class="htwk-t"><tr><th>Wk</th><th>Week</th><th>Forecast</th>' + (band ? '<th>' + W.lvl + '% DACP</th>' : '') + '<th>Observed</th></tr>';
        rows.forEach(function (r) {
          html += '<tr><td>' + r[0] + '</td><td>' + r[1].slice(5) + ' – ' + r[2].slice(5) + '</td><td>' + fmt(r[3]) + '</td>'
            + (band ? '<td>' + (r[4] ? fmt(r[4][0]) + ' – ' + fmt(r[4][1]) : '–') + '</td>' : '')
            + '<td>' + fmt(r[5]) + '</td></tr>';
        });
        html += '</table><div class="htwk-note">cfs, weekly mean flow</div>';
      }
      var sl = stationLine(P, model);
      if (sl) html += '<div class="htwk-note">' + sl + '</div>';
      html += boardHTML(model);
      readEl.innerHTML = html;
    }
  }
  async function runLive() {
    var P = pay(); if (!P) return;
    var model = W.model || curModel();
    var st = $('htwk-status');
    function say(t) { if (st) st.textContent = t; }
    if (!window.htGapAssemble || !window.fetchLiveSoilSnow) { say('live assembly unavailable on this page'); return; }
    if (NEURAL.indexOf(model) < 0) { say('Live weekly outlook runs the neural models in-browser (LSTM, Transformer, TFT, PatchTST, PILSTMv1). ' + model + ' is baked-dates only.'); return; }
    if (!W.wk) { say('weekly data still loading…'); load(); return; }
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
      var url = '../onnx_w/' + P.site + '/' + model + '.onnx';
      var sess = await ort.InferenceSession.create(url);
      var feeds = {}; feeds[sess.inputNames[0]] = new ort.Tensor('float32', flat, [1, 29, 9]);
      var out = await sess.run(feeds);
      var diffs = Array.from(out[sess.outputNames[0]].data);
      if (diffs.length !== 12 || diffs.some(function (v) { return !isFinite(v); })) throw new Error('bad model output');
      var preds = diffs.map(function (d, k) { return Math.exp(last + d * tsd[k]); });
      var ctxD = [];
      for (var j2 = 8; j2 >= 1; j2--) {
        var s = 0, c = 0;
        for (var d2 = 0; d2 < 7; d2++) { var iso = addDays(win30[29], -7 * (j2 - 1) - d2); var v = flows[iso]; if (v != null && v > 0) { s += v; c++; } }
        ctxD.push([-j2, c >= 4 ? s / c : null]);
      }
      var q = null;
      if (W.dq && W.dq.q_end[model]) q = W.dq.q_end[model][String(W.lvl)];
      W.live = { issue: win30[29], preds: preds, ctx: ctxD, q: q };
      say('live outlook issued ' + win30[29] + ' · ' + model);
      var bx = $('htwk-back'); if (bx) bx.style.display = '';
      render();
    } catch (e) {
      say('live weekly failed: ' + (e && e.message ? e.message : e));
    }
    W.busy = false;
  }
  function controlsHTML() {
    var P = pay();
    var opts = (W.wk ? W.wk.models : (P ? P.models : [])).map(function (m) { return '<option value="' + m + '">' + m + '</option>'; }).join('');
    return '<div class="htwk-ctl">'
      + '<label>model <select id="htwk-model">' + opts + '</select></label>'
      + '<label style="cursor:pointer"><input type="checkbox" id="htwk-on" checked> DACP band</label>'
      + '<label>level <select id="htwk-lvl"><option value="70">70%</option><option value="80">80%</option><option value="90" selected>90%</option><option value="95">95%</option></select></label>'
      + (is3d ? '<button type="button" id="htwk-live">▶ Live weekly outlook</button><button type="button" id="htwk-back" style="display:none">↩ selected date</button>' : '')
      + '</div>'
      + '<div id="htwk-issue" class="htwk-issue"></div>'
      + '<canvas id="htwk-canvas" width="760" height="380"></canvas>'
      + '<div id="htwk-read"></div>'
      + (is3d ? '<div id="htwk-status" class="htwk-note"></div>' : '');
  }
  function wire() {
    var m = $('htwk-model');
    if (m) m.addEventListener('change', function () { W.touched = true; W.follow = false; W.model = this.value; render(); });
    var on = $('htwk-on');
    if (on) on.addEventListener('change', function () { W.on = this.checked; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lv = $('htwk-lvl');
    if (lv) lv.addEventListener('change', function () { W.lvl = +this.value; if (W.live && W.dq && W.dq.q_end[W.model]) W.live.q = W.dq.q_end[W.model][String(W.lvl)]; render(); });
    var lb = $('htwk-live');
    if (lb) lb.addEventListener('click', runLive);
    var bb = $('htwk-back');
    if (bb) bb.addEventListener('click', function () { W.live = null; bb.style.display = 'none'; var st = $('htwk-status'); if (st) st.textContent = ''; render(); });
  }
  var css = '.htwk-ctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0}'
    + '.htwk-ctl select,.htwk-ctl button{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:3px 6px;cursor:pointer}'
    + '.htwk-issue{font-weight:600;color:#BFD0E0;margin:2px 0 4px}'
    + '#htwk-canvas{width:100%;height:auto;display:block;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.12);border-radius:8px}'
    + '.htwk-t{border-collapse:collapse;width:100%;font-size:12px;margin-top:6px}'
    + '.htwk-t th,.htwk-t td{border-bottom:1px solid rgba(255,255,255,.12);padding:2px 6px;text-align:right}'
    + '.htwk-t th:first-child,.htwk-t td:first-child,.htwk-t td:nth-child(2){text-align:left}'
    + '.htwk-note{opacity:.85;font-size:12px;margin-top:6px}'
    + '.htwk-board{margin-top:10px}.htwk-bt{font-weight:700;color:#8FC1F2;font-size:12.5px;margin-bottom:4px}'
    + '.htwk-board table{border-collapse:collapse;font-size:12px}'
    + '.htwk-board td{padding:1px 10px 1px 0}'
    + '.htwk-board tr.htwk-sel td{color:#4CC9F0;font-weight:700}'
    + '#htwk-panel{position:fixed;left:14px;bottom:76px;z-index:9997;width:440px;max-width:94vw;background:rgba(12,18,28,.94);color:#e8eef5;border:1px solid rgba(255,255,255,.16);border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.45);font:12.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}'
    + '#htwk-panel .htwk-head{display:flex;justify-content:space-between;align-items:center;background:rgba(12,18,28,.9);color:#BFD0E0;font-weight:700;padding:6px 8px 6px 12px;border-radius:12px 12px 0 0;cursor:move;user-select:none;-webkit-user-select:none}'
    + '#htwk-panel .htwk-head button{background:rgba(35,70,110,.9);border:1px solid rgba(255,255,255,.35);color:#E6EDF5;border-radius:6px;min-width:24px;height:24px;padding:0 6px;cursor:pointer;font:600 13px/1 Arial}'
    + '#htwk-panel .htwk-body{padding:8px 12px 12px;max-height:66vh;overflow:auto}'
    + '#htwk-panel.htwk-max{left:10px !important;top:10px !important;bottom:auto !important;width:calc(100vw - 20px) !important;max-width:none !important}'
    + '#htwk-panel.htwk-max .htwk-body{max-height:calc(100vh - 90px)}'
    + '#htwk-panel .htwk-dev{background:#d9930d;color:#111;border-radius:4px;padding:0 5px;font-size:10px;vertical-align:1px;margin-left:6px}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);
  if (is3d) {
    var panel = document.createElement('div'); panel.id = 'htwk-panel';
    panel.innerHTML = '<div class="htwk-head" id="htwk-head"><span>Weekly outlook<span class="htwk-dev">DEV</span></span>'
      + '<span><button type="button" id="htwk-max" aria-label="maximize">⛶</button> <button type="button" id="htwk-min" aria-label="collapse">–</button></span></div>'
      + '<div class="htwk-body" id="htwk-body"><div id="htwk-root"></div></div>';
    document.body.appendChild(panel);
    var root0 = $('htwk-root'); root0.innerHTML = controlsHTML();
    wire(); load(); render();
    var head = $('htwk-head'), dragging = null;
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
    $('htwk-min').addEventListener('click', function () {
      var b = $('htwk-body'); var hid = b.style.display === 'none';
      b.style.display = hid ? '' : 'none'; this.textContent = hid ? '–' : '+';
    });
    $('htwk-max').addEventListener('click', function () { panel.classList.toggle('htwk-max'); });
  } else {
    var root1 = $('htwk-root');
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
    return ("<script>\nwindow.__wkMeta = " + json.dumps(WEEKLY_META, ensure_ascii=False, separators=(",", ":"))
            + ";\n</script>" + JS_BODY)


def patch_3d(s):
    if s.count(D_LIVE_OLD) != 1:
        return None
    return s.replace(D_LIVE_OLD, D_LIVE_NEW, 1)


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
    if MARKER not in out or "__wkMeta" not in out:
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
    print(f"patch_weekly: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
