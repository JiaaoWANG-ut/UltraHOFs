import { Button, Card, Col, Collapse, Form, Input, InputNumber, Pagination, Row, Segmented, Select, Slider, Space, Table, Tag, Typography } from 'antd';
import { AppstoreOutlined, BarsOutlined, SearchOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { useAuth } from '../auth';
import { EmptyState, EvidenceDots, MolSvg, PageHead, StatusTag } from '../components/common';
import { SmilesInput } from '../components/SmilesInput';

const SYNTHONS = ['carboxylic_acid', 'carboxylate', 'amidinium', 'sulfonate', 'guanidinium', 'ammonium', 'dat', 'benzimidazolone',
  'imide', 'pyrazole', 'triazole', 'tetrazole', 'pyridone', 'primary_amide', 'secondary_amide', 'urea', 'boronic_acid',
  'phosphonic_acid', 'pyridyl', 'hydroxy', 'amine', 'nitrile', 'imidazole'];

export default function DatabasePage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  const { isCurator } = useAuth();
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState<'cards' | 'table'>('cards');
  const [structQuery, setStructQuery] = useState<Json | null>(null);
  const [smiles, setSmiles] = useState('');
  const [mode, setMode] = useState('substructure');
  const [threshold, setThreshold] = useState(0.5);
  const page = Number(params.get('page') || 1);
  const filters = Object.fromEntries(params.entries());

  const list = useQuery({
    queryKey: ['hofs', filters],
    queryFn: () => api.get('/hofs', { ...filters, page, size: 24 }),
    enabled: !structQuery,
  });
  const struct = useQuery({
    queryKey: ['hofs-struct', structQuery],
    queryFn: () => api.post('/hofs/search/structure', structQuery),
    enabled: !!structQuery,
  });
  const stats = useQuery({ queryKey: ['hofstats'], queryFn: () => api.get('/hofs/stats') });
  const data: Json = structQuery ? struct.data || { total: 0, items: [] } : list.data || { total: 0, items: [] };
  const loading = structQuery ? struct.isFetching : list.isFetching;

  const apply = (v: Json) => {
    const p: Record<string, string> = {};
    Object.entries(v).forEach(([k, val]) => {
      if (val !== undefined && val !== null && val !== '') p[k] = String(val);
    });
    setStructQuery(null);
    setParams(p);
  };

  const columns = [
    { title: '', dataIndex: 'svg', width: 140, render: (s: string) => <MolSvg svg={s} /> },
    { title: t('common.name'), dataIndex: 'name', render: (n: string, r: Json) => <Link to={`/database/${r.id}`}><b>{n || `#${r.id}`}</b></Link> },
    { title: t('db.hbondClass'), dataIndex: 'hbond_class', render: (c: string) => (c ? <Tag>{c}</Tag> : null) },
    { title: t('entry.ccdc'), dataIndex: 'ccdc_numbers', render: (c: string[]) => c?.join(', ') },
    { title: t('common.year'), dataIndex: 'year', width: 70 },
    { title: 'PLD (Å)', dataIndex: 'pld', width: 80, render: (v: number) => (v ? v.toFixed(2) : '') },
    { title: t('db.dim'), dataIndex: 'hbond_dimensionality', width: 90, render: (d: number) => (d !== null && d !== undefined ? `${d}D` : '') },
    { title: t('entry.evidence'), dataIndex: 'evidence', render: (e: Json) => <EvidenceDots evidence={e} /> },
    { title: t('common.status'), dataIndex: 'curation_status', render: (s: string) => <StatusTag status={s} /> },
    { title: t('entry.citation'), dataIndex: 'reference', render: (r: Json) => (r ? <span className="muted" style={{ fontSize: 12 }}>{r.first_author} · <em>{r.journal}</em> {r.year}</span> : null) },
  ];

  return (
    <div>
      <PageHead title={t('db.title')} sub={t('db.sub')} extra={stats.data ? <span className="muted">{t('common.total', { n: stats.data.n_entries })} · {stats.data.n_references} refs</span> : null} />
      <Row gutter={18}>
        <Col xs={24} lg={6}>
          <Card size="small" title={<span className="display">{t('common.search')}</span>}>
            <Form layout="vertical" initialValues={filters} onFinish={apply} key={JSON.stringify(filters)}>
              <Form.Item name="q" label={t('db.query')}>
                <Input allowClear prefix={<SearchOutlined />} />
              </Form.Item>
              <Form.Item name="synthon" label={t('design.synthons')}>
                <Select allowClear showSearch options={SYNTHONS.map((s) => ({ value: s, label: s }))} />
              </Form.Item>
              <Form.Item name="hbond_class" label={t('db.hbondClass')}>
                <Select allowClear showSearch options={(stats.data?.by_hbond_class || []).map((x: any[]) => ({ value: x[0], label: `${x[0]} (${x[1]})` }))} />
              </Form.Item>
              <Form.Item name="topology" label={t('db.topology')}>
                <Select allowClear options={(stats.data?.by_topology || []).map((x: any[]) => ({ value: x[0], label: `${x[0]} (${x[1]})` }))} />
              </Form.Item>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item name="year_min" label={t('common.year') + ' ≥'}>
                    <InputNumber style={{ width: '100%' }} min={1950} max={2100} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="year_max" label={t('common.year') + ' ≤'}>
                    <InputNumber style={{ width: '100%' }} min={1950} max={2100} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="dim" label={t('db.dim') + ' ≥'}>
                <Select allowClear options={[1, 2, 3].map((d) => ({ value: d, label: `${d}D` }))} />
              </Form.Item>
              <Form.Item name="porous" label={t('db.porous')}>
                <Select allowClear options={['yes', 'no'].map((v) => ({ value: v, label: t(`evidence.${v}`) }))} />
              </Form.Item>
              <Form.Item name="charged" label={t('db.charged')}>
                <Select allowClear options={[{ value: 'true', label: t('common.yes') }, { value: 'false', label: t('common.no') }]} />
              </Form.Item>
              {isCurator ? (
                <Form.Item name="status" label={t('db.status')}>
                  <Select allowClear options={['auto', 'verified', 'needs_review', 'candidate', 'rejected'].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
                </Form.Item>
              ) : null}
              <Form.Item name="sort" label={t('db.sort')}>
                <Select
                  allowClear
                  options={[
                    { value: 'year_desc', label: t('db.yearDesc') },
                    { value: 'year_asc', label: t('db.yearAsc') },
                    { value: 'name', label: t('db.byName') },
                    { value: 'pld_desc', label: t('db.byPld') },
                  ]}
                />
              </Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                  {t('common.search')}
                </Button>
                <Button onClick={() => apply({})}>{t('common.reset')}</Button>
              </Space>
            </Form>
          </Card>
          <Collapse
            style={{ marginTop: 14 }}
            items={[
              {
                key: 's',
                label: <span className="display">{t('db.structure')}</span>,
                children: (
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <SmilesInput value={smiles} onChange={setSmiles} preview={false} />
                    <Segmented value={mode} onChange={(v) => setMode(String(v))} options={[{ value: 'substructure', label: t('db.substructure') }, { value: 'similarity', label: t('db.similarity') }, { value: 'exact', label: t('db.exact') }]} />
                    {mode === 'similarity' ? (
                      <div>
                        <Typography.Text type="secondary">{t('db.threshold')}: {threshold}</Typography.Text>
                        <Slider min={0.2} max={1} step={0.05} value={threshold} onChange={setThreshold} />
                      </div>
                    ) : null}
                    <Button type="primary" block disabled={!smiles} onClick={() => setStructQuery({ query: smiles, mode, threshold, limit: 200 })}>
                      {t('common.search')}
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </Col>
        <Col xs={24} lg={18}>
          <Space style={{ marginBottom: 12, justifyContent: 'space-between', width: '100%' }}>
            <span className="muted">
              {t('db.results')} · {t('common.total', { n: data.total })}
              {structQuery ? (
                <Button type="link" onClick={() => setStructQuery(null)}>
                  ×
                </Button>
              ) : null}
            </span>
            <Segmented value={view} onChange={(v) => setView(v as any)} options={[{ value: 'cards', icon: <AppstoreOutlined /> }, { value: 'table', icon: <BarsOutlined /> }]} />
          </Space>
          {!loading && !data.items?.length ? <EmptyState text={t('db.noResults')} /> : null}
          {view === 'cards' ? (
            <Row gutter={[14, 14]}>
              {(data.items || []).map((e: Json) => (
                <Col xs={24} sm={12} xl={8} key={e.id}>
                  <Card hoverable className="mol-card" size="small" onClick={() => nav(`/database/${e.id}`)} loading={loading}>
                    <MolSvg svg={e.svg} height={170} />
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 6 }}>
                      <b className="display" style={{ fontSize: 17 }}>{e.name || `#${e.id}`}</b>
                      <span className="muted">{e.year}</span>
                    </div>
                    <Space size={4} wrap style={{ marginTop: 4 }}>
                      {e.hbond_class ? <Tag>{e.hbond_class}</Tag> : null}
                      {e.topology ? <Tag color="gold">{e.topology}</Tag> : null}
                      {e.hbond_dimensionality !== null && e.hbond_dimensionality !== undefined ? <Tag>{e.hbond_dimensionality}D</Tag> : null}
                      {e.similarity ? <Tag color="blue">{(e.similarity * 100).toFixed(0)}%</Tag> : null}
                      <StatusTag status={e.curation_status} />
                    </Space>
                    <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                      <EvidenceDots evidence={e.evidence} />
                      {e.reference ? <span className="muted" style={{ fontSize: 11.5 }}><em>{e.reference.journal}</em></span> : null}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          ) : (
            <Table rowKey="id" size="small" loading={loading} dataSource={data.items || []} columns={columns as any} pagination={false} />
          )}
          {!structQuery && data.total > 24 ? (
            <Pagination
              style={{ marginTop: 16, textAlign: 'center' }}
              current={page}
              pageSize={24}
              total={data.total}
              showSizeChanger={false}
              onChange={(p) => setParams({ ...filters, page: String(p) })}
            />
          ) : null}
        </Col>
      </Row>
    </div>
  );
}
