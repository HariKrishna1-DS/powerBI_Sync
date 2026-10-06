import React from 'react';
import {Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
export default function ReportChart({rows, capacity = false}) {
  return <div className="report-chart" role="region" aria-label="Scrollable report chart" tabIndex={0}>
    <div style={{height: 320, minWidth: 640}}><ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{top: 12, right: 24, bottom: 8, left: 0}}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false}/>
        <XAxis dataKey="Date" tick={{fill: 'var(--muted)', fontSize: 11}}/>
        <YAxis allowDecimals={false} tick={{fill: 'var(--muted)', fontSize: 11}}/>
        <Tooltip contentStyle={{background: 'var(--surface)', color: 'var(--ink)', borderColor: 'var(--line)'}}/><Legend/>
        <Bar dataKey="Received" fill="var(--accent)" isAnimationActive={false} maxBarSize={34}/>
        <Bar dataKey="Completed" fill="var(--chart-blue)" isAnimationActive={false} maxBarSize={34}/>
        {capacity && <Line dataKey="Capacity" stroke="var(--warning)" strokeWidth={2} dot={false} isAnimationActive={false}/>}
        {capacity && <Line dataKey="Ext capacity" stroke="var(--chart-purple)" strokeWidth={2} dot={false} isAnimationActive={false}/>}
      </ComposedChart>
    </ResponsiveContainer></div>
  </div>;
}
