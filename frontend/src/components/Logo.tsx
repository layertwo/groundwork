interface LogoProps {
  size?: number
}

export default function Logo({ size = 24 }: LogoProps) {
  return (
    <svg
      viewBox="0 0 512 512"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="gw-g1" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#34d399" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id="gw-g2" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#059669" />
          <stop offset="100%" stopColor="#047857" />
        </linearGradient>
        <linearGradient id="gw-g3" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#047857" />
          <stop offset="100%" stopColor="#065f46" />
        </linearGradient>
      </defs>
      <path d="M256 100 L436 180 L256 260 L76 180 Z" fill="url(#gw-g1)" />
      <path d="M76 230 L256 310 L436 230 L436 280 L256 360 L76 280 Z" fill="url(#gw-g2)" />
      <path d="M76 330 L256 410 L436 330 L436 380 L256 460 L76 380 Z" fill="url(#gw-g3)" />
      <path
        d="M256 150 C240 150 228 162 228 178 C228 189 234 198 244 203 L240 230 L272 230 L268 203 C278 198 284 189 284 178 C284 162 272 150 256 150 Z"
        fill="#1a1a1a"
        opacity="0.85"
      />
    </svg>
  )
}
