const countFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})
const currencyFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

export function formatCount(value) {
  return value === null || value === undefined ? '—' : countFormatter.format(value)
}

export function formatDecimal(value) {
  return value === null || value === undefined ? '—' : decimalFormatter.format(value)
}

export function formatCurrency(value) {
  return value === null || value === undefined ? '—' : currencyFormatter.format(value)
}
