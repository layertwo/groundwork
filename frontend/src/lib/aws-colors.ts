export const AWS_COLORS: Record<string, string> = {
  pink: '#e0529e',
  purple: '#8b5cf6',
  darkBlue: '#1d4ed8',
  lightBlue: '#38bdf8',
  teal: '#14b8a6',
  green: '#22c55e',
  yellow: '#eab308',
  orange: '#f97316',
  red: '#ef4444',
}

export const AWS_COLOR_NAMES = [
  'pink',
  'purple',
  'darkBlue',
  'lightBlue',
  'teal',
  'green',
  'yellow',
  'orange',
  'red',
] as const

export type AwsColor = (typeof AWS_COLOR_NAMES)[number]

export function awsColorLabel(color: string): string {
  switch (color) {
    case 'darkBlue':
      return 'Dark Blue'
    case 'lightBlue':
      return 'Light Blue'
    default:
      return color.charAt(0).toUpperCase() + color.slice(1)
  }
}
