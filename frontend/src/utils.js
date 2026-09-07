export function bytes(value = 0) {
  if (!value) return '۰ بایت'
  const units = ['بایت', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  const number = value / 1024 ** index
  return `${new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(number)} ${units[index]}`
}

export function number(value = 0) {
  return new Intl.NumberFormat('fa-IR').format(value)
}

export function date(value) {
  if (!value) return 'شروع نشده'
  return new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function relativeDays(value) {
  if (value == null) return 'نامحدود'
  return `${number(value)} روز`
}

export async function copy(value) {
  await navigator.clipboard.writeText(value)
}
