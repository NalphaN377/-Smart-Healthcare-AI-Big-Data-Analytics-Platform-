import { get } from './client.js'

export const analyticsApi = {
  health: () => get('/health'),
  overview: (filters) => get('/overview', filters),
  diseasesTop: (filters) => get('/diseases/top', { ...filters, limit: 10 }),
  diseasesCost: (filters) => get('/diseases/cost', { ...filters, limit: 10 }),
  hospitalsTop: (filters) => get('/hospitals/top', { ...filters, limit: 10 }),
  ageDistribution: (filters) => get('/age/distribution', { ...filters, limit: 20 }),
  paymentsDistribution: (filters) => get('/payments/distribution', { ...filters, limit: 20 }),
  severityDistribution: (filters) => get('/severity/distribution', { ...filters, limit: 20 }),
  yearlyTrends: (filters) => get('/trends/year', { ...filters, limit: 100 }),
}
