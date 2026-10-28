import { Alert, Button, Col, Descriptions, Form, Input, InputNumber, Row, Select, Space, Spin, Table, Tabs, Tag, Typography, message } from 'antd';
import { ApartmentOutlined, DownloadOutlined, ExperimentOutlined, LinkOutlined } from '@ant-design/icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, type Json } from '../api';
import { useAuth } from '../auth';
import { AddToProject } from '../components/AddToProject';
import { BandTag, Citation, CopyText, EvidenceTable, MolSvg, PageHead, SectionCard, StatusTag } from '../components/common';

const Viewer3D = lazy(() => import('../components/Viewer3D'));

export default function EntryPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { isCurator } = useAuth();
  const q = useQuery({ queryKey: ['hof', id], queryFn: () => api.get(`/hofs/${id}`) });
  const hasCif = q.data?.has_framework_cif || q.data?.has_raw_cif;
  const cif = useQuery({
    queryKey: ['hofcif', id],
    queryFn: () => api.text(`/hofs/${id}/cif`, { kind: 'display' }),
    enabled: !!hasCif,
    retry: false,
  });
  if (q.isLoading) return <Spin style={{ margin: '20vh auto', display: 'block' }} />;
  if (q.error || !q.data) return <Alert type="error" message={(q.error as Error)?.message || 'not found'} />;
  const e: Json = q.data;
  const main = (e.all_components || []).find((c: Json) => c.role === 'tecton') || e.all_components?.[0];

  const save = async (v: Json) => {
    const body: Json = { ...v };
    try {
      await api.patch(`/hofs/${id}`, body);
      message.success(t('common.save'));
      qc.invalidateQueries({ queryKey: ['hof', id] });
    } catch (err: any) {
      message.error(err.message);
    }
  };

  const overview = (
    <Row gutter={18}>
      <Col xs={24} lg={14}>
        <SectionCard title={t('entry.components')}>
          <Row gutter={[12, 12]}>
            {(e.all_components || []).map((c: Json) => (
              <Col xs={24} md={12} key={`${c.molecule_id}-${c.role}`}>
                <div className="panel">
                  <MolSvg svg={c.svg} />
                  <Space wrap size={4}>
                    <Tag color={c.role === 'tecton' ? 'gold' : undefined}>{c.role}</Tag>
                    <Tag>×{c.stoichiometry}</Tag>
                    {c.charge ? <Tag>{c.charge > 0 ? `+${c.charge}` : c.charge}</Tag> : null}
                    <BandTag band={c.band} score={c.score} />
                  </Space>
                  {c.name ? <div style={{ marginTop: 6 }}>{c.name}</div> : null}
                  <div style={{ marginTop: 4 }}>
                    <CopyText text={c.smiles} />
                  </div>
                  <Space style={{ marginTop: 8 }} wrap>
                    <Button size="small" icon={<ExperimentOutlined />} onClick={() => nav(`/molecules/${c.molecule_id}`)}>
                      {t('common.details')}
                    </Button>
                    <Button size="small" icon={<ApartmentOutlined />} onClick={() => nav(`/builder?node=${encodeURIComponent(c.smiles)}`)}>
                      {t('common.build')}
                    </Button>
                  </Space>
                </div>
              </Col>
            ))}
          </Row>
        </SectionCard>
        <SectionCard title={t('entry.evidence')}>
          <EvidenceTable evidence={e.evidence} />
        </SectionCard>
      </Col>
      <Col xs={24} lg={10}>
        <SectionCard title={t('entry.citation')}>
          {(e.references || []).length ? (e.references as Json[]).map((r) => <Citation key={r.id} refd={r} />) : <span className="muted">{t('common.none')}</span>}
          {e.ccdc_numbers?.length ? (
            <div style={{ marginTop: 12 }}>
              <span className="muted">{t('entry.ccdc')}: </span>
              {e.ccdc_numbers.map((n: string, i: number) => (
                <a key={n} href={e.ccdc_links[i]} target="_blank" rel="noreferrer" style={{ marginRight: 10 }}>
                  <LinkOutlined /> {n}
                </a>
              ))}
            </div>
          ) : null}
        </SectionCard>
        <SectionCard title={t('entry.cell')}>
          <Descriptions size="small" column={2}>
            {['a', 'b', 'c', 'alpha', 'beta', 'gamma'].map((k) => (
              <Descriptions.Item key={k} label={k}>
                {e.cell?.[k] !== undefined ? Number(e.cell[k]).toFixed(k.length === 1 ? 3 : 2) : '—'}
              </Descriptions.Item>
            ))}
            <Descriptions.Item label={t('entry.spaceGroup')}>{e.space_group || '—'}</Descriptions.Item>
            <Descriptions.Item label={t('entry.density')}>{e.density ? `${e.density} g/cm³` : '—'}</Descriptions.Item>
            <Descriptions.Item label={t('entry.hbondDim')}>{e.hbond_dimensionality !== null && e.hbond_dimensionality !== undefined ? `${e.hbond_dimensionality}D` : '—'}</Descriptions.Item>
            <Descriptions.Item label={t('db.topology')}>{e.topology || '—'}</Descriptions.Item>
          </Descriptions>
        </SectionCard>
        {e.pore && Object.keys(e.pore).length ? (
          <SectionCard title={t('entry.pore')}>
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="LCD">{e.pore.lcd_A?.toFixed(2)} Å</Descriptions.Item>
              <Descriptions.Item label="PLD">{e.pore.pld_A?.toFixed(2)} Å</Descriptions.Item>
              <Descriptions.Item label="ASA (N₂)">{e.pore.asa_m2_g?.toFixed(0)} m²/g</Descriptions.Item>
              <Descriptions.Item label="Void fraction">{e.pore.void_fraction_geometric?.toFixed(3)}</Descriptions.Item>
              <Descriptions.Item label="Channels">{e.pore.channel_dimensionality}D</Descriptions.Item>
              <Descriptions.Item label="Probe">{e.pore.probe_radius_A} Å</Descriptions.Item>
            </Descriptions>
          </SectionCard>
        ) : null}
        <SectionCard title={t('entry.source')}>
          <div className="muted" style={{ fontSize: 12.5 }}>
            {e.source_dataset} · {e.source_record}
            <br />
            {t('entry.license')}: {e.license}
            <br />
            {t('entry.confidence')}: {e.confidence}
          </div>
          {e.issues?.length ? <Alert style={{ marginTop: 10 }} type="info" showIcon message={t('entry.issues')} description={<ul style={{ margin: 0, paddingLeft: 18 }}>{e.issues.map((s: string) => <li key={s}>{s}</li>)}</ul>} /> : null}
        </SectionCard>
      </Col>
    </Row>
  );

  const structure = (
    <div>
      <Space style={{ marginBottom: 10 }}>
        {e.has_framework_cif ? (
          <Button icon={<DownloadOutlined />} onClick={() => api.download(`/hofs/${id}/cif`, { kind: 'framework', download: true }, `${e.name || id}_framework.cif`)}>
            {t('entry.framework')}
          </Button>
        ) : null}
        {e.has_raw_cif ? (
          <Button icon={<DownloadOutlined />} onClick={() => api.download(`/hofs/${id}/cif`, { kind: 'raw', download: true }, `${e.name || id}.cif`)}>
            {t('entry.raw')}
          </Button>
        ) : null}
      </Space>
      {hasCif ? (
        <Suspense fallback={<Spin />}>
          {cif.error ? <Alert type="warning" showIcon message={(cif.error as Error).message} /> : cif.data ? <Viewer3D data={cif.data} format="cif" height={560} /> : <Spin />}
        </Suspense>
      ) : (
        <Alert type="info" message="No CIF stored" />
      )}
      {e.cleaning_log?.length ? <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{e.cleaning_log.join(' ')}</div> : null}
    </div>
  );

  const synthesis = (
    <Table
      rowKey={(_r, i) => String(i)}
      pagination={false}
      dataSource={e.conditions || []}
      columns={[
        { title: t('entry.solvents'), dataIndex: 'solvents', render: (s: string[]) => s?.map((x) => <Tag key={x}>{x}</Tag>) },
        { title: t('entry.temperature'), dataIndex: 'temperature' },
        { title: t('entry.time'), dataIndex: 'time_h' },
        { title: t('entry.additive'), dataIndex: 'additive' },
      ]}
      footer={() => (
        <div>
          {e.application ? <div><b>{t('entry.application')}:</b> {e.application}</div> : null}
          {e.notes ? <div className="muted"><b>{t('entry.notes')}:</b> {e.notes}</div> : null}
        </div>
      )}
    />
  );

  const curation = (
    <Form layout="vertical" initialValues={{ name: e.name, topology: e.topology, curation_status: e.curation_status, notes: e.notes, interpenetration: e.interpenetration }} onFinish={save} style={{ maxWidth: 640 }}>
      <Form.Item name="name" label={t('common.name')}>
        <Input />
      </Form.Item>
      <Form.Item name="topology" label={t('db.topology')}>
        <Input placeholder="dia, sql, hcb …" />
      </Form.Item>
      <Form.Item name="interpenetration" label={t('builder.interpenetration')}>
        <InputNumber min={1} max={20} />
      </Form.Item>
      <Form.Item name="curation_status" label={t('db.status')}>
        <Select options={['auto', 'verified', 'needs_review', 'candidate', 'rejected'].map((s) => ({ value: s, label: t(`status.${s}`) }))} />
      </Form.Item>
      <Form.Item name="notes" label={t('entry.notes')}>
        <Input.TextArea rows={3} />
      </Form.Item>
      {['activation_retained', 'measured_porosity', 'extended_hbond_network', 'geometric_porosity'].map((k) => (
        <Form.Item key={k} name={['evidence', k, 'value']} label={t(`evidence.${k}`)}>
          <Select allowClear options={['yes', 'no', 'unknown'].map((v) => ({ value: v, label: t(`evidence.${v}`) }))} />
        </Form.Item>
      ))}
      <Button type="primary" htmlType="submit">
        {t('common.save')}
      </Button>
    </Form>
  );

  return (
    <div>
      <PageHead
        title={
          <span>
            {e.name || `#${e.id}`} <StatusTag status={e.curation_status} />
          </span>
        }
        sub={[e.hbond_class, e.year, e.formula].filter(Boolean).join(' · ')}
        extra={
          <Space>
            <AddToProject itemType="hof_entry" itemId={e.id} size="middle" />
            {main ? (
              <Button type="primary" icon={<ApartmentOutlined />} onClick={() => nav(`/builder?node=${encodeURIComponent(main.smiles)}${e.topology ? `&net=${e.topology}` : ''}`)}>
                {t('common.build')}
              </Button>
            ) : null}
          </Space>
        }
      />
      <Tabs
        items={[
          { key: 'o', label: t('entry.overview'), children: overview },
          { key: 's', label: t('entry.structure3d'), children: structure },
          { key: 'y', label: t('entry.synthesis'), children: synthesis },
          ...(isCurator ? [{ key: 'c', label: t('entry.curation'), children: curation }] : []),
        ]}
      />
      <Typography.Paragraph className="muted" style={{ fontSize: 12, marginTop: 12 }}>
        <Link to="/about">{t('nav.about')}</Link>
      </Typography.Paragraph>
    </div>
  );
}
