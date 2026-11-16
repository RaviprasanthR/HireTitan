export type Tone = 'green' | 'yellow' | 'orange' | 'red' | 'blue' | 'purple' | 'teal' | 'grey'

export const SOURCE_TONE: Record<string, Tone> = {
  naukri: 'blue',
  linkedin: 'teal',
  indeed: 'purple',
  'company job board': 'green',
  'careers page': 'orange',
  'added by you': 'yellow',
  'email alert': 'purple',
  'job site': 'blue',
}
