# Illustrative financial model

The calculator accepts monthly volume, eligibility and success rates, manual and reviewed handling minutes, loaded labor rate, AI cost per eligible request, monthly infrastructure and maintenance, and implementation cost. All inputs are illustrative and editable; they are not saved.

Conservative, Base and Optimistic are illustrative editable presets, not validated forecasts. Export includes assumptions, formula description and results.

Annual eligible = volume × 12 × eligibility. Annual hours saved = eligible × success × (manual − review) / 60. Annual labor savings = hours × hourly cost. Annual recurring cost = eligible × AI cost + 12 × (infrastructure + maintenance). Annual net benefit = labor savings − recurring cost; first-year benefit subtracts implementation cost. ROI = first-year benefit / (recurring + implementation) × 100; it is unavailable if the denominator is zero. Payback in months = implementation / positive annual net benefit × 12, otherwise unavailable. Calculations use Decimal and can yield negative savings. The AI cost assumes one billable call per eligible request; retry, training, quality assurance, change management and taxes are excluded unless included in the supplied inputs.
