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
DACP_SUM = {'01463500': {'LSTM': {'70': [0.6961, 4597.11], '80': [0.7975, 6115.62], '90': [0.8958, 9312.96], '95': [0.9363, 11034.81]}, 'Transformer': {'70': [0.6982, 5556.68], '80': [0.7979, 7222.88], '90': [0.8955, 10278.84], '95': [0.9378, 12728.33]}, 'TFT': {'70': [0.6935, 5419.75], '80': [0.796, 7026.74], '90': [0.896, 10315.7], '95': [0.9365, 12776.59]}, 'PatchTST': {'70': [0.6976, 5731.65], '80': [0.7971, 7703.81], '90': [0.896, 11179.5], '95': [0.9378, 13334.65]}, 'PILSTMv1': {'70': [0.6965, 4931.61], '80': [0.799, 6367.22], '90': [0.8958, 9468.01], '95': [0.9352, 11776.51]}, 'GCN': {'70': [0.7018, 6083.66], '80': [0.8012, 8173.12], '90': [0.896, 11508.72], '95': [0.9346, 14002.16]}, 'GP Matérn': {'70': [0.7001, 6093.78], '80': [0.8005, 8004.72], '90': [0.897, 11622.44], '95': [0.9361, 14133.92]}, 'GP RBF': {'70': [0.7001, 6046.58], '80': [0.8001, 7810.47], '90': [0.8968, 11601.95], '95': [0.9365, 14044.6]}, 'ARIMA': {'70': [0.6976, 26042.59], '80': [0.7947, 28732.86], '90': [0.8747, 32167.23], '95': [0.9086, 34913.86]}, 'SARIMA': {'70': [0.6973, 25731.31], '80': [0.7947, 28406.66], '90': [0.8745, 31785.72], '95': [0.9071, 34582.0]}}, '01646500': {'LSTM': {'70': [0.6999, 4447.25], '80': [0.7985, 6490.71], '90': [0.8916, 9099.63], '95': [0.93, 11702.93]}, 'Transformer': {'70': [0.7005, 4633.77], '80': [0.7985, 6392.8], '90': [0.8916, 9544.94], '95': [0.9318, 11493.35]}, 'TFT': {'70': [0.7064, 6693.56], '80': [0.8015, 8239.45], '90': [0.8953, 11769.83], '95': [0.9324, 13972.85]}, 'PatchTST': {'70': [0.706, 9765.95], '80': [0.7997, 11814.97], '90': [0.8884, 16017.45], '95': [0.9265, 18628.11]}, 'PILSTMv1': {'70': [0.6981, 4712.87], '80': [0.7987, 6404.46], '90': [0.892, 9175.88], '95': [0.9308, 11429.51]}, 'GCN': {'70': [0.7003, 5072.2], '80': [0.7995, 7633.56], '90': [0.8904, 11296.25], '95': [0.9304, 13233.26]}, 'GP Matérn': {'70': [0.7009, 5706.71], '80': [0.7981, 7809.6], '90': [0.89, 11947.68], '95': [0.9292, 13508.55]}, 'GP RBF': {'70': [0.7007, 5609.57], '80': [0.7979, 7702.1], '90': [0.89, 12282.45], '95': [0.9294, 14058.59]}, 'ARIMA': {'70': [0.7084, 35996.75], '80': [0.7995, 40125.46], '90': [0.8866, 43709.26], '95': [0.9257, 47132.67]}, 'SARIMA': {'70': [0.7084, 35235.53], '80': [0.7993, 39289.27], '90': [0.8864, 42835.44], '95': [0.9257, 46244.94]}}, '02320500': {'LSTM': {'70': [0.69, 437.6], '80': [0.7973, 594.05], '90': [0.8949, 895.17], '95': [0.935, 1055.29]}, 'Transformer': {'70': [0.6926, 491.67], '80': [0.7979, 647.08], '90': [0.8964, 931.95], '95': [0.9367, 1083.42]}, 'TFT': {'70': [0.687, 459.67], '80': [0.796, 606.43], '90': [0.8964, 873.15], '95': [0.9376, 984.71]}, 'PatchTST': {'70': [0.6939, 626.82], '80': [0.8001, 819.28], '90': [0.8966, 1105.8], '95': [0.9387, 1219.12]}, 'PILSTMv1': {'70': [0.6898, 424.96], '80': [0.7964, 577.36], '90': [0.894, 855.71], '95': [0.9341, 1022.57]}, 'GCN': {'70': [0.698, 571.78], '80': [0.7992, 807.34], '90': [0.8975, 1200.48], '95': [0.9391, 1407.46]}, 'GP Matérn': {'70': [0.692, 394.39], '80': [0.7982, 582.06], '90': [0.897, 926.19], '95': [0.9372, 1104.0]}, 'GP RBF': {'70': [0.6931, 399.53], '80': [0.7986, 580.0], '90': [0.896, 939.18], '95': [0.9367, 1105.56]}, 'ARIMA': {'70': [0.6935, 6139.24], '80': [0.7711, 6497.34], '90': [0.8503, 6678.28], '95': [0.8863, 6818.88]}, 'SARIMA': {'70': [0.6928, 6165.07], '80': [0.7707, 6522.3], '90': [0.8496, 6702.63], '95': [0.8855, 6843.66]}}, '03294500': {'LSTM': {'70': [0.6933, 87401.36], '80': [0.7935, 108900.51], '90': [0.8914, 146181.7], '95': [0.9261, 164106.01]}, 'Transformer': {'70': [0.6983, 109905.41], '80': [0.7989, 136480.3], '90': [0.8941, 170605.32], '95': [0.931, 191281.84]}, 'TFT': {'70': [0.696, 97933.62], '80': [0.7992, 124756.03], '90': [0.8941, 160761.55], '95': [0.9318, 177614.65]}, 'PatchTST': {'70': [0.6956, 82474.3], '80': [0.7989, 102675.58], '90': [0.8933, 140868.04], '95': [0.9265, 159202.36]}, 'PILSTMv1': {'70': [0.7036, 80714.91], '80': [0.8015, 103679.13], '90': [0.8956, 143621.51], '95': [0.9299, 158909.9]}, 'GCN': {'70': [0.6918, 123118.49], '80': [0.7939, 155553.81], '90': [0.893, 199715.84], '95': [0.9299, 217409.11]}, 'GP Matérn': {'70': [0.6922, 94420.71], '80': [0.7958, 121793.15], '90': [0.8945, 166391.89], '95': [0.9341, 191050.46]}, 'GP RBF': {'70': [0.6933, 94733.63], '80': [0.7947, 126567.91], '90': [0.8952, 176791.41], '95': [0.9333, 193353.68]}, 'ARIMA': {'70': [0.7044, 231673.82], '80': [0.7973, 298169.61], '90': [0.8941, 384248.32], '95': [0.9394, 415222.75]}, 'SARIMA': {'70': [0.7044, 231673.82], '80': [0.7973, 298169.61], '90': [0.8941, 384248.32], '95': [0.9394, 415222.75]}}, '05331000': {'LSTM': {'70': [0.6863, 3925.47], '80': [0.7907, 5013.01], '90': [0.8885, 6536.73], '95': [0.9272, 7711.49]}, 'Transformer': {'70': [0.6927, 3946.65], '80': [0.7937, 4846.28], '90': [0.8891, 6276.55], '95': [0.9268, 7610.18]}, 'TFT': {'70': [0.6878, 3521.07], '80': [0.7915, 4461.74], '90': [0.8868, 5937.74], '95': [0.9251, 6724.62]}, 'PatchTST': {'70': [0.6874, 3542.04], '80': [0.792, 4555.94], '90': [0.8878, 5943.89], '95': [0.9255, 7011.69]}, 'PILSTMv1': {'70': [0.6876, 3805.98], '80': [0.7911, 4824.11], '90': [0.8893, 6348.13], '95': [0.9289, 7510.86]}, 'GCN': {'70': [0.6931, 4596.74], '80': [0.7943, 5940.01], '90': [0.8883, 7585.18], '95': [0.9274, 8606.04]}, 'GP Matérn': {'70': [0.6916, 4323.85], '80': [0.7951, 5631.27], '90': [0.8897, 7878.96], '95': [0.9287, 9080.61]}, 'GP RBF': {'70': [0.6914, 4396.69], '80': [0.7949, 5659.81], '90': [0.8908, 7894.78], '95': [0.9289, 9139.76]}, 'ARIMA': {'70': [0.6832, 20263.39], '80': [0.7888, 22401.68], '90': [0.8766, 24801.24], '95': [0.913, 25881.9]}, 'SARIMA': {'70': [0.6832, 20263.39], '80': [0.7888, 22401.68], '90': [0.8766, 24801.24], '95': [0.913, 25881.9]}}, '06214500': {'LSTM': {'70': [0.6996, 1630.68], '80': [0.7997, 2143.42], '90': [0.891, 2676.7], '95': [0.9263, 3009.92]}, 'Transformer': {'70': [0.7028, 1805.96], '80': [0.8013, 2349.06], '90': [0.8935, 2966.7], '95': [0.9295, 3365.71]}, 'TFT': {'70': [0.6992, 1590.95], '80': [0.7999, 2096.88], '90': [0.8926, 2671.6], '95': [0.9304, 3008.68]}, 'PatchTST': {'70': [0.7008, 2001.56], '80': [0.8006, 2589.62], '90': [0.8919, 3572.55], '95': [0.9311, 3986.69]}, 'PILSTMv1': {'70': [0.7031, 1639.87], '80': [0.8013, 2130.71], '90': [0.8938, 2692.98], '95': [0.932, 3014.96]}, 'GCN': {'70': [0.7088, 3479.71], '80': [0.8063, 4353.78], '90': [0.8897, 4942.61], '95': [0.9217, 5250.26]}, 'GP Matérn': {'70': [0.7056, 2813.05], '80': [0.8043, 3655.46], '90': [0.8917, 4388.41], '95': [0.9272, 4967.81]}, 'GP RBF': {'70': [0.7047, 2853.29], '80': [0.8033, 3705.28], '90': [0.8894, 4435.94], '95': [0.927, 5080.98]}, 'ARIMA': {'70': [0.6646, 13155.71], '80': [0.7457, 13849.02], '90': [0.8276, 14839.84], '95': [0.8645, 15645.86]}, 'SARIMA': {'70': [0.6646, 13112.11], '80': [0.7457, 13787.39], '90': [0.8276, 14793.24], '95': [0.8647, 15597.82]}}, '06934500': {'LSTM': {'70': [0.706, 28069.27], '80': [0.8056, 36797.23], '90': [0.8929, 48223.42], '95': [0.9278, 55460.48]}, 'Transformer': {'70': [0.7072, 31895.35], '80': [0.8052, 41493.3], '90': [0.8914, 54429.66], '95': [0.928, 60996.83]}, 'TFT': {'70': [0.6997, 24372.83], '80': [0.8019, 31668.11], '90': [0.8935, 42615.41], '95': [0.9294, 47693.35]}, 'PatchTST': {'70': [0.6981, 22666.62], '80': [0.7987, 28674.94], '90': [0.8929, 38919.93], '95': [0.932, 45041.41]}, 'PILSTMv1': {'70': [0.7054, 26875.48], '80': [0.8052, 35114.3], '90': [0.8933, 47694.22], '95': [0.9294, 54953.65]}, 'GCN': {'70': [0.7119, 38298.58], '80': [0.8095, 50787.85], '90': [0.8943, 65020.43], '95': [0.9286, 72042.39]}, 'GP Matérn': {'70': [0.7088, 33241.77], '80': [0.8064, 43475.77], '90': [0.8949, 57330.57], '95': [0.9306, 67896.36]}, 'GP RBF': {'70': [0.7086, 33547.61], '80': [0.8062, 44988.44], '90': [0.8941, 58674.67], '95': [0.9294, 68456.88]}, 'ARIMA': {'70': [0.6974, 111485.69], '80': [0.7985, 125168.66], '90': [0.8847, 136236.68], '95': [0.916, 141854.53]}, 'SARIMA': {'70': [0.6974, 111485.69], '80': [0.7985, 125168.66], '90': [0.8847, 136236.68], '95': [0.916, 141854.53]}}, '07374000': {'LSTM': {'70': [0.6961, 67319.12], '80': [0.7975, 83445.62], '90': [0.896, 107978.94], '95': [0.9369, 121144.02]}, 'Transformer': {'70': [0.6993, 66704.66], '80': [0.8003, 81017.82], '90': [0.8947, 104908.32], '95': [0.9359, 120862.65]}, 'TFT': {'70': [0.6939, 55589.5], '80': [0.7947, 68974.98], '90': [0.896, 85933.51], '95': [0.9365, 98342.2]}, 'PatchTST': {'70': [0.6961, 61575.56], '80': [0.7975, 76780.21], '90': [0.896, 97027.09], '95': [0.9374, 110461.57]}, 'PILSTMv1': {'70': [0.6963, 67753.11], '80': [0.7975, 82679.71], '90': [0.8962, 104491.22], '95': [0.9372, 116280.37]}, 'GCN': {'70': [0.695, 109067.38], '80': [0.7952, 133938.82], '90': [0.8949, 168706.75], '95': [0.9354, 177996.39]}, 'GP Matérn': {'70': [0.6993, 75899.54], '80': [0.7984, 94767.39], '90': [0.8938, 123242.93], '95': [0.9348, 138020.37]}, 'GP RBF': {'70': [0.6982, 77535.28], '80': [0.7979, 93991.41], '90': [0.8932, 122697.86], '95': [0.9346, 136084.36]}, 'ARIMA': {'70': [0.6686, 615113.7], '80': [0.7447, 688983.83], '90': [0.8275, 735626.73], '95': [0.8696, 761046.78]}, 'SARIMA': {'70': [0.6686, 615029.73], '80': [0.7445, 691691.96], '90': [0.8275, 735525.79], '95': [0.8696, 760947.12]}}, '08057000': {'LSTM': {'70': [0.7205, 2306.32], '80': [0.8162, 3183.95], '90': [0.9034, 5037.21], '95': [0.9363, 6991.75]}, 'Transformer': {'70': [0.7196, 2456.83], '80': [0.8156, 3332.82], '90': [0.9034, 5767.58], '95': [0.9363, 7347.64]}, 'TFT': {'70': [0.7203, 2331.03], '80': [0.8167, 3069.75], '90': [0.9038, 4863.49], '95': [0.9356, 6687.69]}, 'PatchTST': {'70': [0.7222, 2516.71], '80': [0.8189, 3632.14], '90': [0.9087, 6893.08], '95': [0.9414, 9000.16]}, 'PILSTMv1': {'70': [0.7169, 2347.46], '80': [0.8134, 3163.67], '90': [0.9027, 5017.83], '95': [0.9348, 6477.19]}, 'GCN': {'70': [0.7264, 2747.94], '80': [0.8198, 3740.93], '90': [0.906, 5866.59], '95': [0.9394, 8437.72]}, 'GP Matérn': {'70': [0.7196, 2699.4], '80': [0.8149, 4022.61], '90': [0.9045, 6703.07], '95': [0.9374, 8671.47]}, 'GP RBF': {'70': [0.7207, 2756.25], '80': [0.8173, 4069.51], '90': [0.906, 6526.56], '95': [0.939, 8459.8]}, 'ARIMA': {'70': [0.6776, 10159.71], '80': [0.7899, 11751.11], '90': [0.8888, 14113.93], '95': [0.9275, 16158.78]}, 'SARIMA': {'70': [0.6776, 10196.39], '80': [0.7899, 11814.41], '90': [0.8888, 14225.04], '95': [0.927, 16178.16]}}, '08158000': {'LSTM': {'70': [0.7092, 313.0], '80': [0.8056, 444.18], '90': [0.9016, 784.76], '95': [0.9387, 903.92]}, 'Transformer': {'70': [0.709, 296.15], '80': [0.806, 408.46], '90': [0.9018, 971.39], '95': [0.9401, 1070.76]}, 'TFT': {'70': [0.7054, 285.15], '80': [0.8054, 405.15], '90': [0.9014, 699.78], '95': [0.9391, 814.87]}, 'PatchTST': {'70': [0.7072, 334.67], '80': [0.8056, 456.15], '90': [0.9008, 1215.21], '95': [0.9369, 1493.18]}, 'PILSTMv1': {'70': [0.71, 298.22], '80': [0.8062, 421.71], '90': [0.9022, 789.94], '95': [0.9401, 916.09]}, 'GCN': {'70': [0.7056, 333.05], '80': [0.8056, 462.88], '90': [0.9018, 1166.56], '95': [0.9399, 1380.78]}, 'GP Matérn': {'70': [0.707, 377.5], '80': [0.8068, 567.05], '90': [0.9016, 1513.89], '95': [0.9369, 1820.15]}, 'GP RBF': {'70': [0.7076, 376.61], '80': [0.807, 542.87], '90': [0.902, 1493.9], '95': [0.9383, 1804.37]}, 'ARIMA': {'70': [0.7088, 1127.71], '80': [0.8056, 1335.46], '90': [0.902, 1611.85], '95': [0.9436, 1868.53]}, 'SARIMA': {'70': [0.6976, 1022.39], '80': [0.8009, 1295.46], '90': [0.8975, 1562.06], '95': [0.9397, 1798.14]}}, '08313000': {'LSTM': {'70': [0.6828, 252.84], '80': [0.7894, 339.18], '90': [0.8872, 461.69], '95': [0.9265, 528.29]}, 'Transformer': {'70': [0.6818, 218.32], '80': [0.791, 287.51], '90': [0.8896, 397.19], '95': [0.9296, 457.62]}, 'TFT': {'70': [0.6859, 223.22], '80': [0.7896, 284.6], '90': [0.8904, 391.55], '95': [0.929, 457.27]}, 'PatchTST': {'70': [0.6816, 210.98], '80': [0.7904, 276.51], '90': [0.8884, 381.8], '95': [0.9274, 440.22]}, 'PILSTMv1': {'70': [0.6824, 244.21], '80': [0.7898, 329.44], '90': [0.888, 449.34], '95': [0.9263, 519.48]}, 'GCN': {'70': [0.6812, 249.17], '80': [0.79, 334.88], '90': [0.8892, 445.75], '95': [0.9294, 528.86]}, 'GP Matérn': {'70': [0.6814, 274.25], '80': [0.79, 358.68], '90': [0.8866, 467.19], '95': [0.9243, 530.91]}, 'GP RBF': {'70': [0.6814, 272.41], '80': [0.7902, 365.72], '90': [0.8864, 481.64], '95': [0.9249, 549.0]}, 'ARIMA': {'70': [0.6999, 897.73], '80': [0.7991, 1008.31], '90': [0.8856, 1075.48], '95': [0.9205, 1110.81]}, 'SARIMA': {'70': [0.6999, 898.12], '80': [0.7991, 1008.97], '90': [0.8856, 1076.13], '95': [0.9205, 1111.4]}}, '09380000': {'LSTM': {'70': [0.6982, 1068.14], '80': [0.8017, 1402.14], '90': [0.8991, 1889.89], '95': [0.939, 2195.57]}, 'Transformer': {'70': [0.7027, 1038.05], '80': [0.8045, 1356.22], '90': [0.8998, 1909.42], '95': [0.9407, 2272.01]}, 'TFT': {'70': [0.7106, 912.93], '80': [0.8066, 1166.99], '90': [0.9017, 1698.81], '95': [0.9428, 2002.21]}, 'PatchTST': {'70': [0.7046, 922.28], '80': [0.8025, 1252.18], '90': [0.8972, 1784.84], '95': [0.9377, 2105.95]}, 'PILSTMv1': {'70': [0.6995, 1091.27], '80': [0.8015, 1407.0], '90': [0.8991, 1881.62], '95': [0.9387, 2209.79]}, 'GCN': {'70': [0.7096, 1222.5], '80': [0.8072, 1559.32], '90': [0.9023, 2108.35], '95': [0.9413, 2424.09]}, 'GP Matérn': {'70': [0.7111, 1152.73], '80': [0.8092, 1536.85], '90': [0.8993, 2110.64], '95': [0.9402, 2409.72]}, 'GP RBF': {'70': [0.7132, 1135.02], '80': [0.8109, 1486.69], '90': [0.9038, 1979.12], '95': [0.9417, 2325.77]}, 'ARIMA': {'70': [0.7025, 2927.98], '80': [0.7989, 3181.9], '90': [0.8882, 3486.61], '95': [0.9263, 3611.19]}, 'SARIMA': {'70': [0.7031, 2869.78], '80': [0.8008, 3157.6], '90': [0.8918, 3470.64], '95': [0.9278, 3594.89]}}, '11447650': {'LSTM': {'70': [0.7177, 6048.0], '80': [0.8137, 8161.3], '90': [0.9022, 10893.51], '95': [0.9357, 12191.54]}, 'Transformer': {'70': [0.7212, 6721.69], '80': [0.8157, 8474.33], '90': [0.9067, 12152.4], '95': [0.9409, 15107.19]}, 'TFT': {'70': [0.7165, 5696.03], '80': [0.8117, 7636.2], '90': [0.9024, 11568.12], '95': [0.9401, 13643.1]}, 'PatchTST': {'70': [0.7153, 6447.5], '80': [0.8113, 8901.24], '90': [0.9032, 13430.89], '95': [0.9407, 17279.94]}, 'PILSTMv1': {'70': [0.7173, 5869.81], '80': [0.8127, 8160.1], '90': [0.9032, 10898.57], '95': [0.9381, 12175.07]}, 'GCN': {'70': [0.7198, 7312.23], '80': [0.8157, 10186.6], '90': [0.9034, 16497.2], '95': [0.9391, 19231.62]}, 'GP Matérn': {'70': [0.7198, 7352.85], '80': [0.8145, 10416.63], '90': [0.9048, 16457.38], '95': [0.9409, 19838.31]}, 'GP RBF': {'70': [0.721, 7553.59], '80': [0.8168, 10453.43], '90': [0.9054, 16677.16], '95': [0.9409, 19597.21]}, 'ARIMA': {'70': [0.7206, 35988.92], '80': [0.8143, 42152.47], '90': [0.8922, 45996.43], '95': [0.9274, 47995.83]}, 'SARIMA': {'70': [0.7206, 35988.92], '80': [0.8143, 42152.47], '90': [0.8922, 45996.43], '95': [0.9274, 47995.83]}}, '14105700': {'LSTM': {'70': [0.708, 31754.47], '80': [0.8078, 40616.69], '90': [0.8972, 51889.69], '95': [0.9311, 57969.92]}, 'Transformer': {'70': [0.711, 35115.7], '80': [0.8072, 43527.37], '90': [0.8958, 53996.93], '95': [0.9295, 59350.63]}, 'TFT': {'70': [0.7104, 32953.82], '80': [0.8078, 42085.56], '90': [0.8955, 52164.13], '95': [0.9279, 57645.56]}, 'PatchTST': {'70': [0.7135, 38622.74], '80': [0.8102, 49612.28], '90': [0.8943, 62302.46], '95': [0.9266, 69535.22]}, 'PILSTMv1': {'70': [0.7102, 31865.14], '80': [0.808, 41227.95], '90': [0.8964, 51296.05], '95': [0.9295, 57537.02]}, 'GCN': {'70': [0.7092, 36542.83], '80': [0.8063, 45402.8], '90': [0.8947, 56790.16], '95': [0.9283, 62401.02]}, 'GP Matérn': {'70': [0.7094, 36786.99], '80': [0.8065, 47100.02], '90': [0.8966, 58890.84], '95': [0.9317, 64885.27]}, 'GP RBF': {'70': [0.7094, 37595.99], '80': [0.8072, 47180.11], '90': [0.896, 58610.29], '95': [0.9295, 64963.67]}, 'ARIMA': {'70': [0.6761, 82923.41], '80': [0.7726, 94333.05], '90': [0.8606, 109462.57], '95': [0.8988, 121131.5]}, 'SARIMA': {'70': [0.6761, 83747.34], '80': [0.7744, 95207.51], '90': [0.861, 110024.26], '95': [0.8992, 120929.9]}}}

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


def _scan_obj(s, j):
    depth, k, in_str, esc = 0, j, False, False
    while k < len(s):
        c = s[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j, k + 1
        k += 1
    return None


def refresh_sum(s):
    """Replace the baked window.__dacpSum literal with the current DACP_SUM
    (drift fix: marked pages keep their panel code; only the summary table
    is refreshed so it always matches the served models)."""
    i = s.find("window.__dacpSum = ")
    if i == -1:
        return s
    j = s.find("{", i)
    if j == -1:
        return s
    span = _scan_obj(s, j)
    if span is None:
        return s
    a, b = span
    return s[:a] + json.dumps(DACP_SUM, ensure_ascii=False, separators=(",", ":")) + s[b:]


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
    n_new = n_skip = n_warn = n_ref = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if MARKER in s:
            out = refresh_sum(s)
            if out != s:
                p.write_text(out, encoding="utf-8")
                n_ref += 1
                print(f"sum refreshed: {p.name}")
            else:
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
    print(f"patch_dacp: {n_new} page(s) newly patched, {n_ref} sum-refreshed, "
          f"{n_skip} already, {n_warn} skipped-with-warning, {len(pages)} pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
