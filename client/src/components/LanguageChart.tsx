import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';

interface LanguageChartProps {
  languages: {
    [key: string]: {
      count: number;
      lines: number;
    };
  };
}

const LANGUAGE_COLORS: { [key: string]: string } = {
  'Python': '#3572A5',
  'JavaScript': '#f1e05a',
  'TypeScript': '#2b7489',
  'Java': '#b07219',
  'C++': '#f34b7d',
  'C': '#555555',
  'Go': '#00ADD8',
  'Rust': '#dea584',
  'Ruby': '#701516',
  'PHP': '#4F5D95',
  'HTML': '#e34c26',
  'CSS': '#563d7c',
  'SCSS': '#c6538c',
  'Markdown': '#083fa1',
  'JSON': '#292929',
  'YAML': '#cb171e',
  'Shell': '#89e051',
  'Dockerfile': '#384d54',
};

const getColor = (language: string, index: number): string => {
  if (LANGUAGE_COLORS[language]) {
    return LANGUAGE_COLORS[language];
  }
  // Generate consistent colors for unknown languages
  const colors = ['#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444'];
  return colors[index % colors.length];
};

export default function LanguageChart({ languages }: LanguageChartProps) {
  if (!languages || Object.keys(languages).length === 0) {
    return null;
  }

  const data = Object.entries(languages)
    .map(([name, stats]) => ({
      name,
      value: stats.lines,
      count: stats.count,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10); // Top 10 languages

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg p-3 shadow-lg">
          <p className="font-semibold text-slate-900 dark:text-white">{data.name}</p>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Lines: {data.value.toLocaleString()}
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Files: {data.count}
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-[400px]">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            outerRadius={120}
            fill="#8884d8"
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getColor(entry.name, index)} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value, entry: any) => (
              <span className="text-sm text-slate-700 dark:text-slate-300">
                {value} ({entry.payload.value.toLocaleString()} lines)
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
