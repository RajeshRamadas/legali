export type UsageSummary = { attempts:number; succeeded:number; failed:number; unfinished:number; usage_reported:number; input_tokens:number|null; output_tokens:number|null; known_estimated_usd:string|null; unpriced_attempts:number; average_duration_ms:number|null };

export function estimatedCost(value:string|null) {
  if (value === null) return "Unavailable";
  const number=Number(value);
  if (number>0 && number<0.000001) return "< $0.000001 USD";
  return `$${number.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:6})} USD`;
}

export default function VerificationUsageSummary({usage}:{usage:UsageSummary}) {
  if (!usage.attempts) return <p>No provider attempts recorded.</p>;
  return <div className="verification-usage-summary">
    <p>{usage.attempts} provider {usage.attempts===1?"attempt":"attempts"} · {usage.succeeded} succeeded · {usage.failed} failed · {usage.unfinished} unfinished</p>
    <p>Reported tokens: {usage.input_tokens===null?"unavailable":`${usage.input_tokens.toLocaleString("en-IN")} input · ${usage.output_tokens?.toLocaleString("en-IN")} output`} ({usage.usage_reported} of {usage.attempts} attempts).</p>
    <p>Known estimated cost: <strong>{estimatedCost(usage.known_estimated_usd)}</strong>. {usage.unpriced_attempts} {usage.unpriced_attempts===1?"attempt has":"attempts have"} no estimate.</p>
    {usage.average_duration_ms!==null&&<p>Average completed attempt time: {(usage.average_duration_ms/1000).toLocaleString("en-IN",{maximumFractionDigits:2})} seconds.</p>}
    {!!usage.unfinished&&<p>Unfinished attempts have unknown outcomes and may have incurred provider charges.</p>}
    <p>Estimates use configured rates and are not a provider invoice. Failed or cancelled analysis may still incur charges.</p>
  </div>;
}
