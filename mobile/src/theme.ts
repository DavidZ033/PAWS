export const colors = {
  background: '#11151c',
  card: '#1c232e',
  border: '#2c3645',
  text: '#f2f4f8',
  muted: '#8f9bb0',
  primary: '#4f9dff',
  good: '#3ecf8e',
  warn: '#f5b83d',
  danger: '#ef4b4b',
};

export const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function timeAgo(unixSeconds: number | null | undefined): string {
  if (!unixSeconds) return 'never';
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - unixSeconds));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function formatDays(days: number[]): string {
  if (days.length === 0 || days.length === 7) return 'Every day';
  if (days.join() === '0,1,2,3,4') return 'Weekdays';
  if (days.join() === '5,6') return 'Weekends';
  return days.map((d) => DAY_LABELS[d]).join(', ');
}
