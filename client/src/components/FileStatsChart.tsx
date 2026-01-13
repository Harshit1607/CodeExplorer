import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface FileStatsChartProps {
  languages: {
    [key: string]: {
      count: number;
      lines: number;
    };
  };
}

export default function FileStatsChart({ languages }: FileStatsChartProps) {
  if (!languages || Object.keys(languages).length === 0) {
    return null;
  }

  const data = Object.entries(languages)
    .map(([name, stats]) => ({
      name,
      files: stats.count,
      lines: stats.lines,
    }))
    .sort((a, b) => b.lines - a.lines)
    .slice(0, 10); // Top 10 languages

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 shadow-lg">
          <p className="font-semibold text-slate-900 dark:text-white mb-2">{data.name}</p>
          <p className="text-sm text-blue-600 dark:text-blue-400">
            Files: {data.files.toLocaleString()}
          </p>
          <p className="text-sm text-purple-600 dark:text-purple-400">
            Lines: {data.lines.toLocaleString()}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full">
      <div className="mb-4">
        <h4 className="text-md font-semibold text-slate-900 dark:text-white mb-2">
          Language Statistics
        </h4>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Comparison of file count and lines of code across languages
        </p>
      </div>
      <div className="w-full h-[400px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis
              dataKey="name"
              angle={-45}
              textAnchor="end"
              height={80}
              tick={{ fill: '#64748b', fontSize: 12 }}
            />
            <YAxis
              yAxisId="left"
              tick={{ fill: '#64748b', fontSize: 12 }}
              label={{ value: 'Files', angle: -90, position: 'insideLeft', fill: '#64748b' }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fill: '#64748b', fontSize: 12 }}
              label={{ value: 'Lines', angle: 90, position: 'insideRight', fill: '#64748b' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="square"
            />
            <Bar
              yAxisId="left"
              dataKey="files"
              fill="#3b82f6"
              name="Files"
              radius={[8, 8, 0, 0]}
            />
            <Bar
              yAxisId="right"
              dataKey="lines"
              fill="#8b5cf6"
              name="Lines of Code"
              radius={[8, 8, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
