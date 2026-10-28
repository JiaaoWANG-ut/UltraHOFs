import { Alert, Button, Col, Descriptions, Form, InputNumber, Modal, Radio, Row, Select, Space, Spin, Switch, Table, Tag, Typography, message } from 'antd';
import { BulbOutlined, DownloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useMutation, useQuery } from '@tanstack/react-query';
import { lazy, Suspense, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { PageHead, SectionCard, useNetColumns } from '../components/common';
import { SmilesInput } from '../components/SmilesInput';

const Viewer3D = lazy(() => import('../components/Viewer3D'));

export const EXPORT_FORMATS: [string, string, string][] = [
  ['cif', 'CIF (P1)', 'cif'],
  ['cif_sym', 'CIF (sym.)', 'cif'],
  ['poscar', 'POSCAR', 'vasp'],
  ['xyz', 'extXYZ', 'xyz'],
  ['lammps', 'LAMMPS', 'data'],
  ['pdb', 'PDB', 'pdb'],
];

export function QcPanel({ st }: { st: Json }) {
  const { t } = useTranslation();
  const qc: Json = st.qc || {};
  const info: Json = st.analysis?.build_info || {};
  const pore: Json = st.analysis?.pore || {};
  const color = qc.status === 'ok' ? 'green' : qc.status === 'warning' ? 'gold' : 'red';
  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Tag color={color}>{qc.status}</Tag>
        {(qc.messages || []).map((m: string) => (
          <span key={m} className="muted" style={{ fontSize: 12.5 }}>
            {m}
          </span>
        ))}
      </Space>
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="a / b / c">{st.cell ? `${st.cell.a} / ${st.cell.b} / ${st.cell.c}` : '—'}</Descriptions.Item>
        <Descriptions.Item label="α / β / γ">{st.cell ? `${st.cell.alpha} / ${st.cell.beta} / ${st.cell.gamma}` : '—'}</Descriptions.Item>
        <Descriptions.Item label={t('entry.density')}>{qc.density_g_cm3} g/cm³</Descriptions.Item>
        <Descriptions.Item label="atoms / molecules">{qc.n_atoms} / {qc.n_molecules}</Descriptions.Item>
        <Descriptions.Item label={t('builder.hbonds')}>{qc.hbonds_per_molecule}</Descriptions.Item>
        <Descriptions.Item label={t('builder.dim')}>{qc.hbond_dimensionality}D</Descriptions.Item>
        <Descriptions.Item label={t('builder.contacts')}>{qc.n_close_contacts}</Descriptions.Item>
        <Descriptions.Item label="min d(heavy)">{qc.min_intermolecular_heavy_A} Å</Descriptions.Item>
        {info.scale !== undefined ? (
          <>
            <Descriptions.Item label={t('builder.mismatch')}>{info.x_mismatch_max} Å</Descriptions.Item>
            <Descriptions.Item label={t('builder.fit')}>{info.node_fit_rmsd_max}</Descriptions.Item>
            {info.synthon_angle_max !== undefined && info.synthon_angle_max !== null ? (
              <Descriptions.Item label={t('builder.synthonAngle')}>
                <span style={info.synthon_angle_max > 15 ? { color: '#B4691F', fontWeight: 600 } : undefined}>{info.synthon_angle_max}°</span>
              </Descriptions.Item>
            ) : null}
          </>
        ) : null}
        {info.interlayer ? <Descriptions.Item label={t('builder.interlayer')}>{info.interlayer} Å ({info.stacking})</Descriptions.Item> : null}
        {info.interpenetration ? <Descriptions.Item label={t('builder.interpenetration')}>{info.interpenetration}</Descriptions.Item> : null}
        {pore.pld_A !== undefined ? (
          <>
            <Descriptions.Item label="LCD / PLD">{pore.lcd_A?.toFixed(2)} / {pore.pld_A?.toFixed(2)} Å</Descriptions.Item>
            <Descriptions.Item label="ASA (N₂)">{pore.asa_m2_g?.toFixed(0)} m²/g</Descriptions.Item>
            <Descriptions.Item label="Void fraction">{pore.void_fraction_geometric?.toFixed(3)}</Descriptions.Item>
            <Descriptions.Item label="Channels">{pore.channel_dimensionality}D</Descriptions.Item>
          </>
        ) : null}
      </Descriptions>
    </div>
  );
}

export function ExportButtons({ st }: { st: Json }) {
  return (
    <Space wrap>
      {EXPORT_FORMATS.map(([f, label, ext]) => (
        <Button key={f} icon={<DownloadOutlined />} onClick={() => api.download(`/structures/${st.id}/export`, { format: f }, `${(st.name || 'structure').replace(/[\s/]+/g, '_')}.${ext}`)}>
          {label}
        </Button>
      ))}
    </Space>
  );
}

export function RelaxButton({ st, onSubmitted }: { st: Json; onSubmitted?: (job: Json) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const submit = async () => {
    const v = await form.validateFields();
    try {
      const job = await api.post(`/structures/${st.id}/relax`, v);
      message.success(`${t('nav.jobs')} #${job.id}`);
      setOpen(false);
      onSubmitted?.(job);
    } catch (e: any) {
      message.error(e.message);
    }
  };
  return (
    <>
      <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => setOpen(true)}>
        {t('builder.relax')}
      </Button>
      <Modal open={open} onCancel={() => setOpen(false)} onOk={submit} title={t('builder.relax')} okText={t('builder.relaxSubmit')}>
        <Alert type="info" showIcon message={t('builder.loginNode')} description={t('builder.engineNote')} style={{ marginBottom: 12 }} />
        <Form form={form} layout="vertical" initialValues={{ engine: 'mace_off24', fmax_atoms: 0.05, fmax_cell: 0.02, steps_atoms: 400, steps_cell: 800, cell_relax: true }}>
          <Form.Item name="engine" label="Engine">
            <Select options={[{ value: 'mace_off24', label: 'MACE-OFF24 (medium)' }]} />
          </Form.Item>
          <Row gutter={10}>
            <Col span={12}>
              <Form.Item name="fmax_atoms" label="fmax atoms (eV/Å)">
                <InputNumber min={0.005} max={1} step={0.01} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="steps_atoms" label="steps (atoms)">
                <InputNumber min={10} max={5000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="fmax_cell" label="fmax cell (eV/Å)">
                <InputNumber min={0.005} max={1} step={0.01} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="steps_cell" label="steps (cell)">
                <InputNumber min={0} max={10000} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="cell_relax" label="Cell relaxation" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

export default function BuilderPage() {
  const { t } = useTranslation();
  const netColumns = useNetColumns();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const initialMode = params.get('node_a') ? 'bipartite' : params.get('edge') ? 'linker' : 'single';
  const [mode, setMode] = useState<string>(initialMode);
  const [node, setNode] = useState(params.get('node') || '');
  const [nodeA, setNodeA] = useState(params.get('node_a') || '');
  const [nodeB, setNodeB] = useState(params.get('node_b') || '');
  const [edge, setEdge] = useState(params.get('edge') || '');
  const [net, setNet] = useState<string | undefined>(params.get('net') || undefined);
  const [opts, setOpts] = useState<Json>({ stacking: 'AA', interlayer: null, slip: [0, 0], interpenetration: 1, align_synthons: true, analyze: true, name: '' });
  const nets = useQuery({ queryKey: ['topologies', 'all'], queryFn: () => api.get('/topologies', { limit: 3000 }) });
  const preview = useQuery({ queryKey: ['topology', net], queryFn: () => api.get(`/topologies/${net}`), enabled: !!net });
  const suggest = useMutation({
    mutationFn: () => {
      if (mode === 'single') return api.post('/topologies/suggest', { smiles: node });
      if (mode === 'linker') return api.post('/topologies/suggest', { smiles: node, partner_smiles: edge });
      return api.post('/topologies/suggest', { smiles: nodeA, partner_smiles: nodeB });
    },
  });
  const build = useMutation({
    mutationFn: () => {
      const apiMode = mode === 'linker' ? 'single' : mode;
      const body: Json = { ...opts, net, mode: apiMode };
      if (mode === 'single' || mode === 'linker') body.node = node;
      if (mode === 'linker') body.edge = edge;
      if (mode === 'bipartite' || mode === 'binodal') {
        body.node_a = nodeA;
        body.node_b = nodeB;
      }
      return api.post('/structures/build', body);
    },
  });
  const st: Json | undefined = build.data;
  const netInfo: Json | undefined = (nets.data?.items || []).find((n: Json) => n.name === net);

  useEffect(() => {
    if ((mode === 'single' && node) || (mode !== 'single' && nodeA && nodeB)) suggest.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ready = !!net && (mode === 'single' ? !!node : mode === 'linker' ? !!node && !!edge : !!nodeA && !!nodeB);

  return (
    <div>
      <PageHead title={t('builder.title')} sub={t('builder.sub')} />
      <Row gutter={18}>
        <Col xs={24} xl={9}>
          <SectionCard title={t('builder.mode')}>
            <Radio.Group
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}
              options={[
                { value: 'single', label: t('builder.single') },
                { value: 'linker', label: t('builder.withLinker') },
                { value: 'bipartite', label: t('builder.bipartite') },
                { value: 'binodal', label: t('builder.binodal') },
              ]}
            />
            <div style={{ marginTop: 14 }}>
              {mode === 'single' || mode === 'linker' ? (
                <>
                  <div className="muted">{t('builder.node')}</div>
                  <SmilesInput value={node} onChange={setNode} />
                </>
              ) : (
                <>
                  <div className="muted">{t('builder.nodeA')}</div>
                  <SmilesInput value={nodeA} onChange={setNodeA} />
                  <div className="muted" style={{ marginTop: 10 }}>{t('builder.nodeB')}</div>
                  <SmilesInput value={nodeB} onChange={setNodeB} />
                </>
              )}
              {mode === 'linker' ? (
                <>
                  <div className="muted" style={{ marginTop: 10 }}>{t('builder.edge')}</div>
                  <SmilesInput value={edge} onChange={setEdge} />
                </>
              ) : null}
            </div>
            <Button style={{ marginTop: 12 }} icon={<BulbOutlined />} loading={suggest.isPending} onClick={() => suggest.mutate()}>
              {t('builder.suggest')}
            </Button>
            {suggest.error ? <Alert type="error" showIcon style={{ marginTop: 10 }} message={(suggest.error as Error).message} /> : null}
            {suggest.data ? (
              <div style={{ marginTop: 12 }}>
                <div className="muted" style={{ fontSize: 12 }}>
                  {(suggest.data.building_blocks || []).map((b: Json, i: number) => (
                    <div key={i}>
                      BB{i + 1}: {b.k}-c · {b.geometry} (RMSD {b.geometry_rmsd}) · r = {b.radius} Å {b.notes?.length ? `· ${b.notes.join('; ')}` : ''}
                    </div>
                  ))}
                </div>
                <Table
                  size="small"
                  rowKey="net"
                  pagination={false}
                  style={{ marginTop: 8 }}
                  dataSource={suggest.data.nets}
                  onRow={(r: Json) => ({ onClick: () => setNet(r.net), style: { cursor: 'pointer', background: r.net === net ? '#F3EBDD' : undefined } })}
                  columns={[
                    ...netColumns,
                    { title: 'nodes', dataIndex: 'n_nodes' },
                    ...(suggest.data.mode !== 'single' && suggest.data.mode !== 'single+edge' ? [{ title: 'mode', dataIndex: 'mode' }] : []),
                  ]}
                />
              </div>
            ) : null}
          </SectionCard>
        </Col>
        <Col xs={24} xl={15}>
          <SectionCard title={t('builder.options')}>
            <Row gutter={14}>
              <Col xs={24} md={12}>
                <div className="muted">{t('builder.net')}</div>
                <Select
                  showSearch
                  style={{ width: '100%' }}
                  value={net}
                  onChange={setNet}
                  placeholder="dia, sql, hcb, pcu …"
                  options={(nets.data?.items || []).map((n: Json) => ({
                    value: n.name,
                    label: `${n.name}${n.precedent ? ' ★' : ''} · ${n.dim}D · ${n.node_types.map((x: Json) => x.cn).join(',')}-c · ${n.n_nodes} nodes`,
                  }))}
                />
                {netInfo ? <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{netInfo.spacegroup} {netInfo.precedent ? `· ${t('builder.precedentNet')}` : ''}</div> : null}
                <Row gutter={10} style={{ marginTop: 12 }}>
                  {netInfo?.dim === 2 ? (
                    <>
                      <Col span={12}>
                        <div className="muted">{t('builder.stacking')}</div>
                        <Select style={{ width: '100%' }} value={opts.stacking} onChange={(v) => setOpts({ ...opts, stacking: v })} options={['AA', 'AB', 'ABC'].map((s) => ({ value: s, label: s }))} />
                      </Col>
                      <Col span={12}>
                        <div className="muted">{t('builder.interlayer')}</div>
                        <InputNumber style={{ width: '100%' }} min={2.8} max={12} step={0.05} value={opts.interlayer} placeholder={t('builder.auto')} onChange={(v) => setOpts({ ...opts, interlayer: v })} />
                      </Col>
                      <Col span={12} style={{ marginTop: 10 }}>
                        <div className="muted">{t('builder.slip')} (a)</div>
                        <InputNumber style={{ width: '100%' }} min={-10} max={10} step={0.1} value={opts.slip[0]} onChange={(v) => setOpts({ ...opts, slip: [v || 0, opts.slip[1]] })} />
                      </Col>
                      <Col span={12} style={{ marginTop: 10 }}>
                        <div className="muted">{t('builder.slip')} (b)</div>
                        <InputNumber style={{ width: '100%' }} min={-10} max={10} step={0.1} value={opts.slip[1]} onChange={(v) => setOpts({ ...opts, slip: [opts.slip[0], v || 0] })} />
                      </Col>
                    </>
                  ) : (
                    <Col span={12}>
                      <div className="muted">{t('builder.interpenetration')}</div>
                      <InputNumber style={{ width: '100%' }} min={1} max={6} value={opts.interpenetration} onChange={(v) => setOpts({ ...opts, interpenetration: v || 1 })} />
                    </Col>
                  )}
                </Row>
                <Space style={{ marginTop: 12 }}>
                  <Switch checked={opts.align_synthons} onChange={(v) => setOpts({ ...opts, align_synthons: v })} /> {t('builder.align')}
                </Space>
                <div style={{ marginTop: 14 }}>
                  <Button data-testid="build-btn" type="primary" size="large" icon={<ThunderboltOutlined />} disabled={!ready} loading={build.isPending} onClick={() => build.mutate()}>
                    {build.isPending ? t('builder.building') : t('builder.build')}
                  </Button>
                </div>
                {build.error ? <Alert type="error" showIcon style={{ marginTop: 10 }} message={(build.error as Error).message} /> : null}
              </Col>
              <Col xs={24} md={12}>
                <div className="muted">{t('builder.preview')}</div>
                <Suspense fallback={<Spin />}>
                  {preview.data ? <Viewer3D lines={preview.data.edges} nodes={preview.data.nodes} height={240} controls={false} /> : <div className="viewer3d" style={{ height: 240 }} />}
                </Suspense>
              </Col>
            </Row>
          </SectionCard>
          {st ? (
            <SectionCard
              title={`${t('builder.result')} · ${st.name}`}
              extra={
                <Space>
                  <Link to={`/structures/${st.id}`}>{t('common.details')}</Link>
                  <RelaxButton st={st} onSubmitted={() => nav('/jobs')} />
                </Space>
              }
            >
              <Suspense fallback={<Spin />}>
                <Viewer3D data={st.cif} format="cif" height={480} periodic />
              </Suspense>
              <div style={{ marginTop: 12 }}>
                <QcPanel st={st} />
              </div>
              <div style={{ marginTop: 12 }}>
                <Typography.Text strong>{t('builder.export')}</Typography.Text>
                <div style={{ marginTop: 6 }}>
                  <ExportButtons st={st} />
                </div>
              </div>
            </SectionCard>
          ) : null}
        </Col>
      </Row>
    </div>
  );
}
