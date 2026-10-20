/** Pure chart data adapter: no Three.js or DOM dependency. */
import { dateAt, getComparison, getInputSummary } from './data.mjs';

/**
 * Z-axis choices share one definition for label, unit, and data accessor.
 * To add a variable, add an entry here and expose its key in the host selector.
 * Soil depths (2/8/20 in) are sensor depths, not reading units (%).
 * Snow is SWE: the depth of liquid water contained in snow, in inches.
 */
export const graphVariables = {
  rain7: { title: '7-day rainfall', unit: 'mm', value: (input) => input.rain7.value },
  rain3: { title: '3-day rainfall', unit: 'mm', value: (input) => input.rain3.value },
  soil2: { title: 'Soil moisture · 2 in', unit: '%', value: (input) => input.soil2 },
  soil8: { title: 'Soil moisture · 8 in', unit: '%', value: (input) => input.soil8 },
  soil20: { title: 'Soil moisture · 20 in', unit: '%', value: (input) => input.soil20 },
  temperature: { title: 'Mean temperature', unit: '°C', value: (input) => input.temperature },
  snow: { title: 'Snow water equivalent · station 1', unit: 'in', value: (input) => input.snow1 },
  snow2: { title: 'Snow water equivalent · station 2', unit: 'in', value: (input) => input.snow2 },
  snow3: { title: 'Snow water equivalent · station 3', unit: 'in', value: (input) => input.snow3 },
};

/**
 * Build one sample per issue day, with inclusive start/end indices.
 * X = target date, Y = predicted/observed-flow gauge-height estimates,
 * Z = selected environment reading on the earlier ISSUE date.
 * Fixed lead makes issue-day spacing identical to target-day spacing.
 * Using issue-date inputs avoids future-information leakage.
 * These paths show association; they do not establish a causal effect.
 */
export function graphSamples(dataset, selection, variable, start, end) {
  const definition = graphVariables[variable];
  if (!definition) throw new RangeError('Graph variable unavailable');

  return Array.from({ length: Math.max(0, end - start + 1) }, (_, offset) => {
    const issueIndex = start + offset;
    const comparison = getComparison(dataset, { ...selection, issueIndex });
    const input = definition.value(getInputSummary(dataset, issueIndex));
    return {
      issueIndex,
      issueDate: dateAt(dataset, issueIndex),
      targetDate: comparison.targetDate,
      input: Number.isFinite(input) ? input : null,
      predictedStage: comparison.predictedStageFt,
      observedStage: comparison.observedEstimatedStageFt,
      predictedCfs: comparison.predictedCfs,
      observedCfs: comparison.observedCfs,
    };
  });
}
