import { Checkbox, Segmented, Space, Spin } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

type Fmt = 'cif' | 'sdf' | 'mol' | 'xyz';

interface Props {
  data?: string;
  format?: Fmt;
  height?: number;
  periodic?: boolean;
  hbonds?: boolean;
  controls?: boolean;
  lines?: number[][][];
  nodes?: { pos: number[]; type: number }[];
}

const ELEMENT_COLORS: Record<string, string> = {
  C: '#3a3f47', H: '#d9d6cf', O: '#b23a2e', N: '#2f5aa8', S: '#c9a227', F: '#5a9e6f', Cl: '#3f8f4f', Br: '#8a4b2e',
  P: '#d17a22', B: '#b08d57', Si: '#8d8778',
};

function computeHbonds(atoms: any[]): [any, any][] {
  const cell = 3;
  const grid = new Map<string, any[]>();
  const key = (x: number, y: number, z: number) => `${Math.floor(x / cell)},${Math.floor(y / cell)},${Math.floor(z / cell)}`;
  for (const a of atoms) {
    const k = key(a.x, a.y, a.z);
    if (!grid.has(k)) grid.set(k, []);
    grid.get(k)!.push(a);
  }
  const near = (a: any, r: number): [any, number][] => {
    const out: [any, number][] = [];
    const cx = Math.floor(a.x / cell), cy = Math.floor(a.y / cell), cz = Math.floor(a.z / cell);
    for (let i = -1; i <= 1; i++)
      for (let j = -1; j <= 1; j++)
        for (let k = -1; k <= 1; k++)
          for (const b of grid.get(`${cx + i},${cy + j},${cz + k}`) || []) {
            if (b === a) continue;
            const d = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
            if (d < r) out.push([b, d]);
          }
    return out;
  };
  const pairs: [any, any][] = [];
  for (const h of atoms) {
    if (h.elem !== 'H') continue;
    const parent = near(h, 1.15).find(([b]) => b.elem === 'O' || b.elem === 'N');
    if (!parent) continue;
    const d = parent[0];
    for (const [acc, dist] of near(h, 2.6)) {
      if (acc === d || (acc.elem !== 'O' && acc.elem !== 'N') || dist < 1.4) continue;
      const v1 = [d.x - h.x, d.y - h.y, d.z - h.z];
      const v2 = [acc.x - h.x, acc.y - h.y, acc.z - h.z];
      const cos = (v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]) / (Math.hypot(v1[0], v1[1], v1[2]) * Math.hypot(v2[0], v2[1], v2[2]));
      if ((Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI > 120) pairs.push([h, acc]);
    }
  }
  return pairs;
}

export default function Viewer3D({ data, format = 'cif', height = 460, periodic = false, hbonds = true, controls = true, lines, nodes }: Props) {
  const { t } = useTranslation();
  const el = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const [lib, setLib] = useState<any>(null);
  const [cells, setCells] = useState<string>(periodic ? '2×2×1' : '1×1×1');
  const [showHb, setShowHb] = useState(hbonds);
  const [style, setStyle] = useState<string>('stick');
  const [err, setErr] = useState<string>('');

  useEffect(() => {
    let alive = true;
    import('3dmol').then((m: any) => {
      const mod = m.createViewer ? m : m.default;
      if (alive) setLib(mod);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!lib || !el.current) return;
    if (!viewerRef.current) viewerRef.current = lib.createViewer(el.current, { backgroundColor: 'white', antialias: true });
    const v = viewerRef.current;
    v.clear();
    if (lines && nodes) {
      for (const [p1, p2] of lines) {
        v.addCylinder({ start: { x: p1[0], y: p1[1], z: p1[2] }, end: { x: p2[0], y: p2[1], z: p2[2] }, radius: 0.03, color: '#1E2A3A', fromCap: 1, toCap: 1 });
      }
      for (const n of nodes) v.addSphere({ center: { x: n.pos[0], y: n.pos[1], z: n.pos[2] }, radius: 0.1, color: n.type === 0 ? '#B08D57' : '#1E2A3A' });
      v.zoomTo();
      v.render();
      return;
    }
    if (!data) {
      v.render();
      return;
    }
    let model: any;
    try {
      model = v.addModel(data, format, format === 'cif' ? { doAssembly: true, normalizeAssembly: true, duplicateAssemblyAtoms: false } : {});
      setErr('');
    } catch (e: any) {
      setErr(String(e?.message || e));
      v.render();
      return;
    }
    const colorfunc = (a: any) => ELEMENT_COLORS[a.elem] || '#888';
    if (style === 'stick') v.setStyle({}, { stick: { radius: 0.13, colorfunc }, sphere: { scale: 0.18, colorfunc } });
    else if (style === 'sphere') v.setStyle({}, { sphere: { scale: 0.85, colorfunc } });
    else v.setStyle({}, { line: { linewidth: 1.2, colorfunc } });
    if (format === 'cif') {
      const [a, b, c] = cells.split('×').map(Number);
      try {
        if (a * b * c > 1) v.replicateUnitCell(a, b, c, model, true);
        v.addUnitCell(model, { box: { color: '#B08D57' }, astyle: { hidden: true }, bstyle: { hidden: true }, cstyle: { hidden: true } });
      } catch {
        /* not periodic */
      }
    }
    if (showHb) {
      const atoms = v.selectedAtoms({});
      if (atoms.length < 25000) {
        for (const [h, acc] of computeHbonds(atoms)) {
          v.addCylinder({ start: { x: h.x, y: h.y, z: h.z }, end: { x: acc.x, y: acc.y, z: acc.z }, radius: 0.06, color: '#B08D57', dashed: true, dashLength: 0.18, gapLength: 0.14 });
        }
      }
    }
    v.zoomTo();
    v.render();
  }, [lib, data, format, cells, showHb, style, lines, nodes]);

  return (
    <div>
      {controls && !lines ? (
        <Space wrap style={{ marginBottom: 8 }}>
          <Segmented size="small" value={style} onChange={(v) => setStyle(String(v))} options={[{ label: 'Stick', value: 'stick' }, { label: 'CPK', value: 'sphere' }, { label: 'Line', value: 'line' }]} />
          {format === 'cif' ? (
            <Space size={6}>
              <span className="muted">{t('entry.supercell')}</span>
              <Segmented size="small" value={cells} onChange={(v) => setCells(String(v))} options={['1×1×1', '2×2×1', '2×2×2', '3×3×1']} />
            </Space>
          ) : null}
          <Checkbox checked={showHb} onChange={(e) => setShowHb(e.target.checked)}>
            {t('entry.showHbonds')}
          </Checkbox>
        </Space>
      ) : null}
      <div className="viewer3d" style={{ height }}>
        {!lib ? <Spin style={{ position: 'absolute', top: '45%', left: '48%' }} /> : null}
        {err ? <div className="muted" style={{ position: 'absolute', top: 12, left: 12, zIndex: 2 }}>3D viewer: {err}</div> : null}
        <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      </div>
    </div>
  );
}
