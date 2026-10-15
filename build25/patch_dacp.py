#!/usr/bin/env python3
"""DACP confidence intervals for the DEV station pages (dev only).

Adds adaptive conformal prediction (DACP) interval bands to the baked
7-day forecasts, mirroring the method in the student "Prediction Model"
report: per station x model x lead, a chronological walk over the test
era (WY2025-26) with a rolling 180-day calibration window of |residuals|
in log-flow space; k adapts +0.005 on a hit / -miss on a miss with
miss/hit = target/(1-target) for levels 70/80/90/95. Computed offline by
~/workspace/hydrotwin_25yr/dacp25.py (RMSE-gated against the published
25-year results); per-station daily half-widths ship as sidecar JSON in
dacp/<site>.json, fetched lazily by the pages (same pattern as params/).

This patch (string surgery, no regex on code):
  classic pages (window.HT_DATA):
    - ivFor() consults window.__dacpIv first (DACP band via the page's
      own, previously inert, lo/hi band machinery), D.lo fallback kept;
    - the hardcoded '80%' band labels become the selected DACP level;
    - publishes the scene state as window.__htS for the readout.
  3D pages (window.HT3D):
    - publishes S2 as window.__htS;
    - drawFlow() calls window.__dacpBand before stroking the forecast
      line (band from the sidecar q for the issue date, pixel-clamped);
    - bigModelLive()'s livetxt summary gains a 'calibrated interval'
      line built from the end-of-test-era q (window.__dacpLiveIv).
  both: appends the DACP panel (toggle + 70/80/90/95 selector + one-line
  coverage/width readout; summary baked in below) just before </body>.
  If the sidecar fetch fails the toggle reports 'intervals unavailable'
  and every hook returns null - the page behaves exactly as before.

Idempotent: pages carrying the MARKER are skipped.
Run from the repo root: python3 build25/patch_dacp.py
"""
import json
import sys
from pathlib import Path

MARKER = "ht-dacp v1"

# === READOUT SUMMARY (generated from DACP_summary25.csv; do not hand-edit) ===
# {site: {model: {level: [test coverage, mean width cfs]}}}
DACP_SUM = {'01463500': {'LSTM': {'70': [0.7053, 6851.6], '80': [0.8027, 8322.18], '90': [0.8975, 11727.13], '95': [0.9376, 13766.96]}, 'Transformer': {'70': [0.7003, 6429.32], '80': [0.799, 8016.58], '90': [0.8945, 10949.6], '95': [0.9341, 13147.82]}, 'TFT': {'70': [0.7044, 6364.59], '80': [0.802, 7904.43], '90': [0.8964, 10941.54], '95': [0.9378, 13432.98]}, 'PatchTST': {'70': [0.707, 7511.05], '80': [0.8048, 9364.94], '90': [0.8958, 12819.3], '95': [0.9374, 15196.2]}, 'PILSTMv1': {'70': [0.7057, 6686.67], '80': [0.8024, 8112.04], '90': [0.8977, 11538.95], '95': [0.9378, 13737.58]}, 'GCN': {'70': [0.7036, 5959.77], '80': [0.8027, 8153.43], '90': [0.8958, 11280.61], '95': [0.9333, 13591.35]}, 'GP Matérn': {'70': [0.6999, 5582.66], '80': [0.8005, 7625.1], '90': [0.8964, 11686.85], '95': [0.9352, 13888.63]}, 'GP RBF': {'70': [0.7001, 5487.51], '80': [0.8014, 7509.37], '90': [0.8966, 11516.32], '95': [0.9374, 13661.02]}, 'ARIMA': {'70': [0.6976, 26476.85], '80': [0.7956, 29574.47], '90': [0.8756, 33241.16], '95': [0.9084, 35970.63]}, 'SARIMA': {'70': [0.6976, 26474.11], '80': [0.7956, 29552.95], '90': [0.8758, 33222.1], '95': [0.9084, 35946.05]}}, '01646500': {'LSTM': {'70': [0.7056, 6786.32], '80': [0.8015, 8976.68], '90': [0.8912, 12168.88], '95': [0.9318, 14170.48]}, 'Transformer': {'70': [0.7021, 6234.69], '80': [0.7993, 8176.63], '90': [0.8918, 11499.1], '95': [0.93, 13481.81]}, 'TFT': {'70': [0.706, 9657.19], '80': [0.7983, 12049.78], '90': [0.8904, 15220.54], '95': [0.9284, 17979.72]}, 'PatchTST': {'70': [0.6995, 5841.69], '80': [0.7969, 8083.65], '90': [0.8876, 12023.14], '95': [0.9294, 14150.17]}, 'PILSTMv1': {'70': [0.7041, 6608.56], '80': [0.8007, 8462.95], '90': [0.8925, 11442.44], '95': [0.9314, 13711.01]}, 'GCN': {'70': [0.7011, 5173.22], '80': [0.8001, 7230.27], '90': [0.8898, 11242.09], '95': [0.929, 13548.82]}, 'GP Matérn': {'70': [0.7017, 5958.37], '80': [0.8009, 8440.79], '90': [0.8922, 12601.59], '95': [0.9314, 14687.2]}, 'GP RBF': {'70': [0.7015, 5656.84], '80': [0.8011, 7771.21], '90': [0.892, 12046.43], '95': [0.932, 13867.05]}, 'ARIMA': {'70': [0.7114, 35939.02], '80': [0.8013, 39758.06], '90': [0.8876, 42791.09], '95': [0.9267, 46246.79]}, 'SARIMA': {'70': [0.7114, 35730.87], '80': [0.8013, 39573.94], '90': [0.8878, 42753.76], '95': [0.9259, 46228.8]}}, '02320500': {'LSTM': {'70': [0.6937, 493.66], '80': [0.7986, 744.39], '90': [0.8955, 1082.1], '95': [0.9352, 1275.81]}, 'Transformer': {'70': [0.6911, 543.8], '80': [0.7969, 734.97], '90': [0.8943, 1057.1], '95': [0.9359, 1231.75]}, 'TFT': {'70': [0.6939, 535.95], '80': [0.7994, 743.43], '90': [0.897, 1089.69], '95': [0.9378, 1280.76]}, 'PatchTST': {'70': [0.6946, 610.78], '80': [0.7988, 847.42], '90': [0.8966, 1227.42], '95': [0.9372, 1364.91]}, 'PILSTMv1': {'70': [0.6939, 497.36], '80': [0.7986, 740.96], '90': [0.8955, 1082.89], '95': [0.9365, 1270.55]}, 'GCN': {'70': [0.6956, 577.64], '80': [0.7988, 788.73], '90': [0.8968, 1136.41], '95': [0.9402, 1343.55]}, 'GP Matérn': {'70': [0.6903, 412.04], '80': [0.7969, 604.09], '90': [0.8955, 1016.68], '95': [0.9359, 1271.34]}, 'GP RBF': {'70': [0.6909, 404.75], '80': [0.7982, 607.23], '90': [0.8975, 1009.6], '95': [0.9374, 1293.81]}, 'ARIMA': {'70': [0.6935, 6139.24], '80': [0.7711, 6497.34], '90': [0.8503, 6678.28], '95': [0.8863, 6818.88]}, 'SARIMA': {'70': [0.6928, 6165.07], '80': [0.7707, 6522.3], '90': [0.8496, 6702.63], '95': [0.8855, 6843.66]}}, '03294500': {'LSTM': {'70': [0.6945, 105542.5], '80': [0.7962, 133025.14], '90': [0.8941, 165604.31], '95': [0.9272, 185707.29]}, 'Transformer': {'70': [0.6983, 96622.24], '80': [0.8, 127160.16], '90': [0.8949, 172723.54], '95': [0.9299, 193732.61]}, 'TFT': {'70': [0.6983, 98768.34], '80': [0.7981, 125816.87], '90': [0.893, 163209.63], '95': [0.9299, 185735.56]}, 'PatchTST': {'70': [0.696, 102151.56], '80': [0.8004, 126288.43], '90': [0.896, 177650.72], '95': [0.9318, 201771.19]}, 'PILSTMv1': {'70': [0.6956, 98196.25], '80': [0.7973, 127178.38], '90': [0.893, 163955.64], '95': [0.9291, 180301.09]}, 'GCN': {'70': [0.693, 121550.82], '80': [0.7947, 153633.7], '90': [0.8933, 197030.27], '95': [0.933, 221085.34]}, 'GP Matérn': {'70': [0.6968, 103994.38], '80': [0.797, 134206.37], '90': [0.8971, 191962.08], '95': [0.9368, 217203.79]}, 'GP RBF': {'70': [0.6937, 102279.18], '80': [0.7947, 134540.36], '90': [0.8964, 181044.76], '95': [0.9345, 204898.21]}, 'ARIMA': {'70': [0.7013, 233701.92], '80': [0.795, 300758.82], '90': [0.8933, 392548.27], '95': [0.9375, 427268.31]}, 'SARIMA': {'70': [0.6998, 227853.23], '80': [0.7947, 297743.58], '90': [0.8933, 384700.18], '95': [0.9364, 417399.33]}}, '05331000': {'LSTM': {'70': [0.6914, 4629.03], '80': [0.7943, 5829.5], '90': [0.8891, 7681.51], '95': [0.927, 8931.37]}, 'Transformer': {'70': [0.6959, 4729.13], '80': [0.7945, 6197.93], '90': [0.8887, 8074.84], '95': [0.9272, 9109.74]}, 'TFT': {'70': [0.6902, 4817.75], '80': [0.7915, 5831.76], '90': [0.8874, 7466.55], '95': [0.9266, 8476.82]}, 'PatchTST': {'70': [0.6938, 4823.33], '80': [0.7947, 6099.84], '90': [0.8891, 7819.75], '95': [0.9259, 8784.52]}, 'PILSTMv1': {'70': [0.6923, 4553.7], '80': [0.7928, 5979.64], '90': [0.8874, 7717.22], '95': [0.9266, 8628.85]}, 'GCN': {'70': [0.6925, 4659.35], '80': [0.7939, 5890.56], '90': [0.8876, 7547.24], '95': [0.928, 8547.09]}, 'GP Matérn': {'70': [0.6942, 4939.91], '80': [0.796, 6122.33], '90': [0.8906, 8126.99], '95': [0.9289, 9542.96]}, 'GP RBF': {'70': [0.6938, 4807.18], '80': [0.7956, 5902.23], '90': [0.8912, 7926.61], '95': [0.9291, 9265.71]}, 'ARIMA': {'70': [0.683, 20213.04], '80': [0.7884, 22293.49], '90': [0.8777, 24689.83], '95': [0.9156, 25802.0]}, 'SARIMA': {'70': [0.6832, 19902.85], '80': [0.7888, 22127.32], '90': [0.8792, 24497.98], '95': [0.9162, 25584.55]}}, '06214500': {'LSTM': {'70': [0.7026, 2102.05], '80': [0.802, 2824.81], '90': [0.8929, 3517.64], '95': [0.9297, 3922.28]}, 'Transformer': {'70': [0.7001, 2219.97], '80': [0.8013, 2921.51], '90': [0.8908, 3599.38], '95': [0.9297, 4090.3]}, 'TFT': {'70': [0.7033, 2065.81], '80': [0.8024, 2811.68], '90': [0.8929, 3543.37], '95': [0.9293, 4263.46]}, 'PatchTST': {'70': [0.7026, 2240.47], '80': [0.8029, 3255.03], '90': [0.8942, 4124.65], '95': [0.9309, 4691.49]}, 'PILSTMv1': {'70': [0.6989, 2236.29], '80': [0.8001, 2936.51], '90': [0.8903, 3730.86], '95': [0.9288, 4134.21]}, 'GCN': {'70': [0.7095, 3572.51], '80': [0.8072, 4473.9], '90': [0.891, 5031.1], '95': [0.9247, 5395.77]}, 'GP Matérn': {'70': [0.709, 2877.88], '80': [0.8072, 3832.26], '90': [0.8924, 4849.7], '95': [0.9297, 5393.34]}, 'GP RBF': {'70': [0.7086, 2819.39], '80': [0.8061, 3855.31], '90': [0.8935, 4654.49], '95': [0.9299, 5221.71]}, 'ARIMA': {'70': [0.6653, 12759.38], '80': [0.7454, 13437.26], '90': [0.8274, 14498.55], '95': [0.8652, 15231.25]}, 'SARIMA': {'70': [0.6646, 12912.89], '80': [0.7461, 13612.03], '90': [0.8285, 14630.1], '95': [0.8661, 15404.82]}}, '06934500': {'LSTM': {'70': [0.7058, 31458.99], '80': [0.8046, 41111.24], '90': [0.8914, 55184.72], '95': [0.928, 63519.72]}, 'Transformer': {'70': [0.7086, 33589.86], '80': [0.806, 42636.58], '90': [0.8937, 54895.82], '95': [0.9292, 62892.75]}, 'TFT': {'70': [0.7066, 33882.7], '80': [0.8048, 42219.75], '90': [0.8918, 53522.02], '95': [0.9276, 59802.43]}, 'PatchTST': {'70': [0.7086, 35096.22], '80': [0.806, 44752.07], '90': [0.8935, 59139.35], '95': [0.93, 66973.32]}, 'PILSTMv1': {'70': [0.7056, 31695.91], '80': [0.8046, 40875.87], '90': [0.8912, 55240.1], '95': [0.928, 63444.06]}, 'GCN': {'70': [0.7121, 38485.52], '80': [0.8099, 50147.44], '90': [0.8939, 63566.19], '95': [0.9288, 71756.53]}, 'GP Matérn': {'70': [0.7086, 33692.45], '80': [0.8074, 44966.22], '90': [0.8933, 61471.37], '95': [0.93, 70843.81]}, 'GP RBF': {'70': [0.709, 33470.45], '80': [0.8068, 45055.02], '90': [0.8933, 61186.36], '95': [0.9294, 70801.59]}, 'ARIMA': {'70': [0.7039, 107686.55], '80': [0.8028, 119770.5], '90': [0.8847, 129666.28], '95': [0.9146, 133265.59]}, 'SARIMA': {'70': [0.7023, 108464.23], '80': [0.8017, 120841.42], '90': [0.8847, 130552.87], '95': [0.9146, 134592.34]}}, '07374000': {'LSTM': {'70': [0.6973, 81990.86], '80': [0.7949, 98011.29], '90': [0.8927, 127554.2], '95': [0.9316, 144154.39]}, 'Transformer': {'70': [0.6988, 78727.24], '80': [0.8005, 94534.99], '90': [0.8958, 120651.94], '95': [0.9348, 140380.42]}, 'TFT': {'70': [0.7029, 81996.28], '80': [0.7988, 99174.14], '90': [0.8936, 126513.49], '95': [0.9344, 142112.09]}, 'PatchTST': {'70': [0.6982, 85096.03], '80': [0.8009, 105134.86], '90': [0.8958, 134724.2], '95': [0.9337, 153549.45]}, 'PILSTMv1': {'70': [0.6976, 81808.77], '80': [0.796, 96985.71], '90': [0.8943, 128135.48], '95': [0.9331, 146440.11]}, 'GCN': {'70': [0.6954, 110151.67], '80': [0.7954, 134648.0], '90': [0.893, 169276.39], '95': [0.9359, 177974.92]}, 'GP Matérn': {'70': [0.6971, 84659.72], '80': [0.799, 107930.3], '90': [0.8964, 140971.96], '95': [0.9365, 158938.23]}, 'GP RBF': {'70': [0.698, 75972.1], '80': [0.7986, 93326.7], '90': [0.8945, 122094.22], '95': [0.9333, 140359.06]}, 'ARIMA': {'70': [0.6686, 614548.62], '80': [0.7441, 707881.24], '90': [0.8269, 744517.55], '95': [0.8687, 775525.94]}, 'SARIMA': {'70': [0.6684, 615340.8], '80': [0.7439, 703290.37], '90': [0.8267, 744513.28], '95': [0.8685, 776113.1]}}, '08057000': {'LSTM': {'70': [0.7046, 2340.94], '80': [0.8063, 3597.53], '90': [0.902, 6036.83], '95': [0.937, 8081.0]}, 'Transformer': {'70': [0.7158, 2575.59], '80': [0.8134, 3602.59], '90': [0.9047, 5774.21], '95': [0.9379, 7668.03]}, 'TFT': {'70': [0.7034, 2460.3], '80': [0.8052, 3599.63], '90': [0.9003, 5923.82], '95': [0.9361, 7837.87]}, 'PatchTST': {'70': [0.7192, 3233.49], '80': [0.8158, 4710.88], '90': [0.9049, 7990.63], '95': [0.9372, 10284.52]}, 'PILSTMv1': {'70': [0.7088, 2241.3], '80': [0.8083, 3529.4], '90': [0.9029, 6122.64], '95': [0.9381, 8275.13]}, 'GCN': {'70': [0.726, 2750.8], '80': [0.82, 3796.87], '90': [0.906, 5963.06], '95': [0.9383, 8127.23]}, 'GP Matérn': {'70': [0.7231, 2701.5], '80': [0.8171, 4195.81], '90': [0.9056, 7148.03], '95': [0.9392, 9062.84]}, 'GP RBF': {'70': [0.7234, 2690.08], '80': [0.8171, 4204.44], '90': [0.9058, 7207.87], '95': [0.9368, 9569.92]}, 'ARIMA': {'70': [0.6767, 7778.75], '80': [0.7906, 9220.03], '90': [0.8897, 11193.6], '95': [0.9275, 12716.73]}, 'SARIMA': {'70': [0.6767, 7778.75], '80': [0.7906, 9220.03], '90': [0.8897, 11193.6], '95': [0.9275, 12716.73]}}, '08158000': {'LSTM': {'70': [0.7058, 338.23], '80': [0.8056, 453.44], '90': [0.901, 1055.42], '95': [0.9383, 1234.11]}, 'Transformer': {'70': [0.7035, 361.76], '80': [0.8054, 589.71], '90': [0.9008, 1594.87], '95': [0.9399, 1825.26]}, 'TFT': {'70': [0.7013, 346.17], '80': [0.8032, 499.06], '90': [0.8998, 1508.54], '95': [0.9389, 1659.98]}, 'PatchTST': {'70': [0.7088, 396.38], '80': [0.8074, 575.01], '90': [0.9004, 1830.71], '95': [0.9369, 2228.85]}, 'PILSTMv1': {'70': [0.7108, 320.62], '80': [0.807, 447.8], '90': [0.902, 1034.25], '95': [0.9401, 1180.88]}, 'GCN': {'70': [0.706, 332.91], '80': [0.8042, 506.13], '90': [0.9008, 1252.59], '95': [0.9385, 1462.08]}, 'GP Matérn': {'70': [0.7096, 415.43], '80': [0.8068, 655.21], '90': [0.9006, 1717.54], '95': [0.9377, 2152.72]}, 'GP RBF': {'70': [0.7078, 413.66], '80': [0.8064, 660.68], '90': [0.9008, 1848.29], '95': [0.9385, 2196.52]}, 'ARIMA': {'70': [0.7192, 1252.54], '80': [0.8105, 1635.16], '90': [0.902, 1979.46], '95': [0.9405, 2189.9]}, 'SARIMA': {'70': [0.7192, 1252.54], '80': [0.8105, 1635.16], '90': [0.902, 1979.46], '95': [0.9405, 2189.9]}}, '08313000': {'LSTM': {'70': [0.681, 266.74], '80': [0.7892, 349.87], '90': [0.887, 463.39], '95': [0.9245, 517.45]}, 'Transformer': {'70': [0.6847, 269.05], '80': [0.79, 351.69], '90': [0.8888, 481.34], '95': [0.9259, 556.62]}, 'TFT': {'70': [0.6832, 255.51], '80': [0.7902, 335.9], '90': [0.8888, 455.19], '95': [0.9261, 525.61]}, 'PatchTST': {'70': [0.6826, 263.09], '80': [0.7904, 347.37], '90': [0.8896, 464.76], '95': [0.9288, 546.78]}, 'PILSTMv1': {'70': [0.6812, 281.58], '80': [0.7892, 362.53], '90': [0.8856, 478.64], '95': [0.9233, 541.59]}, 'GCN': {'70': [0.6812, 248.26], '80': [0.7902, 336.34], '90': [0.8882, 444.5], '95': [0.9286, 507.63]}, 'GP Matérn': {'70': [0.6843, 276.78], '80': [0.7906, 368.76], '90': [0.8888, 494.87], '95': [0.9282, 586.69]}, 'GP RBF': {'70': [0.6847, 278.34], '80': [0.7908, 374.07], '90': [0.8894, 510.39], '95': [0.9284, 603.53]}, 'ARIMA': {'70': [0.6804, 1421.2], '80': [0.7812, 1580.41], '90': [0.861, 1686.26], '95': [0.8955, 1757.91]}, 'SARIMA': {'70': [0.6997, 929.36], '80': [0.7997, 1046.5], '90': [0.8839, 1139.42], '95': [0.9184, 1203.64]}}, '09380000': {'LSTM': {'70': [0.7025, 1254.07], '80': [0.8032, 1541.09], '90': [0.8993, 2029.23], '95': [0.9379, 2318.84]}, 'Transformer': {'70': [0.7031, 1105.2], '80': [0.8057, 1409.54], '90': [0.9036, 1915.87], '95': [0.9432, 2235.89]}, 'TFT': {'70': [0.7076, 1255.91], '80': [0.8047, 1602.99], '90': [0.8989, 2117.91], '95': [0.9364, 2414.92]}, 'PatchTST': {'70': [0.7126, 1065.21], '80': [0.8079, 1426.09], '90': [0.8983, 1999.66], '95': [0.9351, 2286.97]}, 'PILSTMv1': {'70': [0.7023, 1230.99], '80': [0.8032, 1519.49], '90': [0.8996, 2024.89], '95': [0.9383, 2322.93]}, 'GCN': {'70': [0.7124, 1293.55], '80': [0.8075, 1606.9], '90': [0.9019, 2138.37], '95': [0.9413, 2434.68]}, 'GP Matérn': {'70': [0.7128, 1398.62], '80': [0.8115, 1767.27], '90': [0.9, 2337.62], '95': [0.9364, 2714.59]}, 'GP RBF': {'70': [0.7121, 1287.46], '80': [0.81, 1606.56], '90': [0.9015, 2131.63], '95': [0.9385, 2420.76]}, 'ARIMA': {'70': [0.6957, 2895.27], '80': [0.7946, 3209.07], '90': [0.8884, 3564.8], '95': [0.9287, 3724.95]}, 'SARIMA': {'70': [0.6957, 2895.27], '80': [0.7946, 3209.07], '90': [0.8884, 3564.8], '95': [0.9287, 3724.95]}}, '11447650': {'LSTM': {'70': [0.7198, 7589.43], '80': [0.8151, 10275.33], '90': [0.9044, 15719.92], '95': [0.9407, 19052.6]}, 'Transformer': {'70': [0.7224, 7426.15], '80': [0.8176, 10236.15], '90': [0.905, 15340.6], '95': [0.9403, 19871.86]}, 'TFT': {'70': [0.7196, 7442.73], '80': [0.8157, 10033.58], '90': [0.9046, 15776.33], '95': [0.9391, 19138.38]}, 'PatchTST': {'70': [0.7259, 8704.7], '80': [0.8196, 12125.74], '90': [0.906, 18346.96], '95': [0.9403, 21899.87]}, 'PILSTMv1': {'70': [0.7196, 7582.1], '80': [0.8153, 10199.66], '90': [0.9044, 15787.11], '95': [0.9412, 19252.13]}, 'GCN': {'70': [0.7222, 7821.84], '80': [0.8182, 10705.5], '90': [0.9054, 16909.63], '95': [0.9399, 20441.35]}, 'GP Matérn': {'70': [0.7194, 7573.85], '80': [0.8162, 10628.52], '90': [0.904, 15680.38], '95': [0.9401, 19612.25]}, 'GP RBF': {'70': [0.7196, 7577.77], '80': [0.8164, 10405.79], '90': [0.9038, 15405.38], '95': [0.9393, 19196.41]}, 'ARIMA': {'70': [0.7206, 35988.92], '80': [0.8143, 42152.47], '90': [0.8922, 45996.43], '95': [0.9274, 47995.83]}, 'SARIMA': {'70': [0.7206, 35988.92], '80': [0.8143, 42152.47], '90': [0.8922, 45996.43], '95': [0.9274, 47995.83]}}, '14105700': {'LSTM': {'70': [0.711, 35103.63], '80': [0.8076, 44628.02], '90': [0.8941, 55328.12], '95': [0.9279, 61250.8]}, 'Transformer': {'70': [0.7104, 34468.31], '80': [0.8086, 44315.42], '90': [0.8976, 56334.87], '95': [0.9299, 61786.55]}, 'TFT': {'70': [0.7129, 33654.98], '80': [0.8098, 43261.37], '90': [0.8982, 54911.35], '95': [0.9305, 61413.63]}, 'PatchTST': {'70': [0.7135, 37819.64], '80': [0.8102, 49155.27], '90': [0.8951, 62307.33], '95': [0.9273, 68881.44]}, 'PILSTMv1': {'70': [0.7106, 34856.67], '80': [0.8078, 43762.61], '90': [0.8947, 54870.26], '95': [0.9291, 59881.24]}, 'GCN': {'70': [0.7104, 36084.57], '80': [0.8082, 45079.82], '90': [0.8955, 56120.49], '95': [0.9287, 61896.76]}, 'GP Matérn': {'70': [0.7108, 37351.89], '80': [0.808, 48425.43], '90': [0.8958, 60982.41], '95': [0.9285, 67691.67]}, 'GP RBF': {'70': [0.7112, 37003.86], '80': [0.808, 46351.36], '90': [0.8964, 58991.67], '95': [0.9297, 65038.09]}, 'ARIMA': {'70': [0.6759, 81224.58], '80': [0.7714, 92193.21], '90': [0.8604, 106119.26], '95': [0.8984, 116571.53]}, 'SARIMA': {'70': [0.6759, 81224.58], '80': [0.7714, 92193.21], '90': [0.8604, 106119.26], '95': [0.8984, 116571.53]}}}

# ------------------------- anchors: classic pages -------------------------
C_IV_OLD = ("const ivFor = (m, issue, lead) => (D.lo && issue >= 0 && issue < N && D.lo[m][lead - 1][issue] != null)\n"
            "  ? [Math.max(1, D.lo[m][lead - 1][issue]), D.hi[m][lead - 1][issue]] : null;")
C_IV_NEW = ("const ivFor = (m, issue, lead) => { const R = (typeof window !== 'undefined' && window.__dacpIv) ? window.__dacpIv(m, issue, lead) : null; "
            "if (R) return R; return (D.lo && issue >= 0 && issue < N && D.lo[m][lead - 1][issue] != null) "
            "? [Math.max(1, D.lo[m][lead - 1][issue]), D.hi[m][lead - 1][issue]] : null; };")
C_LEG_OLD = "g.fillText('80%', lx + 40, 62);"
C_LEG_NEW = "g.fillText(window.__dacpLabel || '80%', lx + 40, 62);"
C_LAB_OLD = r"\n80% ${fmtQ(iv[0])}"
C_LAB_NEW = r"\n${window.__dacpLabel || '80%'} ${fmtQ(iv[0])}"
C_SM_OLD = "S.model = params.has('model') ? Math.max(0, D.models.indexOf(params.get('model'))) : (D.live || D.station ? 0 : bestModel(S.lead));"
C_SM_NEW = C_SM_OLD + "\nwindow.__htS = S;"

# --------------------------- anchors: 3D pages ----------------------------
D_QP_OLD = "const qp = new URLSearchParams(location.search);"
D_QP_NEW = "window.__htS = S2;\n" + D_QP_OLD
D_FC_OLD = ("  if (fc.length && D.flow[i] != null) { g.strokeStyle = mcol; g.lineWidth = 6; g.beginPath(); "
            "g.moveTo(X(i), Y(D.flow[i])); fc.forEach(([k, v]) => g.lineTo(X(k), Y(v))); g.stroke(); }")
D_FC_NEW = ("  if (window.__dacpBand) window.__dacpBand(g, X, Y, i, S2.model, fc, mcol, y0, y1);\n" + D_FC_OLD)
D_LV_OLD = r"fc.map((v, l) => `+${l + 1}d ${Math.round(v).toLocaleString('en-US')}`).join(' \u00b7 ') + ' cfs';"
D_LV_NEW = (D_LV_OLD + "\n    if (lv && window.__dacpLiveIv) { const htIvTxt = window.__dacpLiveIv(mname, fc); "
            "if (htIvTxt) lv.innerHTML += '<br>' + htIvTxt; }")

# ------------------------------ injected UI -------------------------------
JS_BODY = r"""
<script>
/* ht-dacp v1 - DACP confidence intervals (dev). Half-widths (log space)
 * ship in ../dacp/<site>.json (offline DACP walk over the test era);
 * band for a forecast value p at lead l is [p*exp(-q), p*exp(q)]. */
(function () {
  var ST = window.__dacp = { on: true, lvl: 90, data: null, err: false, loading: false, idx: null };
  window.__dacpLabel = '90%';
  function pay() {
    try {
      if (window.HT_DATA) { var D = window.HT_DATA; return { models: D.models, pred: D.pred, flow: D.flow, start: D.start, site: (D.station && D.station.stationId || '').replace('USGS-', '') }; }
      if (window.HT3D) { var E = window.HT3D; return { models: E.models, pred: E.pred, flow: E.flow, start: E.start, site: E.site }; }
    } catch (e) {}
    return null;
  }
  function isoDay(P, i) { return new Date(Date.parse(P.start + 'T00:00:00Z') + i * 864e5).toISOString().slice(0, 10); }
  function load() {
    var P = pay();
    if (ST.data || ST.loading || ST.err || !P || !P.site) return;
    ST.loading = true;
    fetch('../dacp/' + P.site + '.json').then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (j) { ST.data = j; ST.idx = {}; j.dates.forEach(function (d, i) { ST.idx[d] = i; }); ST.loading = false; refresh(); poke(); })
      .catch(function () { ST.err = true; ST.loading = false; refresh(); });
  }
  function qFor(P, name, lvl, lead, issue) {
    if (!ST.on || !ST.data || !ST.idx) return null;
    var di = ST.idx[isoDay(P, issue)]; if (di == null) return null;
    var M = ST.data.q[name]; if (!M) return null;
    var L = M[String(lvl)]; if (!L) return null;
    var v = L[lead - 1][di]; return (v == null ? null : v);
  }
  window.__dacpIv = function (m, issue, lead) {
    if (!ST.on) return null;
    var P = pay(); if (!P) return null;
    var p = P.pred[m][lead - 1][issue]; if (p == null) return null;
    var q = qFor(P, P.models[m], ST.lvl, lead, issue); if (q == null) return null;
    return [Math.max(1, p * Math.exp(-q)), p * Math.exp(q)];
  };
  window.__dacpBand = function (g, X, Y, i, model, fc, mcol, yTop, yBot) {
    if (!ST.on || !fc.length) return;
    var P = pay(); if (!P) return;
    var name = P.models[model], pts = [];
    for (var a = 0; a < fc.length; a++) {
      var q = qFor(P, name, ST.lvl, fc[a][0] - i, i); if (q == null) return;
      pts.push([fc[a][0], fc[a][1], q]);
    }
    var cl = function (yy) { return Math.max(yTop, Math.min(yBot, yy)); };
    g.save(); g.fillStyle = mcol; g.globalAlpha = 0.25; g.beginPath();
    g.moveTo(X(i), cl(Y(P.flow[i])));
    pts.forEach(function (pt) { g.lineTo(X(pt[0]), cl(Y(pt[1] * Math.exp(pt[2])))); });
    for (var b = pts.length - 1; b >= 0; b--) g.lineTo(X(pts[b][0]), cl(Y(pts[b][1] * Math.exp(-pts[b][2]))));
    g.closePath(); g.fill(); g.restore();
  };
  window.__dacpLiveIv = function (mname, fc) {
    if (!ST.on) return null;
    if (!ST.data) { load(); return null; }
    var M = ST.data.q_end[mname]; if (!M) return null;
    var qe = M[String(ST.lvl)]; if (!qe) return null;
    var f = function (v) { return Math.round(v).toLocaleString('en-US'); };
    var parts = [];
    for (var l = 0; l < fc.length; l++) { if (qe[l] == null) continue; parts.push('+' + (l + 1) + 'd ' + f(fc[l] * Math.exp(-qe[l])) + '–' + f(fc[l] * Math.exp(qe[l]))); }
    if (!parts.length) return null;
    return '<span style="opacity:.85">' + ST.lvl + '% calibrated interval: ' + parts.join(' · ') + ' cfs</span>';
  };
  var css = '#ht-dacp-panel{position:fixed;left:50%;transform:translateX(-50%);bottom:14px;z-index:9998;background:rgba(12,18,28,.92);color:#e8eef5;border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:8px 14px;font:12.5px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,.45);display:flex;align-items:center;gap:10px;max-width:94vw;flex-wrap:wrap;justify-content:center}'
    + '#ht-dacp-panel select{background:#0E1A24;color:#e8eef5;border:1px solid rgba(255,255,255,.3);border-radius:6px;font:600 12.5px system-ui;padding:2px 4px}'
    + '#ht-dacp-panel .htdc-t{font-weight:700;color:#8FC1F2}'
    + '#ht-dacp-panel .htdc-dev{background:#d9930d;color:#111;border-radius:4px;padding:0 5px;font-size:10px;vertical-align:1px}'
    + '#htdc-read{opacity:.92}';
  var sty = document.createElement('style'); sty.textContent = css; document.head.appendChild(sty);
  var panel = document.createElement('div'); panel.id = 'ht-dacp-panel';
  panel.innerHTML = '<span class="htdc-t">Confidence interval <span class="htdc-dev">DEV</span></span>'
    + '<label style="cursor:pointer"><input type="checkbox" id="htdc-on" checked> DACP band</label>'
    + '<label>level <select id="htdc-lvl"><option value="70">70%</option><option value="80">80%</option><option value="90" selected>90%</option><option value="95">95%</option></select></label>'
    + '<span id="htdc-read"></span>';
  document.body.appendChild(panel);
  var SUM = window.__dacpSum || {};
  function fmtW(w) { return w >= 1000 ? Math.round(w).toLocaleString('en-US') : '' + Math.round(w * 10) / 10; }
  function refresh() {
    var el = document.getElementById('htdc-read'); if (!el) return;
    if (ST.err) { el.textContent = 'intervals unavailable'; return; }
    var P = pay(), S = window.__htS;
    if (!P || !S) { el.textContent = ST.data ? '' : 'loading intervals…'; return; }
    var name = P.models[S.model];
    if (!ST.on) { el.textContent = name + ' · DACP off'; return; }
    var row = (SUM[P.site] || {})[name]; var cell = row && row[String(ST.lvl)];
    if (!cell) { el.textContent = name + ' · no DACP summary'; return; }
    el.textContent = name + ' · ' + ST.lvl + '% DACP · test coverage ' + cell[0].toFixed(2) + ' · mean width ' + fmtW(cell[1]) + ' cfs' + (ST.data ? '' : ' · loading…');
  }
  function poke() { var el = document.getElementById('ht-date'); if (el) el.dispatchEvent(new Event('change')); }
  document.getElementById('htdc-on').addEventListener('change', function () { ST.on = this.checked; if (ST.on) load(); refresh(); poke(); });
  document.getElementById('htdc-lvl').addEventListener('change', function () { ST.lvl = +this.value; window.__dacpLabel = ST.lvl + '%'; refresh(); poke(); });
  var lastKey = '';
  setInterval(function () {
    if (!ST.data && !ST.err) load();
    var S = window.__htS; if (!S) return;
    var key = S.model + '|' + S.day + '|' + ST.on + '|' + ST.lvl + '|' + (ST.data ? 1 : 0) + '|' + ST.err;
    if (key !== lastKey) { lastKey = key; refresh(); }
  }, 700);
  load(); refresh();
})();
</script>
"""


def inject_block():
    return ("<script>\nwindow.__dacpSum = " + json.dumps(DACP_SUM, ensure_ascii=False, separators=(",", ":"))
            + ";\n</script>" + JS_BODY)


def patch_classic(s):
    if s.count(C_IV_OLD) != 1 or s.count(C_LEG_OLD) != 1 or s.count(C_LAB_OLD) != 2 or s.count(C_SM_OLD) != 1:
        return None
    s = s.replace(C_IV_OLD, C_IV_NEW, 1)
    s = s.replace(C_LEG_OLD, C_LEG_NEW, 1)
    s = s.replace(C_LAB_OLD, C_LAB_NEW)
    s = s.replace(C_SM_OLD, C_SM_NEW, 1)
    return s


def patch_3d(s):
    if s.count(D_QP_OLD) != 1 or s.count(D_FC_OLD) != 1 or s.count(D_LV_OLD) != 1:
        return None
    s = s.replace(D_QP_OLD, D_QP_NEW, 1)
    s = s.replace(D_FC_OLD, D_FC_NEW, 1)
    s = s.replace(D_LV_OLD, D_LV_NEW, 1)
    return s


def patch_page(s):
    if MARKER in s:
        return s
    is3d = "window.HT3D" in s
    out = patch_3d(s) if is3d else patch_classic(s)
    if out is None:
        return None
    if out.count("</body>") != 1:
        return None
    out = out.replace("</body>", inject_block() + "\n</body>", 1)
    if MARKER not in out or "__dacpIv" not in out:
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
    print(f"patch_dacp: {n_new} page(s) newly patched, {n_skip} already, "
          f"{n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
