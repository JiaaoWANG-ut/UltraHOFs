import { brand } from '../theme';

/** Lattice-X symbol (variant A): hexagonal H-bond lattice crossed by an X; dashed arms = boundless network. */
export function LatticeSymbol({ size = 40, ink = brand.ink, gold = brand.gold }: { size?: number; ink?: string; gold?: string }) {
  const hex = Array.from({ length: 6 }, (_, k) => {
    const a = ((-90 + 60 * k) * Math.PI) / 180;
    return [60 + 38 * Math.cos(a), 60 + 38 * Math.sin(a)];
  });
  const d = 0.7071;
  const arms: [number, number][] = [[1, 1], [-1, 1], [1, -1], [-1, -1]];
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" aria-hidden>
      <polygon points={hex.map((p) => p.join(',')).join(' ')} fill="none" stroke={ink} strokeWidth={1.5} strokeLinejoin="round" />
      <g stroke={gold} strokeWidth={3.4} strokeLinecap="round">
        <line x1={60 - 24 * d} y1={60 - 24 * d} x2={60 + 24 * d} y2={60 + 24 * d} />
        <line x1={60 + 24 * d} y1={60 - 24 * d} x2={60 - 24 * d} y2={60 + 24 * d} />
      </g>
      <g stroke={gold} strokeWidth={1.6} strokeLinecap="round" strokeDasharray="0.1 4.2">
        {arms.map(([sx, sy], i) => (
          <line key={i} x1={60 + 31 * d * sx} y1={60 + 31 * d * sy} x2={60 + 54 * d * sx} y2={60 + 54 * d * sy} />
        ))}
      </g>
      <g fill={ink}>
        {hex.map((p, i) => (
          <circle key={i} cx={p[0]} cy={p[1]} r={2.7} />
        ))}
        <circle cx={60} cy={60} r={3.8} />
      </g>
    </svg>
  );
}

export function BrandMark({ size = 36, dark = false }: { size?: number; dark?: boolean }) {
  const ink = dark ? brand.paper : brand.ink;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
      <LatticeSymbol size={size} ink={ink} />
      <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.05 }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: size * 0.62, color: ink, letterSpacing: '0.01em' }}>
          UltraHOFs
        </span>
        <span style={{ fontFamily: 'var(--font-zh)', fontSize: Math.max(10, size * 0.3), color: brand.gold, letterSpacing: '0.28em' }}>
          知声无界 · ULTRA-X
        </span>
      </span>
    </span>
  );
}
