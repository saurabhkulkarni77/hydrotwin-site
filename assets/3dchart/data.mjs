/**
 * Hydrology calculations shared by the chart and the other Field Lab scenes.
 * This module has no Three.js or DOM dependency. Forecasts are supplied in the
 * dataset; these helpers compare them, not train a model. Missing values stay null.
 */
const MILLISECONDS_PER_DAY = 86_400_000;
const isFiniteNumber = (value) =>
  typeof value === 'number' && Number.isFinite(value);

/** Convert a daily array index to YYYY-MM-DD using UTC, avoiding DST shifts. */
export function dateAt(dataset, index) {
  const firstDay = Date.parse(dataset.start + 'T00:00:00Z');
  return new Date(firstDay + index * MILLISECONDS_PER_DAY)
    .toISOString()
    .slice(0, 10);
}

export function indexAt(dataset, date) {
  const firstDay = Date.parse(dataset.start + 'T00:00:00Z');
  return Math.round(
    (Date.parse(date + 'T00:00:00Z') - firstDay) / MILLISECONDS_PER_DAY,
  );
}

/**
 * Invert the supplied station-specific stage/discharge fit:
 *   Q = C * (stage - e)^b  =>  stage = e + exp((ln(Q) - ln(C)) / b).
 * Q is discharge in cfs; the resulting gauge-height estimate is in feet.
 * Do not extrapolate beyond the fit's documented discharge range.
 * Gauge height is not river depth or an absolute terrain elevation.
 */
export function stageForFlow(dataset, dischargeCfs) {
  const rating = dataset.rating;
  if (
    !rating ||
    !isFiniteNumber(dischargeCfs) ||
    dischargeCfs < rating.qmin ||
    dischargeCfs > rating.qmax
  ) {
    return null;
  }
  return rating.e + Math.exp((Math.log(dischargeCfs) - rating.lnC) / rating.b);
}

/**
 * Compare an earlier forecast with the observation for the SAME target day.
 * pred[model][lead - 1][issueIndex] is indexed by when the forecast was issued;
 * flow[issueIndex + lead] is indexed by when its predicted outcome occurred.
 */
export function getComparison(dataset, selection) {
  const issueIndex = selection.issueIndex;
  const targetIndex = issueIndex + selection.lead;
  if (
    issueIndex < 0 ||
    targetIndex >= dataset.n ||
    selection.lead < 1 ||
    selection.lead > 7
  ) {
    throw new RangeError('Target outside history');
  }
  const predictedCfs =
    dataset.pred[selection.modelIndex]?.[selection.lead - 1]?.[issueIndex] ?? null;
  const observedCfs = dataset.flow[targetIndex] ?? null;
  const targetDate = dateAt(dataset, targetIndex);
  const readings = dataset.stageObservations[targetDate] || [];
  const hasPair = isFiniteNumber(predictedCfs) && isFiniteNumber(observedCfs);

  return {
    issueIndex,
    targetIndex,
    issueDate: dateAt(dataset, issueIndex),
    targetDate,
    lead: selection.lead,
    modelName: dataset.models[selection.modelIndex],
    predictedCfs,
    observedCfs,
    signedErrorCfs: hasPair ? predictedCfs - observedCfs : null,
    absoluteErrorCfs: hasPair ? Math.abs(predictedCfs - observedCfs) : null,
    predictedStageFt: stageForFlow(dataset, predictedCfs),
    observedEstimatedStageFt: stageForFlow(dataset, observedCfs),
    // Actual packaged readings remain separate from rating-curve estimates.
    measuredStage: readings.length
      ? {
          ft: readings.reduce((total, reading) => total + reading.ft, 0) /
            readings.length,
          n: readings.length,
          statistic: 'mean of available instantaneous readings',
        }
      : null,
    heightMode: dataset.verticalReference.status,
  };
}

/** Environment readings available on the ISSUE date, not the target date. */
export function getInputSummary(dataset, issueIndex) {
  function rainfallTotal(days) {
    const values = dataset.precip.slice(
      Math.max(0, issueIndex - days + 1),
      issueIndex + 1,
    );
    // A partial window must not masquerade as a complete 3- or 7-day total.
    return {
      value: values.length === days && values.every(isFiniteNumber)
        ? values.reduce((total, value) => total + value, 0)
        : null,
      count: values.filter(isFiniteNumber).length,
    };
  }
  const { nrcs } = dataset;
  return {
    date: dateAt(dataset, issueIndex),
    temperature: dataset.tmean[issueIndex],
    rain3: rainfallTotal(3),
    rain7: rainfallTotal(7),
    soil2: nrcs.soil2[issueIndex],
    soil8: nrcs.soil8[issueIndex],
    soil20: nrcs.soil20[issueIndex],
    soilTemperature: nrcs.soilTemp2[issueIndex],
    soilStation: nrcs.soilStation,
    snowAvailable: nrcs.snowStations.some(Boolean),
    snowStations: nrcs.snowStations,
    snow1: nrcs.snow1SWE?.[issueIndex] ?? null,
    snow2: nrcs.snow2SWE?.[issueIndex] ?? null,
    snow3: nrcs.snow3SWE?.[issueIndex] ?? null,
  };
}

/** Largest available observation and forecast within one 7-day forecast run. */
export function getEventSummary(dataset, issueIndex, modelIndex = 0) {
  const observed = [];
  const predicted = [];
  for (let lead = 1; lead <= 7 && issueIndex + lead < dataset.n; lead++) {
    const observation = dataset.flow[issueIndex + lead];
    if (isFiniteNumber(observation)) observed.push({ lead, value: observation });
    const prediction = dataset.pred[modelIndex][lead - 1][issueIndex];
    if (isFiniteNumber(prediction)) predicted.push({ lead, value: prediction });
  }
  const maximum = (items) => items.length
    ? items.reduce((largest, item) => largest.value >= item.value ? largest : item)
    : null;
  return { observedPeak: maximum(observed), predictedPeak: maximum(predicted) };
}

/** Rolling absolute error over up to 30 issue dates, for each supplied model. */
export function getModelSummary(dataset, selection) {
  return dataset.models.map((model, modelIndex) => {
    let totalError = 0;
    let count = 0;
    for (
      let index = Math.max(0, selection.issueIndex - 29);
      index <= selection.issueIndex;
      index++
    ) {
      const prediction = dataset.pred[modelIndex][selection.lead - 1][index];
      const observation = dataset.flow[index + selection.lead];
      if (isFiniteNumber(prediction) && isFiniteNumber(observation)) {
        totalError += Math.abs(prediction - observation);
        count++;
      }
    }
    return {
      model,
      prediction:
        dataset.pred[modelIndex][selection.lead - 1][selection.issueIndex] ?? null,
      mae: count ? totalError / count : null,
      count,
    };
  });
}

export function riverSummary(dataset, comparison) {
  const discharge = comparison.observedCfs;
  const previous = dataset.flow[comparison.targetIndex - 1];
  const history = dataset.flow.filter(isFiniteNumber);
  const hasPair = isFiniteNumber(discharge) && isFiniteNumber(previous);
  return {
    change: hasPair ? discharge - previous : null,
    changePercent: hasPair && previous !== 0
      ? (discharge - previous) / previous * 100
      : null,
    percentile: isFiniteNumber(discharge)
      ? history.filter((value) => value <= discharge).length / history.length * 100
      : null,
  };
}
